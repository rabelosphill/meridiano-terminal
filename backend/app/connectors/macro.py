"""Conectores macro independentes: BCB SGS e FRED (CSV público).

Vintages: se uma observação já existe com valor diferente, grava nova vintage (revisão) —
nunca sobrescreve. Ausência ('.' no FRED) é armazenada como NULL, distinta de zero.
published_at: as fontes não informam o instante de publicação por observação; usamos a regra
documentada em PUBLICATION_RULE (fim do dia de referência, ou dia 10 do mês seguinte p/ IPCA).
"""
import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from .. import config
from ..db import tx
from .base import HttpClient, Run, SourceUnavailable, resolve_mode, save_raw, snapshot_manifest

PUBLICATION_RULE = {
    "BR.SELIC": ("dia de referência 00:00 BRT (meta vigente)", lambda d: f"{d}T00:00:00-03:00"),
    "BR.PTAX": ("dia de referência 13:30 BRT (boletim PTAX)", lambda d: f"{d}T13:30:00-03:00"),
    "BR.IPCA": ("dia 10 do mês seguinte, 09:00 BRT (calendário IBGE aproximado)",
                lambda d: f"{(date.fromisoformat(d).replace(day=28) + timedelta(days=4)).replace(day=10)}T09:00:00-03:00"),
    "GLOBAL.BRENT": ("dia útil seguinte 16:00 ET (EIA via FRED)", lambda d: f"{date.fromisoformat(d) + timedelta(days=1)}T16:00:00-05:00"),
    "US.UST10Y": ("dia útil seguinte 16:15 ET (H.15 via FRED)", lambda d: f"{date.fromisoformat(d) + timedelta(days=1)}T16:15:00-05:00"),
}

SNAP = {"BR.SELIC": "bcb/sgs_432.json", "BR.IPCA": "bcb/sgs_433.json", "BR.PTAX": "bcb/sgs_1.json",
        "GLOBAL.BRENT": "fred/DCOILBRENTEU.csv", "US.UST10Y": "fred/DGS10.csv"}


def _fetch(series: dict, mode: str):
    code, src, key = series["code"], series["source"], series["source_key"]
    if mode in ("live", "auto"):
        try:
            if src == "BCB_SGS":
                start = "01/01/2018" if series["frequency"] == "daily" else "01/01/2015"
                url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{key}/dados"
                r = HttpClient(src, 2).get(url, params={"formato": "json", "dataInicial": start, "dataFinal": date.today().strftime("%d/%m/%Y")})
                return r.content, str(r.url), "live", datetime.now(timezone.utc).isoformat()
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={key}"
            r = HttpClient(src, 2).get(url)
            return r.content, url, "live", datetime.now(timezone.utc).isoformat()
        except SourceUnavailable:
            if mode == "live":
                raise
    m = snapshot_manifest()[SNAP[code]]
    return (config.SNAPSHOT_DIR / SNAP[code]).read_bytes(), m["origin"], "snapshot", m["fetched_at"]


def parse(series: dict, data: bytes):
    if series["source"] == "BCB_SGS":
        for o in json.loads(data):
            d, mth, y = o["data"].split("/")
            yield f"{y}-{mth}-{d}", (Decimal(o["valor"]) if o["valor"] not in ("", None) else None)
    else:
        rd = csv.reader(io.StringIO(data.decode("utf-8")))
        next(rd)
        for row in rd:
            yield row[0], (None if row[1] in (".", "") else Decimal(row[1]))


def ingest(code: str, mode: Optional[str] = None, payload: Optional[bytes] = None) -> dict:
    mode = resolve_mode(mode)
    with tx() as c:
        series = c.execute("SELECT * FROM macro_series WHERE code=%s", (code,)).fetchone()
    if payload is None:
        data, origin, used, fetched_at = _fetch(series, mode)
    else:
        data, origin, used, fetched_at = payload, "test://payload", "test", datetime.now(timezone.utc).isoformat()
    run = Run(f"{series['source']}:{code}", used)
    rule = PUBLICATION_RULE[code][1]
    with tx() as c:
        rp = save_raw(c, series["source"], origin, data, used, fetched_at)
        latest = {str(r["obs_date"]): (r["value"], r["vintage"]) for r in c.execute(
            """SELECT DISTINCT ON (obs_date) obs_date, value, vintage FROM macro_observation WHERE series_id=%s
               ORDER BY obs_date, vintage DESC""", (series["id"],)).fetchall()}
        rows = []
        for d, v in parse(series, data):
            if d in latest:
                old, vint = latest[d]
                if old == v:
                    run.stats["skipped_existing"] += 1
                    continue
                run.stats["revisions"] += 1
                rows.append((series["id"], d, v, fetched_at, vint + 1, rp))   # revisão: conhecida no instante da coleta
            else:
                rows.append((series["id"], d, v, rule(d), 1, rp))
        c.cursor().executemany("""INSERT INTO macro_observation(series_id,obs_date,value,published_at,vintage,raw_payload_id)
                                  VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", rows)
        run.stats["inserted"] = len(rows)
    return run.finish()
