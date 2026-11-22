"""Universo Brasil completo a partir de fontes oficiais da CVM.

- Cadastro de companhias abertas (cad_cia_aberta.csv): CNPJ, razão social, nome comercial, código CVM, setor.
  Colunas de pessoas físicas (responsável, e-mail, telefone) são DESCARTADAS antes de qualquer armazenamento.
- FCA — valores mobiliários (fca_cia_aberta_valor_mobiliario_AAAA.csv): ticker ↔ CNPJ, classe, segmento, vigência.

Cada empresa vira legal_entity + issuer (chave persistente = UUID); cada ticker negociado em bolsa é ligado à
listagem B3 já criada pelo COTAHIST (mesmo instrumento, que passa a ter emissor).
"""
import csv
import io
import json
import unicodedata
import zipfile
from datetime import date
from typing import Dict, Optional

from ..db import q, tx
from .base import HttpClient, Run, save_raw

CAD_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv"
FCA_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{y}.zip"
KEEP_CAD = ["CNPJ_CIA", "DENOM_SOCIAL", "DENOM_COMERC", "DT_REG", "SIT", "DT_INI_SIT", "CD_CVM", "SETOR_ATIV", "TP_MERC", "CATEG_REG",
            "SIT_EMISSOR", "CONTROLE_ACIONARIO", "MUN", "UF", "PAIS"]

SECTOR = [  # (trecho normalizado de SETOR_ATIV, pacote setorial)
    ("BANCO", "banks"), ("INTERMEDIACAO FINANCEIRA", "banks"), ("SEGURADORA", "insurance"), ("PETROLEO", "oil_gas"),
    ("EXTRACAO MINERAL", "mining"), ("METALURGIA", "mining"), ("SIDERURGIA", "mining"), ("ENERGIA ELETRICA", "utilities"),
    ("SANEAMENTO", "utilities"), ("COMERCIO", "retail"), ("CONSTRUCAO CIVIL", "real_estate"), ("EMP. ADM. PART. - CONSTRUCAO", "real_estate"),
    ("COMUNICACAO E INFORMATICA", "software"), ("TELECOMUNICACOES", "utilities"),
]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).upper()


def sector_pack(setor: str) -> str:
    n = _norm(setor)
    return next((p for k, p in SECTOR if k in n), "generic")


LOWER = {"DO", "DA", "DE", "DOS", "DAS", "E", "EM", "NA", "NO"}


def _short(denom_comerc: str, denom_social: str) -> str:
    n = ((denom_comerc or "").strip() or denom_social).upper()
    for suf in (" - EM RECUPERACAO JUDICIAL", " - EM RECUPERAÇÃO JUDICIAL", " EM RECUPERACAO JUDICIAL", " EM RECUPERAÇÃO JUDICIAL"):
        n = n.replace(suf, "")
    for suf in (" S.A.", " S/A", " S.A", " SA", " S. A."):          # só no FINAL do nome
        if n.endswith(suf):
            n = n[: -len(suf)]
    words = []
    for i, w in enumerate(n.split()):
        if i and w in LOWER:
            words.append(w.lower())
        elif len(w) <= 3 and w.isalpha() and w not in LOWER:
            words.append(w)                                          # siglas: BB, WEG, CSN
        else:
            words.append(w[0] + w[1:].capitalize() if not w[0].isalpha() else w.capitalize())   # "(BRASIL)" -> "(Brasil)"
    return " ".join(words)[:60]


