"""Conector CVM Dados Abertos — DFP (anual) e ITR (trimestral), consolidado e individual.

Cada linha do CSV vira um fato com: escala (ESCALA_MOEDA), moeda, escopo (GRUPO_DFP), período (DT_INI/DT_FIM),
versão do documento (VERSAO), data de recebimento (DT_RECEB) e localização (arquivo + linha original).
Versões reapresentadas são preservadas como novas linhas (bitemporal).
"""
import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .. import config
from ..db import tx
from .base import HttpClient, Run, SourceUnavailable, resolve_mode, save_raw, snapshot_manifest

SRC = "CVM_DADOS"
BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{kind}/DADOS/{kind_l}_cia_aberta_{year}.zip"
STATEMENTS = {"BPA": "BS", "BPP": "BS", "DRE": "IS", "DFC_MI": "CF"}
SCALE = {"MIL": 3, "UNIDADE": 0, "MILHAO": 6}
CCY = {"REAL": "BRL", "DOLAR": "USD"}
# Composição do capital não traz escala; Vale informa em milhares (confirmado no formulário DFP "Quantidade (Mil)").
SHARE_SCALE_OVERRIDE = {"33.592.510/0001-54": 3}
BRT = "-03:00"


def _files_for(kind: str, year: int, mode: str) -> Tuple[Dict[str, Tuple[List[str], str]], str, str]:
    """{nome_csv: (linhas_com_SRC_LINE, origem)}"""
    kind_l = kind.lower()
    if mode in ("live", "auto"):
        try:
            cl = HttpClient(SRC, 2)
            url = BASE.format(kind=kind, kind_l=kind_l, year=year)
            data = cl.get(url).content
            with tx() as c:
                save_raw(c, SRC, url, data, "live")
            zf = zipfile.ZipFile(io.BytesIO(data))
            out = {}
            for n in zf.namelist():
                if not (any(f"_{k}_" in n for k in STATEMENTS) or "composicao_capital" in n or n == f"{kind_l}_cia_aberta_{year}.csv"):
                    continue          # DMPL, DVA, DRA, pareceres: não usados — não carregar em memória
                lines = zf.read(n).decode("latin-1").splitlines()
                out[n] = (["SRC_LINE;" + lines[0]] + [f"{i};{l}" for i, l in enumerate(lines[1:], start=2)], url)
            return out, "live", datetime.now(timezone.utc).isoformat()
        except SourceUnavailable:
            if mode == "live":
                raise
    man = snapshot_manifest()
    out = {}
    fetched = None
    for p in sorted((config.SNAPSHOT_DIR / "cvm").glob(f"{kind_l}_cia_aberta_*{year}.csv")):
        m = man[f"cvm/{p.name}"]
        out[p.name] = (p.read_text(encoding="utf-8").splitlines(), m["origin"])
        fetched = m["fetched_at"]
        with tx() as c:
            save_raw(c, SRC, f"snapshot:cvm/{p.name} <- {m['origin']}", p.read_bytes(), "snapshot", fetched)
    return out, "snapshot", fetched or ""


FACT_COLS = ("issuer_id,source,concept,label,statement,scope,period_type,period_start,period_end,fiscal_year,fiscal_period,value,unit,currency,"
             "scale,basis,document_id,location,published_at,doc_version,raw_payload_id,natural_key")


