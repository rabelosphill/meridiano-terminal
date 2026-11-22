"""Conector B3 — Séries Históricas (COTAHIST), arquivo oficial de cotações diárias.

Layout posicional de 245 bytes (documentação "SeriesHistoricas_Layout.pdf" da B3). Usamos o mercado à vista
(TPMERC=010) lote padrão (CODBDI=02) e ETFs (CODBDI=14). Preços com 2 decimais implícitos e divididos por
FATCOT (fator de cotação). PREMED = preço médio dos negócios da sessão (calculado pela B3 sobre negócios
individuais) — é o VWAP de sessão exato. Barras são gravadas brutas; ajustes por eventos são aplicados na leitura.
"""
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Tuple

from .. import config
from ..db import q, tx
from .base import HttpClient, Run, SourceUnavailable, resolve_mode, save_raw, snapshot_manifest

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

SRC = "B3_COTAHIST"
URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"
SP = ZoneInfo("America/Sao_Paulo")
KEEP_BDI = {"02", "14"}


def _f(line: str, a: int, b: int) -> str:
    return line[a - 1:b]


def parse_line(line: str) -> Optional[dict]:
    if not line.startswith("01") or _f(line, 25, 27) != "010" or _f(line, 11, 12) not in KEEP_BDI:
        return None
    fat = Decimal(_f(line, 211, 217).strip() or "1")
    px = lambda a, b: Decimal(_f(line, a, b)) / 100 / fat
    return {
        "date": date(int(_f(line, 3, 6)), int(_f(line, 7, 8)), int(_f(line, 9, 10))),
        "bdi": _f(line, 11, 12), "ticker": _f(line, 13, 24).strip(), "nomres": _f(line, 28, 39).strip(),
        "especi": _f(line, 40, 49).strip(), "open": px(57, 69), "high": px(70, 82), "low": px(83, 95),
        "vwap": px(96, 108), "close": px(109, 121), "trades": int(_f(line, 148, 152)),
        "volume": Decimal(_f(line, 153, 170)), "fin_volume": Decimal(_f(line, 171, 188)) / 100,
        "isin": _f(line, 231, 242).strip(), "fatcot": int(fat), "dismes": _f(line, 243, 245).strip(),
    }


def build_snapshot(year: int) -> str:
    """Extrai do ZIP oficial as linhas do mercado à vista (lote padrão + ETFs), mantendo bytes e número da linha."""
    src = config.ROOT / "data" / "raw" / "b3" / f"COTAHIST_A{year}.ZIP"
    out = config.SNAPSHOT_DIR / "b3" / f"COTAHIST_A{year}_vista.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(src)
    raw = zf.read(zf.namelist()[0]).decode("latin-1").splitlines()
    keep = [f"{i}|{l}" for i, l in enumerate(raw, start=1) if l.startswith("01") and l[24:27] == "010" and l[10:12] in KEEP_BDI]
    out.write_text(raw[0] + "\n" + "\n".join(keep) + "\n", encoding="utf-8")
    return str(out)


def _lines(year: int, mode: str) -> Tuple[List[str], str, str, bytes]:
    if mode in ("live", "auto"):
        try:
            data = HttpClient(SRC, 1, headers={"User-Agent": "Mozilla/5.0"}).get(URL.format(year=year)).content
            zf = zipfile.ZipFile(io.BytesIO(data))
            raw = zf.read(zf.namelist()[0]).decode("latin-1").splitlines()
            return [f"{i}|{l}" for i, l in enumerate(raw, start=1)], URL.format(year=year), "live", data
        except SourceUnavailable:
            if mode == "live":
                raise
    p = config.SNAPSHOT_DIR / "b3" / f"COTAHIST_A{year}_vista.txt"
    if not p.exists():
        # o repositório público não redistribui as cotações da B3: na 1ª execução o arquivo oficial é baixado da própria B3
        raw_zip = config.ROOT / "data" / "raw" / "b3" / f"COTAHIST_A{year}.ZIP"
        if not raw_zip.exists():
            raw_zip.parent.mkdir(parents=True, exist_ok=True)
            raw_zip.write_bytes(HttpClient(SRC, 1, headers={"User-Agent": "Mozilla/5.0"}).get(URL.format(year=year)).content)
        build_snapshot(year)
    m = snapshot_manifest()[f"b3/{p.name}"]
    b = p.read_bytes()
    return b.decode("utf-8").splitlines()[1:], m["origin"], "snapshot", b


def _kind(bdi: str, especi: str) -> Tuple[str, str]:
    e = especi.upper()
    if bdi == "14":
        return "etf", "ETF"
    if e.startswith("UNT"):
        return "equity_unit", "UNT"
    if e.startswith("PN"):
        return "equity_pref", e.split()[0]
    return "equity_common", e.split()[0] if e else "ON"


