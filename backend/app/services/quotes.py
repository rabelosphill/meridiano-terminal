"""Cotações: classe do feed, estado do mercado (calendário + horário da bolsa) separado do estado do feed.

Não há contrato de bolsa nesta entrega: ações/ADRs/índices/DI/opções vêm do feed SIM_DEV (fictício,
marcado em toda a interface). USD/BRL, Brent e UST10Y vêm de fontes oficiais de fim de dia (BCB, FRED).
Em falha do provedor o último valor válido permanece, com a hora ORIGINAL da observação.
"""
import random
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from .. import config
from ..db import q, q1, tx

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

SIM_BASE = {"BOVA11": "163.60", "PETR4": "32.10", "PETR3": "35.20", "VALE3": "61.40", "AAPL": "271.30", "META": "640.00", "IBOV": "151200", "SPX": "6705",
            "DI1F27": "14.12", "AAPL261218C00250000": "26.40"}
ADR_OF = {"PBR": "PETR3", "PBR.A": "PETR4", "VALE": "VALE3"}
EOD_SERIES = {"USDBRL": ("BR.PTAX", "BCB_SGS"), "BRENT": ("GLOBAL.BRENT", "FRED"), "UST10Y": ("US.UST10Y", "FRED")}


class FeedState:
    def __init__(self):
        self.interrupted: Dict[str, bool] = {}
        self.last_ok: Dict[str, str] = {}
        self.seq = 0
        self.events: List[dict] = []
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)

    def push(self, ev: dict):
        with self.cond:
            self.seq += 1
            ev["seq"] = self.seq
            self.events.append(ev)
            self.events = self.events[-500:]
            self.cond.notify_all()


STATE = FeedState()


def market_state(exchange_code: Optional[str], now: Optional[datetime] = None) -> dict:
    if not exchange_code:
        return {"state": "n/a", "label": "OTC / sem pregão"}
    ex = q1("SELECT * FROM exchange WHERE code=%s", (exchange_code,))
    tz = ZoneInfo(ex["timezone"])
    now = (now or datetime.now(timezone.utc)).astimezone(tz)
    hol = q1("SELECT name FROM calendar_holiday WHERE calendar_id=%s AND day=%s", (ex["calendar_id"], now.date()))
    base = {"exchange": exchange_code, "local_time": now.isoformat(timespec="seconds"), "timezone": ex["timezone"],
            "session": f"{ex['open_local'].strftime('%H:%M')}–{ex['close_local'].strftime('%H:%M')} ({ex['timezone']})"}
    if hol:
        return {**base, "state": "holiday", "label": f"fechado — feriado: {hol['name']}"}
    if now.weekday() >= 5:
        return {**base, "state": "closed", "label": "fechado — fim de semana"}
    if ex["open_local"] <= now.time() <= ex["close_local"]:
        return {**base, "state": "open", "label": "aberto"}
    return {**base, "state": "closed", "label": "fechado — fora do horário"}


def _eod(code: str) -> Optional[dict]:
    return q1("""SELECT o.obs_date, o.value, o.published_at FROM macro_observation o JOIN macro_series s ON s.id=o.series_id
                 WHERE s.code=%s AND o.value IS NOT NULL ORDER BY o.obs_date DESC, o.vintage DESC LIMIT 2""", (code,))


def _eod_two(code: str) -> List[dict]:
    return q("""SELECT DISTINCT ON (o.obs_date) o.obs_date, o.value, o.published_at FROM macro_observation o JOIN macro_series s ON s.id=o.series_id
                WHERE s.code=%s AND o.value IS NOT NULL ORDER BY o.obs_date DESC, o.vintage DESC LIMIT 2""", (code,))


EOD: Dict[str, dict] = {}
EOD_PREV: Dict[str, dict] = {}
_EOD_AT = [0.0]
EOD_TTL = 600   # s — pega pregões novos gravados pela rotina diária sem reiniciar o servidor


def refresh_eod():
    """Últimos dois fechamentos diários de TODAS as listagens (fim de dia oficial: B3 COTAHIST / Tiingo)."""
    EOD.clear(); EOD_PREV.clear()
    for r in q("""SELECT ticker, close, session_date, source, rn FROM (
                    SELECT l.ticker, b.close, b.session_date, b.source,
                           row_number() OVER (PARTITION BY b.listing_id ORDER BY b.session_date DESC) rn
                    FROM price_bar b JOIN listing l ON l.id=b.listing_id
                    WHERE b.interval='1d' AND b.session_date >= CURRENT_DATE - 60 AND (l.valid_to IS NULL OR l.valid_to >= CURRENT_DATE)) t
                  WHERE rn <= 2"""):
        (EOD if r["rn"] == 1 else EOD_PREV)[r["ticker"]] = r
    _EOD_AT[0] = time.time()