def ingest(years=(2025, 2026)) -> dict:
    cl = HttpClient("CVM_DADOS", 2)
    run = Run("CVM_UNIVERSE", "live")
    cad_raw = cl.get(CAD_URL).content.decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(cad_raw), delimiter=";"))
    # descarta dados pessoais antes de armazenar o payload
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=KEEP_CAD, delimiter=";", extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow(r)
    cad_clean = buf.getvalue().encode("utf-8")
    # FCA: tickers (versão mais recente de cada companhia)
    tickers: Dict[str, dict] = {}
    fca_payloads = []
    for y in years:
        data = cl.get(FCA_URL.format(y=y)).content
        fca_payloads.append((FCA_URL.format(y=y), data))
        zf = zipfile.ZipFile(io.BytesIO(data))
        name = next(n for n in zf.namelist() if "valor_mobiliario" in n)
        for r in csv.DictReader(io.StringIO(zf.read(name).decode("latin-1")), delimiter=";"):
            tk = (r["Codigo_Negociacao"] or "").strip().upper()
            if not tk or r["Mercado"] != "Bolsa" or r.get("Data_Fim_Negociacao"):
                continue
            prev = tickers.get(tk)
            key = (r["Data_Referencia"], int(r["Versao"] or 0))
            if not prev or key > prev["_k"]:
                tickers[tk] = {**r, "_k": key}
    # cadastro: uma linha por CNPJ (prefere situação ATIVO)
    comp: Dict[str, dict] = {}
    for r in rows:
        c = comp.get(r["CNPJ_CIA"])
        if not c or (r["SIT"] == "ATIVO" and c["SIT"] != "ATIVO"):
            comp[r["CNPJ_CIA"]] = r
    stats = {"companies": 0, "issuers_created": 0, "tickers_linked": 0, "tickers_without_listing": 0}
    with tx() as cx:
        save_raw(cx, "CVM_DADOS", CAD_URL + " (sem colunas de pessoas físicas)", cad_clean, "live")
        for u, d in fca_payloads:
            save_raw(cx, "CVM_DADOS", u, d, "live")
        listings = {r["ticker"]: r for r in cx.execute("""SELECT l.id, l.ticker, l.instrument_id, i.issuer_id FROM listing l
                                                          JOIN instrument i ON i.id=l.instrument_id WHERE l.exchange_mic='BVMF'""").fetchall()}
        by_cnpj = {r["tax_id"]: r["id"] for r in cx.execute("SELECT i.id, le.tax_id FROM issuer i JOIN legal_entity le ON le.id=i.legal_entity_id").fetchall()}
        with_ticker = {t["CNPJ_Companhia"] for t in tickers.values()}
        for cnpj, c in comp.items():
            if c["SIT"] != "ATIVO" and cnpj not in with_ticker:
                continue
            stats["companies"] += 1
            short = _short(c["DENOM_COMERC"], c["DENOM_SOCIAL"])
            pack = sector_pack(c["SETOR_ATIV"])
            iid = by_cnpj.get(cnpj)
            if iid:   # emissores criados por este conector: mantém nome curto/setor em dia
                cx.execute("UPDATE issuer SET short_name=%s, sector_pack=%s WHERE id=%s AND description LIKE 'Setor CVM:%%'", (short, pack, iid))
            if not iid:
                le = cx.execute("INSERT INTO legal_entity(name,country,tax_id) VALUES (%s,'BR',%s) RETURNING id", (c["DENOM_SOCIAL"], cnpj)).fetchone()["id"]
                iid = cx.execute("""INSERT INTO issuer(legal_entity_id,name,short_name,sector_pack,fiscal_year_end,reporting_std,description,status)
                                    VALUES (%s,%s,%s,%s,'1231','IFRS',%s,%s) RETURNING id""",
                                 (le, c["DENOM_SOCIAL"], short, pack, f"Setor CVM: {c['SETOR_ATIV'] or '—'}. Controle: {c['CONTROLE_ACIONARIO'] or '—'}. {c['MUN']}/{c['UF']}.",
                                  "active" if c["SIT"] == "ATIVO" else "inactive")).fetchone()["id"]
                by_cnpj[cnpj] = iid
                stats["issuers_created"] += 1
            for scheme, val in (("CVM_CODE", c["CD_CVM"].zfill(6)), ("CNPJ", cnpj)):
                cx.execute("""INSERT INTO identifier(object_type,object_id,scheme,value,valid_from,source) VALUES ('issuer',%s,%s,%s,'1900-01-01','CVM cadastro')
                              ON CONFLICT DO NOTHING""", (iid, scheme, val))
        for tk, t in tickers.items():
            iid = by_cnpj.get(t["CNPJ_Companhia"])
            l = listings.get(tk)
            if not iid:
                continue
            if not l:
                stats["tickers_without_listing"] += 1
                continue
            # classe/tipo vêm do registro da B3 (ESPECI no COTAHIST); o FCA só estabelece o emissor
            short = cx.execute("SELECT short_name FROM issuer WHERE id=%s", (iid,)).fetchone()["short_name"]
            cx.execute("""UPDATE instrument SET issuer_id=%s,
                          name=CASE WHEN attrs ? 'nomres' THEN %s || ' ' || coalesce(class_name,'') ELSE name END,
                          attrs = attrs || %s::jsonb WHERE id=%s""",
                       (iid, short, json.dumps({"segmento": t["Segmento"], "fca": t["ID_Documento"], "fca_valor_mobiliario": t["Valor_Mobiliario"]}), l["instrument_id"]))
            stats["tickers_linked"] += 1
    run.stats.update(inserted=stats["issuers_created"], **{k: v for k, v in stats.items() if k != "issuers_created"})
    run.finish()
    return {**stats, "inserted": stats["issuers_created"]}
