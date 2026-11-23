"""Rotas de gráfico, estudos, eventos, notícias, rastreador, alertas, desenhos e layouts."""
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from . import config, db
from .calc import alerts as AL
from .calc import ta
from .connectors.news import NEWS_CATALOG
from .services import marketdata as MD
from .services import quotes
from .services import scan as SCAN
from .services.permissions import allowed, current_user, require

router = APIRouter()


async def _dev_delay(delay_ms: int):
    """Somente dev/test: simula resposta atrasada para provar o descarte de respostas obsoletas no cliente."""
    if delay_ms and config.ENV != "prod":
        await asyncio.sleep(min(delay_ms, 10000) / 1000)


def _f(x):
    return None if x is None else float(x)


@router.get("/api/studies")
def studies():
    return {k: {kk: vv for kk, vv in v.items() if kk != "warmup"} | {"warmup_example": v["warmup"](v["params"]) if k != "avwap" else 0}
            for k, v in ta.STUDIES.items()}


@router.get("/api/chart/{listing_id}")
async def chart(listing_id: str, interval: str = "1D", window: str = "2Y", basis: str = "adjusted", studies: str = "[]",
                bench: Optional[str] = "BOVA11", as_of: Optional[str] = None, delay_ms: int = 0, user: str = Depends(current_user)):
    await _dev_delay(delay_ms)
    li = MD.listing_info(listing_id)
    if not li:
        raise HTTPException(404, detail={"error": "not_found", "message": "listagem não encontrada"})
    asof = datetime.fromisoformat(as_of + "T23:59:59-03:00") if as_of and len(as_of) == 10 else (datetime.fromisoformat(as_of) if as_of else None)
    feed = {"daily": None, "intraday": None}
    src_name = None
    if interval in ("1m", "5m"):
        if quotes.STATE.interrupted.get("SIM_DEV"):
            feed["intraday"] = {"state": "interrupted", "label": "feed intradiário interrompido — histórico diário segue disponível"}
            raw = []
        else:
            raw = db.q("""SELECT ts, session_date, open, high, low, close, volume, fin_volume, trades, vwap, source FROM price_bar
                          WHERE listing_id=%s AND interval='1m' ORDER BY ts""", (listing_id,))
            feed["intraday"] = {"state": "ok" if raw else "unavailable", "label": "SIMULADO (dev) — barras de 1 min agregadas do feed fictício" if raw
                                else "sem cobertura intradiária licenciada para este ativo"}
        bars = raw
        if interval == "5m" and raw:
            agg = []
            for b in raw:
                k = b["ts"].replace(minute=b["ts"].minute - b["ts"].minute % 5, second=0, microsecond=0)
                if agg and agg[-1]["ts"] == k:
                    a = agg[-1]; a["high"] = max(a["high"], b["high"]); a["low"] = min(a["low"], b["low"]); a["close"] = b["close"]; a["volume"] = (a["volume"] or 0) + (b["volume"] or 0)
                else:
                    agg.append({**b, "ts": k})
            bars = agg
        adj_info = {"basis": "raw", "events_applied": [], "note": "intradiário sem ajuste"}
    else:
        raw = MD.raw_daily(listing_id, asof)
        if not raw:
            feed["daily"] = {"state": "unavailable", "label": "sem histórico diário de fonte autorizada para esta listagem (EUA: configure TIINGO_API_KEY)"}
            return {"listing": _li(li), "interval": interval, "bars": [], "feed": feed, "studies": {}, "events": [], "basis": basis}
        evs = MD.adjustment_events(li["instrument_id"])
        if basis == "adjusted":
            res = MD.adjust(raw, evs)
            bars = res["bars"]
            has_div = any(e["kind"] == "cash_dividend" for e in evs)
            adj_info = {"basis": "adjusted", "events_applied": res["events_applied"],
                        "note": ("ajuste retroativo aplicado uma única vez por desdobramento/grupamento no período" if res["events_applied"]
                                 else "nenhum desdobramento/grupamento no período (série ajustada = bruta)")
                                + ("; proventos cadastrados, não aplicados ao preço (retorno de preço, não total)" if has_div else "; proventos não carregados (retorno de preço, não total)")}
        else:
            bars, adj_info = raw, {"basis": "raw", "events_applied": [], "note": "preços como negociados"}
        bars = MD.aggregate(bars, interval)
        last = raw[-1]
        src_name = {"B3_COTAHIST": "B3 COTAHIST", "TIINGO": "Tiingo (licença do usuário)"}.get(last["source"], last["source"])
        feed["daily"] = {"state": "eod", "label": f"fim de dia — {src_name} · última sessão {last['session_date']}", "last_session": str(last["session_date"]),
                         "granularity": MD.INTERVALS.get(interval, interval)}
        feed["intraday"] = {"state": "interrupted" if quotes.STATE.interrupted.get("SIM_DEV") else "simulated",
                            "label": "feed intradiário interrompido" if quotes.STATE.interrupted.get("SIM_DEV") else "intradiário apenas SIMULADO (dev)"}
    n_vis = MD.WINDOWS.get(window, 504)
    if window == "YTD" and bars:
        y = bars[-1]["session_date"].year
        n_vis = sum(1 for b in bars if b["session_date"].year == y)
    if interval == "1W":
        n_vis = max(1, n_vis // 5)
    elif interval == "1M":
        n_vis = max(1, n_vis // 21)
    vis_from = max(0, len(bars) - n_vis)
    bench_bars = None
    req = json.loads(studies or "[]")
    if bench and any(s["id"] in ("rs", "cmp") for s in req):
        bl = db.q1("SELECT id FROM listing WHERE ticker=%s AND valid_to IS NULL", (bench,))
        bench_bars = MD.aggregate(MD.raw_daily(bl["id"], asof), interval) if bl else None
    out_studies = {}
    for s in req:
        try:
            out_studies[s.get("key") or s["id"]] = ta.compute(s["id"], s.get("params", {}), bars, bench_bars)
        except Exception as e:  # estudo inválido não derruba o gráfico
            out_studies[s.get("key") or s["id"]] = {"error": str(e)}
    events = []
    if bars and interval not in ("1m", "5m"):
        events = MD.events_for(li["instrument_id"], listing_id, bars[0]["session_date"], bars[-1]["session_date"] if not asof else asof.date(), asof)
    return {
        "listing": _li(li), "interval": interval, "window": window, "visible_from": vis_from, "warmup_policy": "estudos calculados sobre todo o histórico carregado",
        "basis": adj_info, "feed": feed, "as_of": as_of, "source": (src_name if interval not in ("1m", "5m") else "SIM_DEV") if bars else None,
        "bars": [{"t": (b["session_date"].isoformat() if interval not in ("1m", "5m") else b["ts"].isoformat()), "o": _f(b["open"]), "h": _f(b["high"]),
                  "l": _f(b["low"]), "c": _f(b["close"]), "v": _f(b.get("volume")), "fv": _f(b.get("fin_volume")), "vwap": _f(b.get("vwap")),
                  "n": b.get("trades"), "end": str(b["end_date"]) if b.get("end_date") else None} for b in bars],
        "studies": out_studies, "events": events,
        "sessions_note": f"datas sem pregão da {li['exchange_code'] or 'bolsa'} não aparecem (feriados e fins de semana não são retorno zero)",
    }


def _li(li):
    return {"id": str(li["id"]), "ticker": li["ticker"], "exchange": li["exchange_code"], "timezone": li["timezone"], "currency": li["currency"],
            "instrument_id": str(li["instrument_id"]), "name": li["name"], "kind": li["kind"]}


@router.get("/api/news")
async def news(tab: str = "top", ticker: Optional[str] = None, exchange: Optional[str] = None, as_of: Optional[str] = None, limit: int = 120,
               delay_ms: int = 0, user: str = Depends(current_user)):
    await _dev_delay(delay_ms)
    where, args = ["TRUE"], []
    if as_of:
        where.append("n.published_at <= %s"); args.append(datetime.fromisoformat(as_of + "T23:59:59-03:00") if len(as_of) == 10 else as_of)
    join = ""
    if tab in ("br", "us", "asia", "eu"):
        where.append("%s = ANY(n.region)"); args.append(tab.upper())
    elif tab == "bridge":
        join = "JOIN news_link nl ON nl.news_id=n.id"
        where.append("n.material AND (nl.relation='macro' OR ('BR' = ANY(n.region) AND 'US' = ANY(n.region)))")
    elif tab == "ticker" and ticker:
        r = db.q1("SELECT l.instrument_id, i.issuer_id FROM listing l JOIN instrument i ON i.id=l.instrument_id WHERE upper(l.ticker)=upper(%s) ORDER BY l.valid_to NULLS FIRST LIMIT 1", (ticker,))
        if not r:
            raise HTTPException(404, detail={"error": "not_found", "message": f"{ticker} não encontrado"})
        join = "JOIN news_link nl ON nl.news_id=n.id"
        where.append("(nl.instrument_id=%s OR nl.issuer_id=%s)"); args += [r["instrument_id"], r["issuer_id"]]
    elif tab == "watchlist":
        join = "JOIN news_link nl ON nl.news_id=n.id"
        where.append("""nl.instrument_id IN (SELECT wi.instrument_id FROM watchlist_item wi JOIN watchlist w ON w.id=wi.watchlist_id WHERE w.user_id=%s)""")
        args.append(user)
    elif tab == "portfolio":
        return {"tab": tab, "items": [], "note": "Carteira ainda não implementada (próxima entrega): sem posições, sem notícias de carteira.", "catalog": NEWS_CATALOG}
    order = "n.published_at DESC"
    if tab == "top":
        where.append("n.published_at >= (SELECT max(published_at) FROM news_item) - interval '7 days'")
        order = "n.material DESC, n.published_at DESC"
    rows = db.q(f"""SELECT DISTINCT n.id, n.source, n.outlet, n.distributor, n.url, n.lang, n.kind, n.headline, n.summary, n.published_at, n.time_precision,
                           n.ingested_at, n.status, n.version, n.story_id, n.region, n.topics, n.material, n.license, n.translation_allowed
                    FROM news_item n {join} WHERE {' AND '.join(where)} ORDER BY {order} LIMIT %s""", args + [limit])
    ids = [r["id"] for r in rows]
    links = {}
    for l in db.q("""SELECT nl.news_id, nl.relation, nl.rationale, l.ticker, e.code exchange FROM news_link nl
                     LEFT JOIN listing l ON l.instrument_id=nl.instrument_id AND (l.valid_to IS NULL OR l.valid_to >= CURRENT_DATE)
                     LEFT JOIN exchange e ON e.mic=l.exchange_mic WHERE nl.news_id = ANY(%s)""", (ids,)):
        links.setdefault(l["news_id"], []).append({"ticker": l["ticker"], "exchange": l["exchange"], "relation": l["relation"], "rationale": l["rationale"]})
    stories = {}
    for s in db.q("SELECT n.story_id, count(*) n, array_agg(n.source) sources FROM news_item n WHERE n.story_id = ANY(%s) GROUP BY 1",
                  ([r["story_id"] for r in rows if r["story_id"]],)):
        stories[s["story_id"]] = {"size": s["n"], "sources": sorted(set(s["sources"]))}
    items = []
    for r in rows:
        items.append({**{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r.items() if k not in ("id", "story_id")},
                      "id": str(r["id"]), "story_id": str(r["story_id"]) if r["story_id"] else None, "story": stories.get(r["story_id"]),
                      "links": [x for x in links.get(r["id"], []) if x["ticker"]],
                      "translation": None if not r["translation_allowed"] else "disponível",
                      "translation_note": "tradução indisponível: nenhum serviço de tradução autorizado configurado; exibindo o original"})
    upd = db.q1("SELECT max(finished_at) t FROM ingestion_run WHERE connector LIKE 'NEWS:%%' AND status='ok'")["t"]
    return {"tab": tab, "items": items, "catalog": NEWS_CATALOG, "as_of": as_of, "updated_at": upd.isoformat() if upd else None,
            "ordering": "cronológica (Ao Vivo)" if tab != "top" else "material primeiro, depois mais recente (últimos 3 dias da base)"}


@router.get("/api/news/{news_id}")
def news_detail(news_id: str, user: str = Depends(current_user)):
    n = db.q1("SELECT * FROM news_item WHERE id=%s", (news_id,))
    if not n:
        raise HTTPException(404)
    links = db.q("""SELECT nl.relation, nl.rationale, l.id listing_id, l.ticker, e.code exchange FROM news_link nl
                    LEFT JOIN listing l ON l.instrument_id=nl.instrument_id AND l.valid_to IS NULL LEFT JOIN exchange e ON e.mic=l.exchange_mic
                    WHERE nl.news_id=%s""", (news_id,))
    story = db.q("SELECT id, source, outlet, headline, published_at, url, lang FROM news_item WHERE story_id=%s ORDER BY published_at", (n["story_id"],)) if n["story_id"] else []
    reactions = []
    for l in links:
        if not l["listing_id"]:
            continue
        has = db.q1("SELECT 1 FROM price_bar WHERE listing_id=%s AND interval='1d' LIMIT 1", (l["listing_id"],))
        fts = MD.first_tradable_session(str(l["listing_id"]), n["published_at"], n["time_precision"]) if has else None
        bench = "BOVA11" if (l["exchange"] == "B3") else None
        reactions.append({"ticker": l["ticker"], "exchange": l["exchange"], "listing_id": str(l["listing_id"]), "relation": l["relation"], "rationale": l["rationale"],
                          "has_prices": bool(has), "tradable_session": fts, "benchmark": bench,
                          "intraday_note": "reações de 5/15/60 min não exibidas: sem barras intradiárias licenciadas (apenas diárias B3)"})
    macro = None
    if n["kind"] == "central_bank":
        macro = {"realized": None, "consensus": None, "previous": None,
                 "note": "Consenso prévio requer fonte licenciada (ex.: pesquisa Focus/Bloomberg/Reuters); não é estimado nem fabricado."}
        if n["source"] == "BCB_SGS":
            macro["realized"] = n["headline"]
    return {"item": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in n.items()}, "links": links, "story": story, "reactions": reactions, "macro": macro}


@router.get("/api/news-catalog")
def news_catalog():
    return {"catalog": NEWS_CATALOG}


@router.get("/api/events/{listing_id}")
def events(listing_id: str, start: str, end: str, as_of: Optional[str] = None, user: str = Depends(current_user)):
    li = MD.listing_info(listing_id)
    asof = datetime.fromisoformat(as_of + "T23:59:59-03:00") if as_of else None
    return {"events": MD.events_for(li["instrument_id"], listing_id, date.fromisoformat(start), date.fromisoformat(end), asof)}


@router.get("/api/scan/example")
def scan_example():
    return SCAN.EXAMPLE_BR


@router.post("/api/scan")
def scan_run(spec: dict = Body(...), user: str = Depends(current_user)):
    require(user, "B3_COTAHIST", "quotes", "view")
    return SCAN.run(spec)


@router.get("/api/scan/saved")
def scan_saved(user: str = Depends(current_user)):
    return {"queries": db.q("SELECT name, spec, updated_at FROM scan_query WHERE user_id=%s ORDER BY name", (user,))}


@router.put("/api/scan/saved/{name}")
def scan_save(name: str, spec: dict = Body(...), user: str = Depends(current_user)):
    db.q("""INSERT INTO scan_query(user_id,name,spec) VALUES (%s,%s,%s) ON CONFLICT (user_id,name) DO UPDATE SET spec=EXCLUDED.spec, updated_at=now()""",
         (user, name, json.dumps(spec)))
    return {"ok": True}


@router.get("/api/alerts")
def alerts_list(user: str = Depends(current_user)):
    rules = db.q("""SELECT a.*, l.ticker FROM alert_rule a JOIN listing l ON l.id=a.listing_id WHERE a.user_id=%s ORDER BY a.created_at DESC""", (user,))
    ev = db.q("""SELECT e.rule_id, e.bar_ts, e.fired_at, e.value FROM alert_event e JOIN alert_rule a ON a.id=e.rule_id WHERE a.user_id=%s
                 ORDER BY e.bar_ts DESC LIMIT 200""", (user,))
    return {"rules": rules, "events": ev}


@router.post("/api/alerts")
def alerts_create(body: dict = Body(...), user: str = Depends(current_user)):
    kind, params, mode, dedupe = body["kind"], body.get("params", {}), body.get("mode", "close"), body.get("dedupe", "once_per_bar")
    text = AL.describe(kind, params, mode)
    rid = db.q1("""INSERT INTO alert_rule(user_id,listing_id,kind,params,mode,dedupe,condition_text) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (user, body["listing_id"], kind, json.dumps(params), mode, dedupe, text))["id"]
    return alerts_evaluate(str(rid), user)


@router.post("/api/alerts/{rule_id}/evaluate")
def alerts_evaluate(rule_id: str, user: str = Depends(current_user)):
    r = db.q1("SELECT * FROM alert_rule WHERE id=%s AND user_id=%s", (rule_id, user))
    if not r:
        raise HTTPException(404)
    li = MD.listing_info(str(r["listing_id"]))
    bars = MD.adjust(MD.raw_daily(str(r["listing_id"])), MD.adjustment_events(li["instrument_id"]))["bars"]
    fired = {str(x["bar_ts"].astimezone(timezone.utc).date()) for x in db.q("SELECT bar_ts FROM alert_event WHERE rule_id=%s", (rule_id,))}
    hits = AL.evaluate(r["kind"], r["params"], r["mode"], r["dedupe"], bars, fired)
    with db.tx() as c:
        for h in hits:
            c.execute("INSERT INTO alert_event(rule_id,bar_ts,value) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                      (rule_id, f"{h['session_date']}T00:00:00+00:00", json.dumps(h)))
    return {"rule": {**r, "id": str(r["id"])}, "new_fires": hits, "condition": r["condition_text"], "price_basis": "ajustada (eventos cadastrados)"}


@router.delete("/api/alerts/{rule_id}")
def alerts_delete(rule_id: str, user: str = Depends(current_user)):
    db.q("DELETE FROM alert_rule WHERE id=%s AND user_id=%s", (rule_id, user))
    return {"ok": True}


@router.get("/api/drawings/{instrument_id}")
def drawings(instrument_id: str, basis: str = "adjusted", user: str = Depends(current_user)):
    rows = db.q("SELECT * FROM drawing WHERE user_id=%s AND instrument_id=%s ORDER BY updated_at", (user, instrument_id))
    out = []
    for r in rows:
        d = {**r, "id": str(r["id"])}
        if r["price_basis"] != basis:
            evs = MD.adjustment_events(str(instrument_id))
            if not [e for e in evs if e["kind"] == "split"]:
                d["reprojected"] = "sem eventos entre as bases: coordenadas idênticas"
            else:
                d["foreign_basis"] = f"desenho criado na base '{r['price_basis']}' — reprojeção por fator de split aplicada no cliente"
        out.append(d)
    return {"drawings": out}


@router.put("/api/drawings/{instrument_id}")
def drawings_save(instrument_id: str, body: dict = Body(...), user: str = Depends(current_user)):
    with db.tx() as c:
        c.execute("DELETE FROM drawing WHERE user_id=%s AND instrument_id=%s AND price_basis=%s", (user, instrument_id, body["basis"]))
        for d in body["drawings"]:
            c.execute("""INSERT INTO drawing(user_id,instrument_id,price_basis,kind,points,style,text,locked,hidden) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (user, instrument_id, body["basis"], d["kind"], json.dumps(d["points"]), json.dumps(d.get("style", {})), d.get("text"),
                       bool(d.get("locked")), bool(d.get("hidden"))))
    return drawings(instrument_id, body["basis"], user)


BUILTIN_LAYOUTS = {
    "Visão Geral": {"sizes": [20, 56, 24], "collapsed": [False, False, False], "cmd": "{T} OVERVIEW"},
    "Gráfico": {"sizes": [14, 70, 16], "collapsed": [True, False, False], "cmd": "{T} CHART 1D 2Y"},
    "Balanço": {"sizes": [18, 58, 24], "collapsed": [False, False, False], "cmd": "{T} FIN Q BS"},
    "Notícias": {"sizes": [20, 50, 30], "collapsed": [False, False, False], "cmd": "NEWS WORLD"},
    "Mesa Brasil–EUA": {"sizes": [22, 54, 24], "collapsed": [False, False, False], "cmd": "MARKETS BR US"},
}


@router.get("/api/layouts")
def layouts(user: str = Depends(current_user)):
    mine = db.q("SELECT name, state, updated_at FROM saved_layout WHERE user_id=%s ORDER BY name", (user,))
    return {"builtin": BUILTIN_LAYOUTS, "saved": mine}


@router.put("/api/layouts/{name}")
def layout_save(name: str, state: dict = Body(...), user: str = Depends(current_user)):
    db.q("""INSERT INTO saved_layout(user_id,name,state) VALUES (%s,%s,%s) ON CONFLICT (user_id,name) DO UPDATE SET state=EXCLUDED.state, updated_at=now()""",
         (user, name, json.dumps(state)))
    return {"ok": True}


@router.get("/api/value/{listing_id}")
def value(listing_id: str, user: str = Depends(current_user)):
    """Múltiplos com preço OFICIAL de fechamento (B3) e fundamentos LTM; denominadores sem significado são sinalizados."""
    from .calc import metrics as M
    from .services import research
    li = MD.listing_info(listing_id)
    ins = db.q1("SELECT issuer_id FROM instrument WHERE id=%s", (li["instrument_id"],))
    if not ins or not ins["issuer_id"]:
        raise HTTPException(422, detail={"error": "no_issuer", "message": "múltiplos exigem emissor com demonstrações"})
    px = db.q1("SELECT close, session_date FROM price_bar WHERE listing_id=%s AND interval='1d' ORDER BY session_date DESC LIMIT 1", (listing_id,))
    met = research.issuer_metrics(str(ins["issuer_id"]), "LTM", None, 1)
    last = met["periods"][-1] if met["periods"] else None
    sh_info = research.shares_outstanding(str(ins["issuer_id"]), Decimal(px["close"]) if px else None)
    sh = {"v": sh_info["value"]}
    out = {"price": {"value": str(px["close"]) if px else None, "session": str(px["session_date"]) if px else None,
                     "source": "B3 COTAHIST (fechamento oficial)" if px else "sem preço de fonte autorizada"},
           "shares": {"value": str(sh["v"]) if sh and sh["v"] else None, "convention": sh_info["note"] + " (todas as classes)"},
           "period": last["period_end"] if last else None, "multiples": {}}
    if px and last and sh and sh["v"]:
        vals = {k: (Decimal(v) if v is not None else None) for k, v in last["values"].items()}
        vals.update(price=Decimal(px["close"]), shares=Decimal(sh["v"]))
        nd = last["metrics"]["net_debt"]["value"]
        vals["net_debt"] = Decimal(nd) if nd else None
        for code in ("pe", "ev_ebit"):
            out["multiples"][code] = M.compute(code, vals)
        if vals.get("equity"):
            pb = vals["price"] * vals["shares"] / vals["equity"]
            out["multiples"]["pb"] = {"name": "P/VP", "value": str(pb), "formula": "preço × ações / PL (último balanço)", "flags": [] if vals["equity"] > 0 else ["PL ≤ 0: sem significado"]}
        out["note"] = "Mesma moeda (BRL). Preço de uma classe aplicado a todas as classes — aproximação declarada para emissores com ON e PN de preços diferentes."
    return out
