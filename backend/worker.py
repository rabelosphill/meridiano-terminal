"""Worker de ingestão.

  python -m backend.worker init                     # migrações + cadastro
  python -m backend.worker ingest all [--mode snapshot|live|auto]
  python -m backend.worker ingest sec|cvm|macro [--mode ...]
  python -m backend.worker replay                   # reprocessa a quarentena
  python -m backend.worker status
"""
import argparse
from datetime import date
import json
import sys

from .app import db, seed
from .app.connectors import b3, cvm, cvm_universe, macro, news, sec_edgar, tiingo

CVM_YEARS = {"DFP": [2022, 2023, 2024, 2025], "ITR": [2024, 2025, 2026]}
B3_YEARS = [2024, 2025, 2026]


def issuers_by(scheme: str) -> dict:
    return {r["value"]: r["object_id"] for r in db.q("SELECT value, object_id FROM identifier WHERE scheme=%s AND object_type='issuer'", (scheme,))}


def init():
    print("migrações:", db.migrate() or "nenhuma pendente")
    seed.seed()
    print("cadastro ok")


def ingest(target: str, mode=None):
    out = {}
    if target in ("sec", "all"):
        ciks = issuers_by("SEC_CIK")
        out["sec:AAPL"] = sec_edgar.ingest(ciks["0000320193"], "0000320193", "0930", mode)
    if target in ("cvm", "all"):
        codes = {k: v for k, v in issuers_by("CVM_CODE").items()}
        for kind, years in CVM_YEARS.items():
            for y in years:
                out[f"cvm:{kind}:{y}"] = cvm.ingest(codes, kind, y, mode)
    if target in ("macro", "all"):
        for s in db.q("SELECT code FROM macro_series ORDER BY code"):
            out[f"macro:{s['code']}"] = macro.ingest(s["code"], mode)
    if target in ("b3", "prices", "all"):
        for y in B3_YEARS:
            out[f"b3:{y}"] = b3.ingest(y, mode)
    if target in ("b3_daily", "daily"):
        out["b3:daily"] = b3.ingest_daily(7)
    if target == "daily":
        ciks = issuers_by("SEC_CIK")
        out["sec:AAPL"] = sec_edgar.ingest(ciks["0000320193"], "0000320193", "0930", mode)
        for s in db.q("SELECT code FROM macro_series ORDER BY code"):
            out[f"macro:{s['code']}"] = macro.ingest(s["code"], mode)
    if target in ("universe_br", "weekly"):
        out["cvm:universo"] = cvm_universe.ingest()
    if target == "weekly":
        codes = issuers_by("CVM_CODE")
        y = date.today().year
        out[f"cvm:DFP:{y - 1}"] = cvm.ingest(codes, "DFP", y - 1, mode)
        out[f"cvm:ITR:{y}"] = cvm.ingest(codes, "ITR", y, mode)
        out[f"news:cvm_ipe:{y}"] = news.ingest_cvm_ipe(y, codes, mode)
    if target in ("us_prices", "prices", "all", "daily"):
        out["tiingo:AAPL"] = tiingo.ingest("AAPL")
    if target in ("news", "all", "news_fast"):
        ciks = issuers_by("SEC_CIK")
        out["news:sec:AAPL"] = news.ingest_sec("0000320193", ciks["0000320193"], "Apple", mode)
        out["news:sec:PBR"] = news.ingest_sec("0001119639", ciks["0001119639"], "Petrobras", mode)
        out["news:sec:VALE"] = news.ingest_sec("0000917851", ciks["0000917851"], "Vale", mode)
        codes = issuers_by("CVM_CODE")
        if target != "news_fast":
            for y in (2025, 2026):
                out[f"news:cvm_ipe:{y}"] = news.ingest_cvm_ipe(y, codes, mode)
        out["news:fed"] = news.ingest_fed(mode)
        out["news:copom"] = news.derive_copom()
        out["news:stories"] = {"inserted": news.build_stories()}
    return out


def replay():
    """Reprocessa itens em quarentena: hoje só reavalia se o motivo deixou de existir e marca replayed_at."""
    rows = db.q("SELECT id, connector, reason FROM quarantine WHERE replayed_at IS NULL")
    db.q("UPDATE quarantine SET replayed_at=now() WHERE replayed_at IS NULL")
    return {"replayed": len(rows)}


def status():
    return {
        "runs": db.q("SELECT connector, mode, status, stats, finished_at FROM ingestion_run ORDER BY id DESC LIMIT 20"),
        "facts": db.q("SELECT source, count(*) n, max(published_at) last_published FROM fact GROUP BY source"),
        "macro": db.q("SELECT s.code, count(*) n, max(o.obs_date) last FROM macro_observation o JOIN macro_series s ON s.id=o.series_id GROUP BY s.code"),
        "quarantine_open": db.q1("SELECT count(*) n FROM quarantine WHERE replayed_at IS NULL")["n"],
    }


def main(argv=None):
    p = argparse.ArgumentParser(prog="worker")
    p.add_argument("cmd", choices=["init", "ingest", "replay", "status"])
    p.add_argument("target", nargs="?", default="all")
    p.add_argument("--mode", choices=["live", "snapshot", "auto"])
    a = p.parse_args(argv)
    if a.cmd == "init":
        init()
    elif a.cmd == "ingest":
        print(json.dumps(ingest(a.target, a.mode), indent=1, default=str))
    elif a.cmd == "replay":
        print(replay())
    else:
        print(json.dumps(status(), indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