def bulk_insert_facts(c, rows) -> int:
    """COPY para tabela temporária + INSERT ... ON CONFLICT DO NOTHING (idempotente, ~50x mais rápido que linha a linha)."""
    if not rows:
        return 0
    c.execute(f"CREATE TEMP TABLE IF NOT EXISTS tmp_fact AS SELECT {FACT_COLS} FROM fact WITH NO DATA")
    c.execute("TRUNCATE tmp_fact")
    with c.cursor().copy(f"COPY tmp_fact ({FACT_COLS}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row(r)
    cur = c.execute(f"INSERT INTO fact ({FACT_COLS}) SELECT {FACT_COLS} FROM tmp_fact ON CONFLICT (natural_key) DO NOTHING")
    return cur.rowcount


def _rows(lines: List[str]) -> Iterable[dict]:
    return csv.DictReader(lines, delimiter=";")


def ingest(issuers: Dict[str, str], kind: str, year: int, mode: Optional[str] = None) -> dict:
    """issuers: {CD_CVM ('009512'): issuer_id}"""
    mode = resolve_mode(mode)
    files, used, fetched_at = _files_for(kind, year, mode)
    run = Run(f"{SRC}:{kind}:{year}", used)
    try:
        with tx() as c:
            rp_ids = {r["request"]: r["id"] for r in c.execute("SELECT id, request FROM raw_payload WHERE source=%s", (SRC,)).fetchall()}
            # 1) documentos (cada VERSAO de cada DT_REFER é um documento)
            meta_name = f"{kind.lower()}_cia_aberta_{year}.csv"
            docs = {}
            by_cnpj = {}
            for r in _rows(files.get(meta_name, ([], ""))[0]):
                if r["CD_CVM"] not in issuers:
                    continue
                iid = issuers[r["CD_CVM"]]
                by_cnpj[r["CNPJ_CIA"]] = r["CD_CVM"]
                published = f"{r['DT_RECEB']}T00:00:00{BRT}"
                row = c.execute("""INSERT INTO document(issuer_id,source,external_id,form,period_end,version,published_at,url,meta)
                                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                   ON CONFLICT (source,external_id) DO UPDATE SET url=EXCLUDED.url RETURNING id""",
                                (iid, SRC, r["ID_DOC"], kind, r["DT_REFER"], int(r["VERSAO"]), published, r["LINK_DOC"],
                                 json.dumps({"cd_cvm": r["CD_CVM"], "cnpj": r["CNPJ_CIA"], "dt_refer": r["DT_REFER"],
                                             "published_precision": "dia (CVM não publica hora em DT_RECEB)"}))).fetchone()
                docs[(r["CD_CVM"], r["DT_REFER"], r["VERSAO"])] = (row["id"], published)
            # 2) fatos
            frows = []
            for name, (lines, origin) in files.items():
                part = next((k for k in STATEMENTS if f"_{k}_" in name), None)
                is_shares = "composicao_capital" in name
                if not part and not is_shares:
                    continue
                rp = next((v for k, v in rp_ids.items() if name in k), None)
                for r in _rows(lines):
                    if is_shares:
                        cd = by_cnpj.get(r["CNPJ_CIA"])
                        if cd is None:
                            continue
                        key = (cd, r["DT_REFER"], r["VERSAO"])
                    else:
                        cd = r["CD_CVM"]
                        if cd not in issuers:
                            continue
                        key = (cd, r["DT_REFER"], r["VERSAO"])
                    if key not in docs:
                        run.quarantine(c, {"file": name, "line": r["SRC_LINE"]}, "documento sem metadados (DT_REFER/VERSAO)")
                        continue
                    doc_id, published = docs[key]
                    if is_shares:
                        sc = SHARE_SCALE_OVERRIDE.get(r["CNPJ_CIA"], 0)
                        for col, concept, label in (("QT_ACAO_TOTAL_CAP_INTEGR", "shares_total", "Ações — total do capital integralizado"),
                                                    ("QT_ACAO_TOTAL_TESOURO", "shares_treasury", "Ações em tesouraria"),
                                                    ("QT_ACAO_ORDIN_CAP_INTEGR", "shares_on", "Ações ON"), ("QT_ACAO_PREF_CAP_INTEGR", "shares_pn", "Ações PN")):
                            v = Decimal(r[col]) * (Decimal(10) ** sc)
                            nk = f"CVM|{cd}|{concept}|{r['DT_REFER']}|{doc_id}"
                            frows.append((issuers[cd], SRC, concept, label, "OTHER", "consolidated", "instant", None, r["DT_REFER"], int(r["DT_REFER"][:4]),
                                          "I", v, "shares", None, sc, "reported", doc_id,
                                          json.dumps({"file": name, "line": int(r["SRC_LINE"]), "column": col, "origin": origin,
                                                      "scale_note": "escala inferida do formulário (CSV não informa)" if sc else None}),
                                          published, int(r["VERSAO"]), rp, nk))
                        continue
                    if r["CD_CONTA"].count(".") > 3:
                        continue
                    scope = "consolidated" if "_con_" in name else "individual"
                    try:
                        raw_v = Decimal(r["VL_CONTA"])
                    except InvalidOperation:
                        run.quarantine(c, {"file": name, "line": r["SRC_LINE"], "VL_CONTA": r["VL_CONTA"]}, "VL_CONTA inválido")
                        continue
                    sc = SCALE.get(r["ESCALA_MOEDA"])
                    ccy = CCY.get(r["MOEDA"])
                    if sc is None or ccy is None:
                        run.quarantine(c, {"file": name, "line": r["SRC_LINE"], "ESCALA": r["ESCALA_MOEDA"], "MOEDA": r["MOEDA"]}, "escala/moeda desconhecida")
                        continue
                    st = STATEMENTS[part]
                    ini = r.get("DT_INI_EXERC") or None
                    fim = r["DT_FIM_EXERC"]
                    fy = int(fim[:4])
                    if ini is None:
                        fp = "I"
                    else:
                        months = (int(fim[:4]) - int(ini[:4])) * 12 + int(fim[5:7]) - int(ini[5:7]) + 1
                        fp = "FY" if months == 12 else (f"Q{int(fim[5:7]) // 3}" if months == 3 else f"{months}M")
                    nk = f"CVM|{cd}|{scope}|{r['CD_CONTA']}|{ini or ''}|{fim}|{doc_id}"
                    frows.append((issuers[cd], SRC, r["CD_CONTA"], r["DS_CONTA"], st, scope, "duration" if ini else "instant", ini, fim, fy, fp,
                                  raw_v * (Decimal(10) ** sc), "BRL" if ccy == "BRL" else ccy, ccy, sc, "reported", doc_id,
                                  json.dumps({"file": name, "line": int(r["SRC_LINE"]), "cd_conta": r["CD_CONTA"], "ordem_exerc": r["ORDEM_EXERC"],
                                              "st_conta_fixa": r["ST_CONTA_FIXA"], "grupo": r["GRUPO_DFP"], "escala": r["ESCALA_MOEDA"],
                                              "moeda": r["MOEDA"], "vl_conta": r["VL_CONTA"], "origin": origin}),
                                  published, int(r["VERSAO"]), rp, nk))
            ins = bulk_insert_facts(c, frows)
            run.stats.update(inserted=ins, skipped_existing=len(frows) - ins, documents=len(docs))
        return run.finish()
    except Exception as e:
        run.finish("error", str(e))
        raise