def snapshot(tickers: Optional[List[str]] = None) -> List[dict]:
    if not EOD or time.time() - _EOD_AT[0] > EOD_TTL:
        refresh_eod()
    rows = q("""SELECT l.id, l.ticker, l.currency, e.code exchange, i.kind, i.name, i.id instrument_id, ql.price, ql.prev_close, ql.observed_at,
                       ql.received_at, ql.source, ql.feed_class
                FROM listing l JOIN instrument i ON i.id=l.instrument_id LEFT JOIN exchange e ON e.mic=l.exchange_mic
                LEFT JOIN quote_last ql ON ql.listing_id=l.id
                WHERE l.valid_to IS NULL OR l.valid_to >= CURRENT_DATE""")
    out = []
    now = datetime.now(timezone.utc)
    for r in rows:
        if tickers and r["ticker"] not in tickers:
            continue
        item = {"listing_id": str(r["id"]), "instrument_id": str(r["instrument_id"]), "ticker": r["ticker"], "exchange": r["exchange"],
                "kind": r["kind"], "name": r["name"], "currency": r["currency"], "market": market_state(r["exchange"], now)}
        if r["ticker"] in EOD_SERIES:
            code, src = EOD_SERIES[r["ticker"]]
            two = _eod_two(code)
            if two:
                item.update(price=str(two[0]["value"]), prev_close=str(two[1]["value"]) if len(two) > 1 else None,
                            observed_at=str(two[0]["obs_date"]), source=src, feed_class="eod",
                            feed_state="eod", feed_label=f"fim de dia — {src} · ref. {two[0]['obs_date']}")
            else:
                item.update(price=None, feed_class="unavailable", feed_state="unavailable", feed_label="sem dado")
        elif r["price"] is not None:
            src = r["source"]
            interrupted = STATE.interrupted.get(src, False)
            age = (now - r["observed_at"]).total_seconds()
            if interrupted:
                fs, fl = "interrupted", f"feed interrompido — último valor válido de {r['observed_at'].isoformat(timespec='seconds')}"
            elif age > config.QUOTE_STALE_SECONDS and (item["market"]["state"] == "open" or config.SIM_IGNORE_HOURS):
                fs, fl = "stale", f"sem atualização há {int(age)} s"
            else:
                fs, fl = "ok", "simulado (dev) — não é dado de mercado" if r["feed_class"] == "simulated" else r["feed_class"]
            item.update(price=str(r["price"]), prev_close=str(r["prev_close"]) if r["prev_close"] is not None else None,
                        observed_at=r["observed_at"].isoformat(timespec="milliseconds"), source=src, feed_class=r["feed_class"],
                        feed_state=fs, feed_label=fl)
        elif r["ticker"] in EOD:
            # sem feed em tempo real: mostra o último fechamento oficial (fim de dia), nunca como se fosse tempo real
            e, pv = EOD[r["ticker"]], EOD_PREV.get(r["ticker"])
            src = "B3 COTAHIST" if e["source"] == "B3_COTAHIST" else "Tiingo"
            item.update(price=str(e["close"]), prev_close=str(pv["close"]) if pv else None, observed_at=str(e["session_date"]),
                        source=e["source"], feed_class="eod", feed_state="eod",
                        feed_label=f"fim de dia — {src} · pregão {e['session_date']:%d/%m/%Y} (sem feed em tempo real)")
        else:
            item.update(price=None, feed_class="unavailable", feed_state="unavailable",
                        feed_label="indisponível — requer contrato com a bolsa/vendor")
        eod = EOD.get(item["ticker"])
        if eod:
            item["official_close"] = {"price": str(eod["close"]), "session_date": str(eod["session_date"]), "source": "B3 COTAHIST (fim de dia, oficial)" if eod["source"] == "B3_COTAHIST" else "Tiingo (fim de dia, licença do usuário)"}
            if item.get("feed_class") == "simulated":
                item["prev_close"] = str(eod["close"])   # variação do simulado medida contra o último fechamento oficial
        if item.get("price") and item.get("prev_close"):
            p, pc = Decimal(item["price"]), Decimal(item["prev_close"])
            item["change"] = str(p - pc)
            item["change_pct"] = str((p / pc - 1) * 100) if pc else None
        out.append(item)
    return out


