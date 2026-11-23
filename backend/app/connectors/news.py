"""Comunicados primários com uso autorizado (domínio público / dados abertos):

- SEC EDGAR 8-K (emissores americanos) e 6-K (estrangeiros) — instante de aceite em UTC (precisão de segundo)
- CVM IPE — Fato Relevante, Comunicado ao Mercado, Aviso aos Acionistas (precisão de DIA: Data_Entrega)
- Federal Reserve — press releases (RSS, US gov, domínio público)
- Copom — evento derivado da série SGS 432 (mudança da meta Selic), marcado como derivado

Veículos jornalísticos (Reuters, Bloomberg, Valor…) dependem de contrato: ver NEWS_CATALOG.
Não armazenamos texto integral de terceiros; guardamos metadados, manchete e link para o original.
"""
import csv
import html
import io
import json
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

from .. import config
from ..db import q, q1, tx
from .base import HttpClient, Run, SourceUnavailable, resolve_mode, save_raw, snapshot_manifest

UA = {"User-Agent": config.SEC_USER_AGENT}
SNAP = config.SNAPSHOT_DIR / "news"

ITEMS_8K = {
    "1.01": "Acordo material relevante", "1.02": "Encerramento de acordo material", "2.01": "Aquisição ou alienação de ativos",
    "2.02": "Resultados operacionais e situação financeira", "2.03": "Nova obrigação financeira direta", "2.05": "Custos de saída",
    "3.01": "Aviso de deslistagem", "5.02": "Mudança de diretores/conselheiros", "5.03": "Alteração do estatuto",
    "5.07": "Resultado de votação de acionistas", "7.01": "Divulgação Regulation FD", "8.01": "Outros eventos", "9.01": "Demonstrações e anexos",
}
MATERIAL_8K = {"1.01", "2.01", "2.02", "3.01", "5.02", "8.01"}

# Catálogo de fontes: o que está integrado e o que depende de contrato. Site/RSS público ≠ direito de redistribuição.
NEWS_CATALOG = [
    {"source": "SEC EDGAR 8-K/6-K", "status": "integrado", "rights": "domínio público (17 CFR 200.80)", "precision": "segundo (aceite UTC)"},
    {"source": "CVM Empresas.NET (fatos relevantes, comunicados — a cada 2 min)", "status": "integrado", "rights": "documento público CVM", "precision": "minuto (entrega)"},
    {"source": "CVM IPE (dados abertos, histórico)", "status": "integrado", "rights": "dados abertos CVM (ODbL)", "precision": "dia (Data_Entrega)"},
    {"source": "Federal Reserve press releases", "status": "integrado", "rights": "domínio público (governo dos EUA)", "precision": "segundo (RSS pubDate)"},
    {"source": "Copom (derivado da SGS 432)", "status": "integrado (derivado)", "rights": "dados abertos BCB", "precision": "dia (vigência)"},
] + [{"source": s, "status": "depende de contrato", "rights": "licença de redistribuição necessária", "precision": "—"} for s in (
    "Reuters", "Bloomberg News", "Dow Jones Newswires", "Financial Times", "The Wall Street Journal", "Valor Econômico", "Broadcast (Estadão)",
    "Brazil Journal", "Nikkei Asia", "Caixin", "Handelsblatt", "Les Echos")]


