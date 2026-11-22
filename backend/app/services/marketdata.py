"""Barras OHLCV: leitura bruta ou ajustada, agregação semanal/mensal, sessões e eventos no gráfico."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from ..db import q, q1

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

INTERVALS = {"1m": "1 minuto", "5m": "5 minutos", "1D": "diário", "1W": "semanal", "1M": "mensal"}
WINDOWS = {"1D": 1, "5D": 5, "1M": 21, "3M": 63, "6M": 126, "YTD": None, "1Y": 252, "2Y": 504, "5Y": 1260, "MAX": 100000}


class AdjustmentError(Exception):
    pass


def listing_info(listing_id: str) -> dict:
    return q1("""SELECT l.*, e.code exchange_code, e.timezone, e.open_local, e.close_local, e.calendar_id, i.kind, i.name, i.id instrument_id
                 FROM listing l LEFT JOIN exchange e ON e.mic=l.exchange_mic JOIN instrument i ON i.id=l.instrument_id WHERE l.id=%s""", (listing_id,))


def raw_daily(listing_id: str, as_of: Optional[datetime] = None) -> List[dict]:
    sql = """SELECT ts, session_date, open, high, low, close, volume, fin_volume, trades, vwap, source, ingested_at, location
             FROM price_bar WHERE listing_id=%s AND interval='1d'"""
    args: list = [listing_id]
    if as_of:
        sql += " AND session_date <= %s"
        args.append(as_of.date())
    return q(sql + " ORDER BY session_date", args)


def adjustment_events(instrument_id: str) -> List[dict]:
    return q("SELECT id, kind, ex_date, ratio, amount, currency, source FROM corporate_action WHERE instrument_id=%s AND kind IN ('split','cash_dividend') ORDER BY ex_date",
             (instrument_id,))


def adjust(bars: List[dict], events: List[dict], already_adjusted: bool = False, include_dividends: bool = False) -> Dict[str, object]:
    """Ajuste retroativo por splits (e opcionalmente proventos). Barras anteriores à data ex são divididas pelo fator
    acumulado; volume multiplicado (splits). Aplicar sobre série já ajustada levanta AdjustmentError (nunca ajusta 2x)."""
    if already_adjusted:
        raise AdjustmentError("série já ajustada — eventos não podem ser reaplicados")
    seen = set()
    factors = []
    for e in events:
        if e["id"] in seen:
            raise AdjustmentError(f"evento {e['id']} duplicado")
        seen.add(e["id"])
        if e["kind"] == "split":
            factors.append((e["ex_date"], Decimal(e["ratio"]), Decimal(e["ratio"])))
        elif include_dividends and e["kind"] == "cash_dividend":
            prev = next((b for b in reversed(bars) if b["session_date"] < e["ex_date"]), None)
            if prev:
                f = Decimal(1) / (1 - Decimal(e["amount"]) / Decimal(prev["close"]))
                factors.append((e["ex_date"], f, Decimal(1)))
    out = []
    for b in bars:
        pf = vf = Decimal(1)
        for d, f, fv in factors:
            if b["session_date"] < d:
                pf *= f; vf *= fv
        nb = dict(b)
        for k in ("open", "high", "low", "close", "vwap"):
            if nb.get(k) is not None:
                nb[k] = Decimal(nb[k]) / pf
        if nb.get("volume") is not None:
            nb["volume"] = Decimal(nb["volume"]) * vf
        nb["adj_factor"] = str(pf)
        out.append(nb)
    first = bars[0]["session_date"] if bars else None
    used = [(d, f) for d, f, _ in factors if first and d > first]          # só eventos dentro do histórico carregado alteram barras
    return {"bars": out, "events_applied": [{"ex_date": str(d), "factor": str(f)} for d, f in used]}


def aggregate(bars: List[dict], interval: str) -> List[dict]:
    if interval in ("1D", "1m"):
        return bars
    key = (lambda d: d.isocalendar()[:2]) if interval == "1W" else (lambda d: (d.year, d.month))
    out: List[dict] = []
    for b in bars:
        k = key(b["session_date"])
        if out and out[-1]["_k"] == k:
            o = out[-1]
            o["high"] = max(o["high"], b["high"]); o["low"] = min(o["low"], b["low"]); o["close"] = b["close"]
            o["volume"] = (o["volume"] or 0) + (b["volume"] or 0); o["fin_volume"] = (o["fin_volume"] or 0) + (b["fin_volume"] or 0)
            o["end_date"] = b["session_date"]; o["sessions"] += 1
        else:
            out.append({**b, "_k": k, "end_date": b["session_date"], "sessions": 1})
    for o in out:
        o.pop("_k")
        o["vwap"] = (Decimal(o["fin_volume"]) / Decimal(o["volume"])) if o.get("fin_volume") and o.get("volume") else None
    return out


def is_session(calendar_id: str, d: date) -> bool:
    if d.weekday() >= 5:
        return False
    return not q1("SELECT 1 FROM calendar_holiday WHERE calendar_id=%s AND day=%s", (calendar_id, d))


def first_tradable_session(listing_id: str, instant: datetime, precision: str = "second") -> dict:
    """Primeira sessão regular em que a informação publicada em `instant` pôde ser negociada.
    Durante o pregão -> mesma sessão (intradiária); após o fechamento/feriado -> próximo dia útil; antes da abertura -> mesmo dia.
    Precisão de dia (CVM): tratada como 'após o fechamento' (conservador)."""
    li = listing_info(listing_id)
    tz = ZoneInfo(li["timezone"] or "America/Sao_Paulo")
    local = instant.astimezone(tz)
    d = local.date()
    if precision == "day":
        status = "hora não informada pela fonte — considerada após o fechamento"
        d += timedelta(days=1)
    elif local.time() < li["open_local"]:
        status = "antes da abertura"
    elif local.time() <= li["close_local"]:
        status = "durante o pregão"
    else:
        status = "após o fechamento"
        d += timedelta(days=1)
    while not is_session(li["calendar_id"], d) and (d - local.date()).days < 15:
        # sem calendário completo para anos fora de 2026: usamos as barras existentes como verdade
        if q1("SELECT 1 FROM price_bar WHERE listing_id=%s AND interval='1d' AND session_date=%s", (listing_id, d)):
            break
        d += timedelta(days=1)
    return {"session_date": d.isoformat(), "status": status, "local_time": local.isoformat(timespec="seconds"), "exchange_tz": li["timezone"]}


def events_for(instrument_id: str, listing_id: str, start: date, end: date, as_of: Optional[datetime] = None) -> List[dict]:
    """Eventos sobrepostos ao gráfico: divulgações (filings/ITR/DFP), comunicados materiais, proventos, splits, Copom/Fed (macro)."""
    ins = q1("SELECT issuer_id FROM instrument WHERE id=%s", (instrument_id,))
    out = []
    params: list = [instrument_id, ins["issuer_id"], start, end + timedelta(days=1)]
    asof_sql = ""
    if as_of:
        asof_sql = " AND n.published_at <= %s"
        params.append(as_of)
    rows = q(f"""SELECT DISTINCT n.id, n.headline, n.published_at, n.time_precision, n.kind, n.topics, n.material, n.source, n.url, n.story_id,
                        nl.relation, nl.rationale
                 FROM news_item n JOIN news_link nl ON nl.news_id=n.id
                 WHERE (nl.instrument_id=%s OR nl.issuer_id=%s) AND n.published_at BETWEEN %s AND %s AND n.material {asof_sql}
                 ORDER BY n.published_at""", params)
    for r in rows:
        fts = first_tradable_session(listing_id, r["published_at"], r["time_precision"])
        kind = "earnings" if "earnings" in r["topics"] else "dividend" if "dividends" in r["topics"] else "macro" if r["relation"] == "macro" else "news"
        out.append({"id": str(r["id"]), "type": kind, "headline": r["headline"], "published_at": r["published_at"].isoformat(),
                    "precision": r["time_precision"], "tradable_session": fts, "source": r["source"], "url": r["url"],
                    "relation": r["relation"], "rationale": r["rationale"], "story_id": str(r["story_id"]) if r["story_id"] else None})
    if ins["issuer_id"]:
        docs = q("""SELECT id, form, period_end, published_at, url, source FROM document WHERE issuer_id=%s AND form IN ('10-K','10-Q','DFP','ITR')
                    AND published_at BETWEEN %s AND %s""" + (" AND published_at <= %s" if as_of else "") + " ORDER BY published_at",
                 [ins["issuer_id"], start, end + timedelta(days=1)] + ([as_of] if as_of else []))
        for d in docs:
            prec = "day" if d["source"] == "CVM_DADOS" else "second"
            out.append({"id": str(d["id"]), "type": "filing", "headline": f"{d['form']} — período {d['period_end']}", "published_at": d["published_at"].isoformat(),
                        "precision": prec, "tradable_session": first_tradable_session(listing_id, d["published_at"], prec), "source": d["source"],
                        "url": d["url"], "relation": "direct", "document_id": str(d["id"])})
    for a in q("SELECT kind, ex_date, ratio, amount FROM corporate_action WHERE instrument_id=%s AND ex_date BETWEEN %s AND %s", (instrument_id, start, end)):
        out.append({"id": f"ca-{a['kind']}-{a['ex_date']}", "type": "split" if a["kind"] == "split" else a["kind"], "headline": f"{a['kind']} {a['ratio'] or a['amount']}",
                    "published_at": f"{a['ex_date']}T00:00:00+00:00", "precision": "day", "tradable_session": {"session_date": str(a["ex_date"]), "status": "data ex"},
                    "source": "corporate_action", "relation": "direct"})
    return sorted(out, key=lambda e: e["published_at"])