def write_quote(listing_id: str, price: Decimal, prev: Optional[Decimal], source: str, feed_class: str, observed_at: Optional[datetime] = None):
    now = datetime.now(timezone.utc)
    with tx() as c:
        c.execute("""INSERT INTO quote_last(listing_id,price,prev_close,observed_at,received_at,source,feed_class) VALUES (%s,%s,%s,%s,%s,%s,%s)
                     ON CONFLICT (listing_id) DO UPDATE SET price=EXCLUDED.price, prev_close=COALESCE(EXCLUDED.prev_close, quote_last.prev_close),
                     observed_at=EXCLUDED.observed_at, received_at=EXCLUDED.received_at, source=EXCLUDED.source, feed_class=EXCLUDED.feed_class""",
                  (listing_id, price, prev, observed_at or now, now, source, feed_class))


class SimFeed(threading.Thread):
    """Feed fictício de desenvolvimento. ADRs derivam do local × razão ÷ PTAX (com ruído), para exercitar a paridade."""

    daemon = True

    def __init__(self, interval: float = 1.5):
        super().__init__(name="sim-feed")
        self.interval = interval
        self.stop_flag = False

    def run(self):
        listings = {r["ticker"]: r for r in q("SELECT l.id, l.ticker FROM listing l WHERE l.valid_to IS NULL OR l.valid_to >= CURRENT_DATE")}
        px = {t: Decimal(v) for t, v in SIM_BASE.items() if t in listings}
        # ancora a simulação no último fechamento OFICIAL quando existir (B3 COTAHIST) — continua rotulada SIMULADO
        for r in q("""SELECT DISTINCT ON (l.ticker) l.ticker, b.close FROM price_bar b JOIN listing l ON l.id=b.listing_id
                      WHERE b.interval='1d' AND l.ticker = ANY(%s) ORDER BY l.ticker, b.session_date DESC""", (list(px),)):
            px[r["ticker"]] = Decimal(r["close"])
        prev = dict(px)
        ptax = _eod("BR.PTAX")
        fx = Decimal(str(ptax["value"])) if ptax else Decimal("5.80")
        adr = {r["ticker"]: r for r in q("""SELECT la.ticker, a.adr_units, a.underlying_units FROM adr_terms a
                                             JOIN listing la ON la.instrument_id=a.adr_id""")}
        for t in list(px) + list(ADR_OF):
            if t in listings:
                p = px.get(t) or self._adr(t, px, adr, fx)
                write_quote(listings[t]["id"], p, prev.get(t, p), "SIM_DEV", "simulated")
        while not self.stop_flag:
            time.sleep(self.interval)
            if STATE.interrupted.get("SIM_DEV"):
                continue
            moved = random.sample(list(px), k=min(3, len(px)))
            for t in moved:
                step = Decimal(str(random.gauss(0, 0.0015)))
                px[t] = (px[t] * (1 + step)).quantize(Decimal("0.01"))
                write_quote(listings[t]["id"], px[t], None, "SIM_DEV", "simulated")
                write_minute_bar(listings[t]["id"], px[t], random.randint(100, 5000))
                STATE.push({"type": "quote", "ticker": t, "price": str(px[t]), "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")})
            for a, u in ADR_OF.items():
                if u in moved and a in listings:
                    p = self._adr(a, px, adr, fx)
                    write_quote(listings[a]["id"], p, None, "SIM_DEV", "simulated")
                    STATE.push({"type": "quote", "ticker": a, "price": str(p), "at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")})

    @staticmethod
    def _adr(t, px, adr, fx):
        terms = adr[t]
        local = px[ADR_OF[t]]
        noise = Decimal(str(1 + random.gauss(0, 0.002)))
        return (local * Decimal(terms["underlying_units"]) / Decimal(terms["adr_units"]) / fx * noise).quantize(Decimal("0.01"))


def write_minute_bar(listing_id, price: Decimal, vol: int):
    """Agrega ticks simulados em barras de 1 minuto (interval='1m', source=SIM_DEV)."""
    now = datetime.now(timezone.utc)
    ts = now.replace(second=0, microsecond=0)
    with tx() as c:
        c.execute("""INSERT INTO price_bar(listing_id,interval,ts,session_date,open,high,low,close,volume,source,location)
                     VALUES (%s,'1m',%s,%s,%s,%s,%s,%s,%s,'SIM_DEV','{"simulated": true}')
                     ON CONFLICT (listing_id,interval,ts,source) DO UPDATE SET high=GREATEST(price_bar.high,EXCLUDED.close),
                       low=LEAST(price_bar.low,EXCLUDED.close), close=EXCLUDED.close, volume=price_bar.volume+EXCLUDED.volume""",
                  (listing_id, ts, ts.astimezone(ZoneInfo("America/Sao_Paulo")).date(), price, price, price, price, vol))


def interrupt(source: str, on: bool):
    STATE.interrupted[source] = on
    STATE.push({"type": "feed", "source": source, "state": "interrupted" if on else "restored", "at": datetime.now(timezone.utc).isoformat()})