def _upsert(c, item: dict, links: List[dict]) -> bool:
    row = c.execute("""INSERT INTO news_item(source,outlet,distributor,external_id,url,lang,kind,headline,summary,published_at,time_precision,
                         region,topics,material,license,translation_allowed,raw_payload_id,meta)
                       VALUES (%(source)s,%(outlet)s,%(distributor)s,%(external_id)s,%(url)s,%(lang)s,%(kind)s,%(headline)s,%(summary)s,%(published_at)s,
                         %(time_precision)s,%(region)s,%(topics)s,%(material)s,%(license)s,false,%(raw_payload_id)s,%(meta)s)
                       ON CONFLICT (source,external_id,version) DO NOTHING RETURNING id""",
                    {**item, "meta": json.dumps(item.get("meta", {})), "summary": item.get("summary"), "raw_payload_id": item.get("raw_payload_id")}).fetchone()
    if not row:
        return False
    for l in links:
        c.execute("INSERT INTO news_link(news_id,issuer_id,instrument_id,relation,rationale) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                  (row["id"], l.get("issuer_id"), l.get("instrument_id"), l["relation"], l.get("rationale")))
    return True


def _headline_6k(doc: str) -> str:
    t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", doc)))
    m = re.search(r"No\s*_*X?_*\s+(.*)", t[t.find("12g3-2(b)"):] if "12g3-2(b)" in t else t)
    body = (m.group(1) if m else t).strip()
    head = re.split(r"\s[—–-]\s(?:Rio de Janeiro|Rio|São Paulo|Sao Paulo)|\s{3,}", body)[0]
    return head[:180].strip() or "Relatório 6-K"


def _instruments_of(issuer_id) -> List[dict]:
    return q("SELECT id FROM instrument WHERE issuer_id=%s", (issuer_id,))


def ingest_sec(cik: str, issuer_id, outlet: str, mode: Optional[str] = None, limit_6k: int = 60) -> dict:
    mode = resolve_mode(mode)
    used = "snapshot"
    subs = None
    docs: Dict[str, bytes] = {}
    if mode in ("live", "auto"):
        try:
            cl = HttpClient("SEC_EDGAR", 8, headers=UA)
            subs = cl.get(f"https://data.sec.gov/submissions/CIK{cik}.json").content
            r = json.loads(subs)["filings"]["recent"]
            known = {x["external_id"] for x in q("SELECT external_id FROM news_item WHERE source='SEC_EDGAR'")}
            n = 0
            for i, f in enumerate(r["form"]):
                if f == "6-K" and n < limit_6k:
                    n += 1
                    accn = r["accessionNumber"][i]
                    if accn in known:          # incremental: não rebaixa o que já foi ingerido
                        continue
                    docs[accn] = cl.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{r['primaryDocument'][i]}").content
            used = "live"
            (SNAP / "sec").mkdir(parents=True, exist_ok=True)
            (SNAP / "sec" / f"submissions_CIK{cik}.json").write_bytes(subs)
            for a, b in docs.items():
                (SNAP / "sec" / f"{a}.htm").write_bytes(b)
        except SourceUnavailable:
            if mode == "live":
                raise
    if subs is None:
        subs = (SNAP / "sec" / f"submissions_CIK{cik}.json").read_bytes()
        for p in (SNAP / "sec").glob("*.htm"):
            docs[p.stem] = p.read_bytes()
    run = Run(f"NEWS:SEC:{cik}", used)
    s = json.loads(subs)
    r = s["filings"]["recent"]
    links = [{"issuer_id": issuer_id, "instrument_id": i["id"], "relation": "direct", "rationale": f"documento do próprio emissor ({outlet})"} for i in _instruments_of(issuer_id)]
    inserted = 0
    with tx() as c:
        rp = save_raw(c, "SEC_EDGAR", f"submissions/CIK{cik}.json (notícias)", subs, used)
        for i, form in enumerate(r["form"]):
            if form not in ("8-K", "6-K"):
                continue
            accn = r["accessionNumber"][i]
            acc = r["acceptanceDateTime"][i]
            published = datetime.fromisoformat(acc[:19]).replace(tzinfo=timezone.utc)
            if published < datetime(2024, 1, 1, tzinfo=timezone.utc):
                continue
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{r['primaryDocument'][i]}"
            if form == "8-K":
                items = [x.strip() for x in (r.get("items", [""] * len(r["form"]))[i] or "").split(",") if x.strip()]
                head = f"{outlet} 8-K: " + "; ".join(ITEMS_8K.get(x, f"Item {x}") for x in items if x != "9.01") or f"{outlet} 8-K"
                material = bool(set(items) & MATERIAL_8K)
                topics = ["earnings"] if "2.02" in items else []
            else:
                if accn not in docs:
                    continue
                head = f"{outlet}: {_headline_6k(docs[accn].decode('utf-8', 'replace'))}"
                low = head.lower()
                topics = (["earnings"] if any(k in low for k in ("results", "resultado", "financial statements", "earnings")) and not any(k in low for k in ("webcast", "schedule", "agenda")) else []) + \
                         (["dividends"] if any(k in low for k in ("dividend", "provento", "interest on capital", "jcp")) else [])
                material = bool(topics) or "material fact" in low or "fato relevante" in low
            ok = _upsert(c, {"source": "SEC_EDGAR", "outlet": outlet, "distributor": "SEC EDGAR", "external_id": accn, "url": url, "lang": "en",
                             "kind": "regulatory_filing", "headline": head, "published_at": published.isoformat(), "time_precision": "second",
                             "region": ["US"] if form == "8-K" else ["BR", "US"], "topics": topics, "material": material,
                             "license": "domínio público (SEC)", "raw_payload_id": rp,
                             "meta": {"form": form, "accession": accn, "filing_date": r["filingDate"][i]}}, links)
            inserted += ok
    run.stats.update(inserted=inserted)
    return run.finish()


IPE_KEEP = {"Fato Relevante", "Comunicado ao Mercado", "Aviso aos Acionistas", "Relatório Proventos", "Calendário de Eventos Corporativos"}


def ingest_cvm_ipe(year: int, cvm_codes: Dict[str, str], mode: Optional[str] = None) -> dict:
    mode = resolve_mode(mode)
    url = f"https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
    used = "snapshot"
    text = None
    if mode in ("live", "auto"):
        try:
            data = HttpClient("CVM_DADOS", 2).get(url).content
            zf = zipfile.ZipFile(io.BytesIO(data))
            text = zf.read(zf.namelist()[0]).decode("latin-1")
            keep = [l for i, l in enumerate(text.splitlines()) if i == 0 or l.split(";")[2].lstrip("0") in {k.lstrip("0") for k in cvm_codes}]
            (SNAP / "cvm").mkdir(parents=True, exist_ok=True)
            (SNAP / "cvm" / f"ipe_cia_aberta_{year}.csv").write_text("\n".join(keep) + "\n", encoding="utf-8")
            text = "\n".join(keep)
            used = "live"
        except SourceUnavailable:
            if mode == "live":
                raise
    if text is None:
        text = (SNAP / "cvm" / f"ipe_cia_aberta_{year}.csv").read_text(encoding="utf-8")
    run = Run(f"NEWS:CVM_IPE:{year}", used)
    inserted = 0
    norm = {k.lstrip("0"): v for k, v in cvm_codes.items()}
    rad_known = {x["p"] for x in q("SELECT substring(external_id from 5) p FROM news_item WHERE source='CVM_DADOS' AND external_id LIKE 'rad-%%'")}
    cache: dict = {}
    with tx() as c:
        rp = save_raw(c, "CVM_DADOS", f"{url} (filtrado)", text.encode("utf-8"), used)
        for row in csv.DictReader(io.StringIO(text), delimiter=";"):
            iid = norm.get(row["Codigo_CVM"].lstrip("0"))
            if not iid or row["Categoria"] not in IPE_KEEP:
                continue
            pm = re.search(r"numProtocolo=(\d+)", row["Link_Download"] or "")
            if pm and pm.group(1) in rad_known:      # já veio em tempo real (com hora) pelo Empresas.NET
                continue
            if iid not in cache:
                cache[iid] = (q1("SELECT short_name FROM issuer WHERE id=%s", (iid,))["short_name"], _instruments_of(iid))
            short, insts = cache[iid]
            head = f"{short} — {row['Categoria']}: {row['Assunto'] or row['Tipo'] or row['Especie'] or ''}".strip(" :")
            cat = row["Categoria"]
            links = [{"issuer_id": iid, "instrument_id": i["id"], "relation": "direct", "rationale": "comunicado do próprio emissor (CVM IPE)"} for i in insts] \
                or [{"issuer_id": iid, "instrument_id": None, "relation": "direct", "rationale": "comunicado do próprio emissor (CVM IPE)"}]
            ok = _upsert(c, {"source": "CVM_DADOS", "outlet": short, "distributor": "CVM — Empresas.NET (IPE)", "external_id": f"{row['Protocolo_Entrega']}",
                             "url": row["Link_Download"], "lang": "pt", "kind": "official_release", "headline": head[:300],
                             # Data_Entrega não traz hora: fim do dia em BRT (conservador para consultas "como se sabia em D")
                             "published_at": f"{row['Data_Entrega']}T23:59:59-03:00", "time_precision": "day", "region": ["BR"],
                             "topics": (["dividends"] if "Provento" in cat or "Aviso aos Acionistas" in cat else []) + (["material_fact"] if cat == "Fato Relevante" else []),
                             "material": cat in ("Fato Relevante", "Relatório Proventos"), "license": "dados abertos CVM (ODbL)", "raw_payload_id": rp,
                             "meta": {"categoria": cat, "tipo": row["Tipo"], "especie": row["Especie"], "data_referencia": row["Data_Referencia"], "versao": row["Versao"]}}, links)
            inserted += ok
    run.stats.update(inserted=inserted)
    return run.finish()


RAD_URL = "https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx/ListarDocumentos"
_RAD_PROT = re.compile(r"OpenDownloadDocumentos\('(\d+)','(\d+)','(\d+)','IPE'\)")


def _strip(v: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", v)).strip(" -")


def ingest_cvm_rad(cvm_codes: Dict[str, str], days: int = 1) -> dict:
    """Quase tempo real: lista pública do Empresas.NET (RAD/CVM) com os comunicados IPE entregues hoje e ontem,
    com hora e minuto da entrega. O arquivo de dados abertos (ingest_cvm_ipe) só é republicado uma vez por dia
    e sem hora; quando ele chega, o mesmo protocolo não é duplicado."""
    import httpx
    hoje = datetime.now(timezone(timedelta(hours=-3))).date()
    body = {"dataDe": (hoje - timedelta(days=days)).strftime("%d/%m/%Y"), "dataAte": hoje.strftime("%d/%m/%Y"), "empresa": "",
            "setorAtividade": "-1", "categoriaEmissor": "-1", "situacaoEmissor": "-1", "tipoParticipante": "1", "dataReferencia": "",
            "categoria": "IPE_-1_-1_-1", "periodo": "2", "horaIni": "", "horaFim": "", "palavraChave": "", "ultimaDtRef": "false",
            "tipoEmpresa": "0", "token": "", "versaoCaptcha": ""}
    try:
        r = httpx.post(RAD_URL, json=body, timeout=30, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json; charset=utf-8"})
        r.raise_for_status()
        d = r.json()["d"]
        if d.get("temErro"):
            raise SourceUnavailable(d.get("msgErro") or "erro no RAD")
    except (httpx.HTTPError, ValueError, KeyError) as e:
        raise SourceUnavailable(f"RAD/CVM indisponível: {type(e).__name__}") from e
    run = Run("NEWS:CVM_RAD", "live")
    norm = {k.lstrip("0"): v for k, v in cvm_codes.items()}
    known = {x["u"] for x in q("""SELECT substring(url from 'numProtocolo=([0-9]+)') u FROM news_item
                                  WHERE source='CVM_DADOS' AND published_at >= now() - interval '10 days'""")}
    cache: dict = {}
    inserted = 0
    with tx() as c:
        rp = save_raw(c, "CVM_DADOS", f"{RAD_URL} {body['dataDe']}–{body['dataAte']}", r.content, "live")
        for rec in (d.get("dados") or "").split("&*"):
            f = rec.split("$&")
            if len(f) < 12:
                continue
            iid = norm.get(f[0].replace("-", "").lstrip("0"))
            cat = f[2].strip()
            m = _RAD_PROT.search(rec)
            if not iid or cat not in IPE_KEEP or not m or m.group(3) in known:
                continue
            seq, ver, prot = m.groups()
            ts = re.search(r"(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2})", _strip(f[6]))
            if not ts:
                continue
            dd, mm, yy, hh, mi = ts.groups()
            if iid not in cache:
                cache[iid] = (q1("SELECT short_name FROM issuer WHERE id=%s", (iid,))["short_name"], _instruments_of(iid))
            short, insts = cache[iid]
            assunto = _strip(f[11]) or _strip(f[4]) or _strip(f[3])
            head = f"{short} — {cat}: {assunto}".strip(" :")
            links = [{"issuer_id": iid, "instrument_id": i["id"], "relation": "direct", "rationale": "comunicado do próprio emissor (CVM — Empresas.NET)"} for i in insts] \
                or [{"issuer_id": iid, "instrument_id": None, "relation": "direct", "rationale": "comunicado do próprio emissor (CVM — Empresas.NET)"}]
            ok = _upsert(c, {"source": "CVM_DADOS", "outlet": short, "distributor": "CVM — Empresas.NET (consulta pública)", "external_id": f"rad-{prot}",
                             "url": f"https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx?Tela=ext&descTipo=IPE&CodigoInstituicao=1&numProtocolo={prot}&numSequencia={seq}&numVersao={ver}",
                             "lang": "pt", "kind": "official_release", "headline": head[:300],
                             "published_at": f"{yy}-{mm}-{dd}T{hh}:{mi}:00-03:00", "time_precision": "minute", "region": ["BR"],
                             "topics": (["dividends"] if "Provento" in cat or "Aviso aos Acionistas" in cat else []) + (["material_fact"] if cat == "Fato Relevante" else []),
                             "material": cat in ("Fato Relevante", "Relatório Proventos"), "license": "documento público CVM", "raw_payload_id": rp,
                             "meta": {"categoria": cat, "tipo": _strip(f[3]), "especie": _strip(f[4]), "data_referencia": _strip(f[5])[-10:], "versao": ver}}, links)
            known.add(prot)
            inserted += ok
    run.stats.update(inserted=inserted)
    return run.finish()


FED_URL = "https://www.federalreserve.gov/feeds/press_all.xml"


def ingest_fed(mode: Optional[str] = None) -> dict:
    mode = resolve_mode(mode)
    used, data = "snapshot", None
    if mode in ("live", "auto"):
        try:
            data = HttpClient("FED_PRESS", 2).get(FED_URL).content
            (SNAP / "fed").mkdir(parents=True, exist_ok=True)
            (SNAP / "fed" / "press_all.xml").write_bytes(data)
            used = "live"
        except SourceUnavailable:
            if mode == "live":
                raise
    if data is None:
        data = (SNAP / "fed" / "press_all.xml").read_bytes()
    run = Run("NEWS:FED", used)
    txt = data.decode("utf-8-sig", "replace")
    targets = q("SELECT l.instrument_id FROM listing l WHERE l.ticker IN ('UST10Y','USDBRL') AND l.valid_to IS NULL")
    links = [{"instrument_id": t["instrument_id"], "relation": "macro", "rationale": "política monetária dos EUA → Treasuries → dólar global → USD/BRL"} for t in targets]
    inserted = 0
    with tx() as c:
        rp = save_raw(c, "FED_PRESS", FED_URL, data, used)
        for it in re.findall(r"<item>(.*?)</item>", txt, re.S):
            g = lambda tag: (re.search(rf"<{tag}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", it, re.S) or [None, ""])[1].strip()
            title, link, cat, pub = html.unescape(g("title")), g("link"), g("category"), g("pubDate")
            if not link:
                continue
            monetary = "Monetary" in cat or "FOMC" in title
            ok = _upsert(c, {"source": "FED_PRESS", "outlet": "Federal Reserve Board", "distributor": "federalreserve.gov RSS", "external_id": link,
                             "url": link, "lang": "en", "kind": "central_bank", "headline": title, "summary": cat,
                             "published_at": parsedate_to_datetime(pub).isoformat(), "time_precision": "second", "region": ["US", "GLOBAL"],
                             "topics": ["monetary_policy"] if monetary else [cat.lower()], "material": monetary,
                             "license": "domínio público (governo dos EUA)", "raw_payload_id": rp, "meta": {"category": cat}},
                        links if monetary else [{**l, "rationale": "comunicado do Fed (relação macro indireta)"} for l in links[:1]])
            inserted += ok
    run.stats.update(inserted=inserted)
    return run.finish()


def derive_copom() -> dict:
    """Eventos 'Copom altera a Selic' a partir das mudanças da série SGS 432 (vigência = dia seguinte à reunião)."""
    obs = q("""SELECT DISTINCT ON (o.obs_date) o.obs_date, o.value FROM macro_observation o JOIN macro_series s ON s.id=o.series_id
               WHERE s.code='BR.SELIC' ORDER BY o.obs_date, o.vintage DESC""")
    targets = q("SELECT l.instrument_id FROM listing l WHERE l.ticker IN ('DI1F27','USDBRL') AND l.valid_to IS NULL")
    links = [{"instrument_id": t["instrument_id"], "relation": "macro", "rationale": "Copom → Selic → curva DI → diferencial de juros → USD/BRL"} for t in targets]
    run = Run("NEWS:COPOM_DERIVED", "derived")
    n = 0
    with tx() as c:
        prev = None
        for o in obs:
            if prev is not None and o["value"] != prev and o["obs_date"] >= date(2024, 1, 1):
                d = o["obs_date"]
                verb = "eleva" if o["value"] > prev else "reduz"
                n += _upsert(c, {"source": "BCB_SGS", "outlet": "Banco Central do Brasil — Copom", "distributor": "derivado da série SGS 432",
                                 "external_id": f"copom-{d}", "url": "https://www.bcb.gov.br/controleinflacao/historicotaxasjuros", "lang": "pt",
                                 "kind": "central_bank", "headline": f"Copom {verb} a meta Selic de {prev}% para {o['value']}% a.a. (vigência {d.strftime('%d/%m/%Y')})",
                                 "published_at": f"{d - timedelta(days=1)}T18:30:00-03:00", "time_precision": "day", "region": ["BR"],
                                 "topics": ["monetary_policy"], "material": True, "license": "dados abertos BCB",
                                 "meta": {"derived": True, "rule": "decisão anunciada na véspera da vigência, ~18h30 BRT (horário aproximado)"}}, links)
            prev = o["value"]
    run.stats.update(inserted=n)
    return run.finish()


def build_stories() -> int:
    """Agrupa comunicados do MESMO emissor no MESMO dia (BRT) vindos de canais diferentes (ex.: 6-K na SEC + Fato Relevante na CVM).
    Heurística declarada na própria história; não funde itens de emissores diferentes."""
    rows = q("""SELECT n.id, n.headline, n.published_at, (n.published_at AT TIME ZONE 'America/Sao_Paulo')::date d, nl.issuer_id, n.source
                FROM news_item n JOIN news_link nl ON nl.news_id=n.id AND nl.relation='direct' AND nl.issuer_id IS NOT NULL
                WHERE n.story_id IS NULL AND n.material""")
    groups: Dict[tuple, list] = {}
    for r in rows:
        groups.setdefault((r["issuer_id"], r["d"]), {})[r["id"]] = r
    n = 0
    with tx() as c:
        for (_, d), items in groups.items():
            its = list(items.values())
            if len({i["source"] for i in its}) < 2:
                continue
            first = min(its, key=lambda i: i["published_at"])
            st = c.execute("INSERT INTO story(title,first_at,last_at) VALUES (%s,%s,%s) RETURNING id",
                           (first["headline"], first["published_at"], max(i["published_at"] for i in its))).fetchone()["id"]
            for i in its:
                c.execute("UPDATE news_item SET story_id=%s WHERE id=%s", (st, i["id"]))
            n += 1
    return n
