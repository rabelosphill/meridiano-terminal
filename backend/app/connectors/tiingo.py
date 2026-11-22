"""Conector Tiingo (EOD EUA) — fonte licenciada por chave. Só roda com TIINGO_API_KEY no ambiente.

Grava OHLCV BRUTO (open/high/low/close/volume) e registra desdobramentos (splitFactor≠1) e proventos (divCash>0)
em corporate_action, para que o ajuste seja feito uma única vez na leitura. NÃO VERIFICADO nesta entrega (sem credencial).
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from ..db import q1, tx
from .base import HttpClient, Run, save_raw

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

NY = ZoneInfo("America/New_York")


def ingest(ticker: str, start: str = "2024-01-01") -> dict:
    key = os.environ.get("TIINGO_API_KEY")
    if not key:
        return {"inserted": 0, "skipped": "TIINGO_API_KEY ausente — histórico EUA indisponível (licença necessária)"}
    li = q1("SELECT l.id, l.instrument_id FROM listing l WHERE l.ticker=%s AND l.valid_to IS NULL", (ticker,))
    url = f"https://api.tiingo.com/tiingo/daily/{ticker.lower()}/prices"
    r = HttpClient("TIINGO", 1).get(url, params={"startDate": start, "token": key})
    rows = r.json()
    run = Run(f"TIINGO:{ticker}", "live")
    with tx() as c:
        rp = save_raw(c, "TIINGO", url + f"?startDate={start}", r.content, "live")
        bars = []
        for x in rows:
            d = date.fromisoformat(x["date"][:10])
            open_ts = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY).astimezone(timezone.utc)
            bars.append((li["id"], "1d", open_ts, d, x["open"], x["high"], x["low"], x["close"], x["volume"], None, None, None, "TIINGO", rp,
                         json.dumps({"adjClose": x.get("adjClose")})))
            if x.get("splitFactor") not in (None, 1, 1.0):
                c.execute("""INSERT INTO corporate_action(instrument_id,kind,ex_date,ratio,detail,source) VALUES (%s,'split',%s,%s,'{}','TIINGO')
                             ON CONFLICT DO NOTHING""", (li["instrument_id"], d, Decimal(str(x["splitFactor"]))))
            if x.get("divCash"):
                c.execute("""INSERT INTO corporate_action(instrument_id,kind,ex_date,amount,currency,detail,source) VALUES (%s,'cash_dividend',%s,%s,'USD','{}','TIINGO')
                             ON CONFLICT DO NOTHING""", (li["instrument_id"], d, Decimal(str(x["divCash"]))))
        before = c.execute("SELECT count(*) n FROM price_bar WHERE listing_id=%s AND source='TIINGO'", (li["id"],)).fetchone()["n"]
        c.cursor().executemany("""INSERT INTO price_bar(listing_id,interval,ts,session_date,open,high,low,close,volume,fin_volume,trades,vwap,source,raw_payload_id,location)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", bars)
        after = c.execute("SELECT count(*) n FROM price_bar WHERE listing_id=%s AND source='TIINGO'", (li["id"],)).fetchone()["n"]
        run.stats["inserted"] = after - before                      # só o que foi realmente gravado
        run.stats["skipped_existing"] = len(bars) - (after - before)
    return run.finish()
