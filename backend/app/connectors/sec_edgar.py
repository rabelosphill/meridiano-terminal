"""Conector SEC EDGAR: submissions + XBRL companyfacts + documentos 10-K/10-Q em Inline XBRL.

live:     baixa da SEC (User-Agent obrigatório, <=8 req/s) e guarda o payload original.
snapshot: lê data/snapshot/sec (bytes originais + manifest com origem e instante).
"""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from .. import config
from ..db import tx
from ..services.templates import SEC_TAG_STATEMENT
from . import ixbrl
from .base import HttpClient, Run, SourceUnavailable, resolve_mode, save_raw, snapshot_manifest

SRC = "SEC_EDGAR"
FORMS = ("10-K", "10-Q", "10-K/A", "10-Q/A")
try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore
NY = ZoneInfo("America/New_York")


def _client():
    return HttpClient(SRC, 8, headers={"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"})


def fiscal_year_of(end: date, fye_mmdd: str) -> int:
    m, d = int(fye_mmdd[:2]), int(fye_mmdd[2:])
    fy_end_this = date(end.year, m, min(d, 28))
    return end.year + (1 if end > fy_end_this + timedelta(days=10) else 0)


def fiscal_period_of(start: Optional[date], end: date, fy: int, fye_mmdd: str) -> str:
    if start is None:
        return "I"  # saldo
    days = (end - start).days
    if days > 340:
        return "FY"
    m = int(fye_mmdd[:2])
    fy_start = date(fy - 1, m, 28) + timedelta(days=3)
    if 80 <= days <= 100:
        q = round(((end - fy_start).days) / 91.3)
        return f"Q{max(1, min(4, q))}"
    if 170 <= days <= 190:
        return "6M"
    if 260 <= days <= 285:
        return "9M"
    return f"{days}D"


def _load(mode: str, cik: str, docs: list):
    """Retorna (submissions_bytes, facts_bytes, {primaryDoc: bytes}, origem, fetched_at)."""
    if mode in ("live", "auto"):
        try:
            cl = _client()
            sub = cl.get(f"https://data.sec.gov/submissions/CIK{cik}.json").content
            cf = cl.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json").content
            s = json.loads(sub)
            r = s["filings"]["recent"]
            files = {}
            n10k = 0
            for i, form in enumerate(r["form"]):
                if form == "10-K" and n10k < 5:
                    n10k += 1
                    accn = r["accessionNumber"][i].replace("-", "")
                    pd = r["primaryDocument"][i]
                    files[pd] = cl.get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{pd}").content
            return sub, cf, files, "live", datetime.now(timezone.utc).isoformat()
        except SourceUnavailable:
            if mode == "live":
                raise
    man = snapshot_manifest()
    d = config.SNAPSHOT_DIR / "sec"
    sub = (d / f"submissions_CIK{cik}.json").read_bytes()
    cf = (d / f"companyfacts_CIK{cik}.json").read_bytes()
    files = {p.name: p.read_bytes() for p in d.glob("*.htm")}
    return sub, cf, files, "snapshot", man[f"sec/submissions_CIK{cik}.json"]["fetched_at"]


