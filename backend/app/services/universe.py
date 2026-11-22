"""Resolução e busca no universo. Ticker é chave de busca; a chave persistente é o UUID do instrumento."""
import unicodedata
from datetime import date
from typing import List, Optional

from ..db import q, q1


def norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).upper()


def search_index() -> List[dict]:
    """Índice compacto enviado ao cliente para sugestões locais (inclui tickers históricos)."""
    rows = q("""SELECT l.id listing_id, l.ticker, l.valid_from, l.valid_to, l.status listing_status, e.code exchange, l.currency,
                       i.id instrument_id, i.kind, i.class_name, i.name instrument_name,
                       iss.id issuer_id, iss.short_name, iss.name issuer_name, le.name entity_name, le.country,
                       (SELECT array_agg(value) FROM identifier x WHERE x.object_id IN (i.id, iss.id)) ids
                FROM listing l JOIN instrument i ON i.id=l.instrument_id
                LEFT JOIN exchange e ON e.mic=l.exchange_mic LEFT JOIN issuer iss ON iss.id=i.issuer_id
                LEFT JOIN legal_entity le ON le.id=iss.legal_entity_id ORDER BY l.ticker""")
    out = []
    for r in rows:
        out.append({
            "listing_id": str(r["listing_id"]), "instrument_id": str(r["instrument_id"]), "issuer_id": str(r["issuer_id"]) if r["issuer_id"] else None,
            "ticker": r["ticker"], "exchange": r["exchange"], "currency": r["currency"], "kind": r["kind"], "class": r["class_name"],
            "name": r["instrument_name"], "issuer": r["short_name"], "entity": r["entity_name"], "country": r["country"],
            "active": r["valid_to"] is None or r["valid_to"] >= date.today(), "valid_from": str(r["valid_from"]), "valid_to": str(r["valid_to"]) if r["valid_to"] else None,
            "status": r["listing_status"],
            "terms": norm(" ".join(filter(None, [r["ticker"], r["instrument_name"], r["short_name"], r["issuer_name"], r["entity_name"]] + (r["ids"] or [])))),
        })
    return out


def find(query: str, limit: int = 30) -> dict:
    qn = norm(query)
    toks = qn.split()
    idx = search_index()
    hits = [r for r in idx if all(t in r["terms"] for t in toks)]

    def score(r):
        s = 0
        if r["ticker"].upper() == qn:
            s += 100
        if r["ticker"].upper().startswith(qn):
            s += 30
        if r["active"]:
            s += 10
        if r["kind"] in ("equity_common", "equity_pref", "equity_unit", "adr"):
            s += 25                      # ações antes de fundos/ETFs
        if r["issuer_id"]:
            s += 5
        if norm(r.get("issuer") or "").startswith(qn):
            s += 15
        return (-s, len(r["ticker"]), r["ticker"])
    hits.sort(key=score)
    companies = {}
    for h in hits:
        if h["issuer_id"]:
            companies.setdefault(h["issuer_id"], {"issuer_id": h["issuer_id"], "name": h["entity"], "country": h["country"], "listings": []})["listings"].append(h)
    instruments = {}
    for h in hits:
        instruments.setdefault(h["instrument_id"], {"instrument_id": h["instrument_id"], "name": h["name"], "kind": h["kind"], "class": h["class"], "listings": []})["listings"].append(h)
    return {"query": query, "companies": list(companies.values()), "instruments": list(instruments.values()), "listings": hits[:limit]}


def resolve(ticker: str, exchange: Optional[str] = None, on: Optional[date] = None) -> Optional[dict]:
    """Resolve ticker(+bolsa) na data `on` (padrão hoje). Tickers antigos resolvem para o mesmo instrumento."""
    on = on or date.today()
    rows = q("""SELECT l.*, e.code exchange_code, e.timezone, e.open_local, e.close_local, e.calendar_id, e.name exchange_name
                FROM listing l LEFT JOIN exchange e ON e.mic=l.exchange_mic WHERE upper(l.ticker)=upper(%s)
                AND (%s::text IS NULL OR upper(e.code)=upper(%s) OR upper(l.exchange_mic)=upper(%s))
                ORDER BY (l.valid_to IS NULL) DESC, l.valid_from DESC""", (ticker, exchange, exchange, exchange))
    if not rows:
        return None
    l = rows[0]
    current = q1("""SELECT l.ticker, e.code exchange_code FROM listing l LEFT JOIN exchange e ON e.mic=l.exchange_mic
                    WHERE l.instrument_id=%s AND l.valid_to IS NULL ORDER BY l.valid_from DESC LIMIT 1""", (l["instrument_id"],))
    return {"listing": l, "renamed_to": current if current and current["ticker"] != l["ticker"] else None, **instrument_context(l["instrument_id"], l["id"])}


def instrument_context(instrument_id, listing_id=None) -> dict:
    ins = q1("SELECT * FROM instrument WHERE id=%s", (instrument_id,))
    issuer = q1("""SELECT iss.*, le.name entity_name, le.country, le.tax_id FROM issuer iss JOIN legal_entity le ON le.id=iss.legal_entity_id
                   WHERE iss.id=%s""", (ins["issuer_id"],)) if ins["issuer_id"] else None
    listings = q("""SELECT l.id, l.ticker, l.valid_from, l.valid_to, l.status, l.currency, e.code exchange, e.timezone, i.kind, i.class_name
                    FROM listing l JOIN instrument i ON i.id=l.instrument_id LEFT JOIN exchange e ON e.mic=l.exchange_mic
                    WHERE i.issuer_id=%s OR i.id=%s ORDER BY i.kind, l.valid_from""", (ins["issuer_id"], instrument_id))
    adr = q("""SELECT a.*, ia.name adr_name, iu.name underlying_name FROM adr_terms a JOIN instrument ia ON ia.id=a.adr_id
               JOIN instrument iu ON iu.id=a.underlying_id WHERE a.adr_id=%s OR a.underlying_id=%s
               OR a.underlying_id IN (SELECT id FROM instrument WHERE issuer_id=%s)""", (instrument_id, instrument_id, ins["issuer_id"]))
    ids = q("SELECT scheme, value, source FROM identifier WHERE object_id IN (%s, %s)", (instrument_id, ins["issuer_id"] or instrument_id))
    actions = q("SELECT kind, ex_date, ratio, amount, currency, detail FROM corporate_action WHERE instrument_id=%s ORDER BY ex_date", (instrument_id,))
    coverage = None
    if issuer:
        coverage = q("""SELECT source, statement, count(*) n, min(period_end) first, max(period_end) last, max(published_at) last_published
                        FROM fact WHERE issuer_id=%s GROUP BY 1,2""", (issuer["id"],))
    return {"instrument": ins, "issuer": issuer, "listings": listings, "adr_terms": adr, "identifiers": ids, "corporate_actions": actions,
            "coverage": coverage}