def ingest(year: int, mode: Optional[str] = None) -> dict:
    mode = resolve_mode(mode)
    lines, origin, used, payload = _lines(year, mode)
    return _ingest_lines(lines, origin if used == "live" else f"snapshot:b3/COTAHIST_A{year}_vista.txt <- {origin}", used, payload,
                         f"{SRC}:{year}", f"COTAHIST_A{year}.TXT")


DAILY_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{d}.ZIP"


def ingest_daily(days: int = 7) -> dict:
    """Arquivos diários oficiais (~500 KB) dos últimos `days` dias corridos. 404 = dia sem pregão (não é erro)."""
    import httpx
    out = {"inserted": 0, "skipped_existing": 0, "files": [], "no_session": []}
    cl = HttpClient(SRC, 1, headers={"User-Agent": "Mozilla/5.0"}, max_retries=2)
    today = date.today()
    for k in range(days, -1, -1):
        d = today - timedelta(days=k)
        if d.weekday() >= 5:
            continue
        url = DAILY_URL.format(d=d.strftime("%d%m%Y"))
        try:
            data = cl.get(url).content
        except httpx.HTTPStatusError:
            out["no_session"].append(str(d))
            continue
        zf = zipfile.ZipFile(io.BytesIO(data))
        raw = zf.read(zf.namelist()[0]).decode("latin-1").splitlines()
        st = _ingest_lines([f"{i}|{l}" for i, l in enumerate(raw, start=1)], url, "live", data, f"{SRC}:D{d.isoformat()}", zf.namelist()[0])
        out["inserted"] += st["inserted"]; out["skipped_existing"] += st["skipped_existing"]; out["files"].append(str(d))
    return out


def _ingest_lines(lines: List[str], origin: str, used: str, payload: bytes, label: str, fname: str) -> dict:
    run = Run(label, used)
    with tx() as c:
        rp = save_raw(c, SRC, origin, payload, used)
        by_isin = {r["value"]: r["object_id"] for r in c.execute("SELECT value, object_id FROM identifier WHERE scheme='ISIN'").fetchall()}
        listings = {r["ticker"]: r["id"] for r in c.execute("SELECT id, ticker FROM listing WHERE exchange_mic='BVMF'").fetchall()}
        rows = []
        for raw in lines:
            n, _, line = raw.partition("|")
            try:
                r = parse_line(line)
            except Exception as e:  # linha corrompida -> quarentena, nunca silenciosa
                run.quarantine(c, {"line": n, "raw": line[:60]}, f"parse: {e}")
                continue
            if not r:
                continue
            tk = r["ticker"]
            if tk not in listings:
                ins_id = by_isin.get(r["isin"])
                if not ins_id:
                    kind, cls = _kind(r["bdi"], r["especi"])
                    ins_id = c.execute("""INSERT INTO instrument(kind,class_name,name,currency,attrs) VALUES (%s,%s,%s,'BRL',%s) RETURNING id""",
                                       (kind, cls, f"{r['nomres']} {r['especi']}".strip(),
                                        json.dumps({"origin": "B3 COTAHIST", "nomres": r["nomres"], "especi": r["especi"]}))).fetchone()["id"]
                    if r["isin"]:
                        c.execute("""INSERT INTO identifier(object_type,object_id,scheme,value,valid_from,source) VALUES ('instrument',%s,'ISIN',%s,'1900-01-01','B3 COTAHIST')
                                     ON CONFLICT DO NOTHING""", (ins_id, r["isin"]))
                        by_isin[r["isin"]] = ins_id
                listings[tk] = c.execute("""INSERT INTO listing(instrument_id,exchange_mic,ticker,currency,valid_from) VALUES (%s,'BVMF',%s,'BRL',%s) RETURNING id""",
                                         (ins_id, tk, r["date"])).fetchone()["id"]
            if r["close"] <= 0 or r["high"] < r["low"]:
                run.quarantine(c, {"line": n, "ticker": tk}, "OHLC inconsistente")
                continue
            open_ts = datetime(r["date"].year, r["date"].month, r["date"].day, 10, 0, tzinfo=SP).astimezone(timezone.utc)
            rows.append((listings[tk], "1d", open_ts, r["date"], r["open"], r["high"], r["low"], r["close"], r["volume"], r["fin_volume"],
                         r["trades"], r["vwap"], SRC, rp, json.dumps({"line": int(n), "file": fname, "fatcot": r["fatcot"], "dismes": r["dismes"]})))
        before = c.execute("SELECT count(*) n FROM price_bar WHERE source=%s", (SRC,)).fetchone()["n"]
        c.cursor().executemany("""INSERT INTO price_bar(listing_id,interval,ts,session_date,open,high,low,close,volume,fin_volume,trades,vwap,source,raw_payload_id,location)
                                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""", rows)
        after = c.execute("SELECT count(*) n FROM price_bar WHERE source=%s", (SRC,)).fetchone()["n"]
        run.stats.update(inserted=after - before, skipped_existing=len(rows) - (after - before))
    return run.finish()