def ingest(issuer_id, cik: str, fye: str, mode: Optional[str] = None) -> dict:
    mode = resolve_mode(mode)
    sub_b, cf_b, files, used, fetched_at = _load(mode, cik, [])
    run = Run(SRC, used)
    try:
        with tx() as c:
            rp_sub = save_raw(c, SRC, f"submissions/CIK{cik}.json", sub_b, used, fetched_at)
            rp_cf = save_raw(c, SRC, f"api/xbrl/companyfacts/CIK{cik}.json", cf_b, used, fetched_at)
            sub = json.loads(sub_b)
            r = sub["filings"]["recent"]
            accn_info = {}
            for i, form in enumerate(r["form"]):
                if form not in FORMS:
                    continue
                accn = r["accessionNumber"][i]
                acc = r.get("acceptanceDateTime", [None] * len(r["form"]))[i]
                # acceptanceDateTime é UTC (conferido no índice EDGAR: 0001292814-26-005335 "Accepted 2026-11-16 18:33:09" ET = 23:33:09Z)
                published = (datetime.fromisoformat(acc[:19]).replace(tzinfo=timezone.utc).isoformat() if acc
                             else f"{r['filingDate'][i]}T16:00:00-05:00")
                pdoc = r["primaryDocument"][i]
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{pdoc}"
                obj_key = sha = rp = None
                ix_index = {}
                if pdoc in files:
                    rp = save_raw(c, SRC, url, files[pdoc], used, fetched_at)
                    row = c.execute("SELECT object_key, sha256 FROM raw_payload WHERE id=%s", (rp,)).fetchone()
                    obj_key, sha = row["object_key"], row["sha256"]
                    ix_index = ixbrl.index_by_key(ixbrl.parse_facts(files[pdoc].decode("utf-8", "replace")))
                accn_info[accn] = {"published": published, "form": form}
                c.execute("""INSERT INTO document(issuer_id,source,external_id,form,period_end,published_at,url,object_key,content_type,sha256,raw_payload_id,meta)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                             ON CONFLICT (source,external_id) DO UPDATE SET object_key=COALESCE(EXCLUDED.object_key,document.object_key),
                               sha256=COALESCE(EXCLUDED.sha256,document.sha256), raw_payload_id=COALESCE(EXCLUDED.raw_payload_id,document.raw_payload_id),
                               meta=CASE WHEN EXCLUDED.object_key IS NOT NULL THEN EXCLUDED.meta ELSE document.meta END""",
                          (issuer_id, SRC, accn, form, r["reportDate"][i] or None, published, url, obj_key,
                           "text/html" if obj_key else None, sha, rp, json.dumps({"primary_document": pdoc, "ix": ix_index})))
            docs = {d["external_id"]: d for d in c.execute("SELECT id, external_id, meta FROM document WHERE issuer_id=%s AND source=%s", (issuer_id, SRC)).fetchall()}

            cf = json.loads(cf_b)
            rows = []
            for ns in ("us-gaap", "dei"):
                for concept, body in cf["facts"].get(ns, {}).items():
                    statement = SEC_TAG_STATEMENT.get(concept, "OTHER")
                    for unit, arr in body["units"].items():
                        for x in arr:
                            if x.get("form") not in FORMS:
                                continue
                            accn = x["accn"]
                            start = x.get("start")
                            end = x["end"]
                            if accn not in accn_info:  # filing fora da janela 'recent' — guarda com data de filing
                                accn_info[accn] = {"published": f"{x['filed']}T16:00:00-05:00", "form": x["form"]}
                            doc = docs.get(accn)
                            ix = (doc["meta"].get("ix", {}) if doc else {}).get(f"{concept}|{start or ''}|{end}")
                            e = date.fromisoformat(end)
                            s = date.fromisoformat(start) if start else None
                            fy = fiscal_year_of(e, fye)
                            fp = fiscal_period_of(s, e, fy, fye)
                            val = x.get("val")
                            if val is None or not isinstance(val, (int, float)):
                                run.quarantine(c, {"concept": concept, **x}, "valor não numérico")
                                continue
                            scale = ix["scale"] if ix else (6 if unit == "USD" else (3 if unit == "shares" else 0))
                            ccy = "USD" if unit.startswith("USD") else None
                            nk = f"SEC|{cik}|{concept}|{unit}|{start or ''}|{end}|{accn}"
                            loc = {"accn": accn, "form": x["form"], "frame": x.get("frame"), "filing_fy": x.get("fy"), "filing_fp": x.get("fp"),
                                   "ix_ids": ix["ids"] if ix else [], "shown": ix["shown"] if ix else None,
                                   "payload": f"companyfacts/{ns}/{concept}/units/{unit}"}
                            rows.append((issuer_id, SRC, concept, body.get("label") or concept, statement, "consolidated",
                                         "duration" if start else "instant", start, end, fy, fp, Decimal(str(val)), unit, ccy, scale,
                                         "reported", doc["id"] if doc else None, json.dumps(loc), accn_info[accn]["published"], 1, rp_cf, nk))
            before = c.execute("SELECT count(*) n FROM fact WHERE issuer_id=%s AND source=%s", (issuer_id, SRC)).fetchone()["n"]
            c.cursor().executemany("""INSERT INTO fact(issuer_id,source,concept,label,statement,scope,period_type,period_start,period_end,fiscal_year,
                                     fiscal_period,value,unit,currency,scale,basis,document_id,location,published_at,doc_version,raw_payload_id,natural_key)
                                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                     ON CONFLICT (natural_key) DO NOTHING""", rows)
            after = c.execute("SELECT count(*) n FROM fact WHERE issuer_id=%s AND source=%s", (issuer_id, SRC)).fetchone()["n"]
            run.stats["inserted"] = after - before
            run.stats["skipped_existing"] = len(rows) - (after - before)
            run.stats["revisions"] = c.execute("""SELECT count(*) n FROM (SELECT concept, unit, period_start, period_end FROM fact
                       WHERE issuer_id=%s AND source=%s GROUP BY 1,2,3,4 HAVING count(DISTINCT value) > 1) t""", (issuer_id, SRC)).fetchone()["n"]
            run.stats["documents"] = len(docs)
        return run.finish()
    except Exception as e:
        run.finish("error", str(e))
        raise
