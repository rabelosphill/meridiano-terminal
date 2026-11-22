"""API HTTP do terminal. Autenticação de dev via cabeçalho X-User (ver permissions.current_user)."""
import asyncio
import csv
import io
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import commands, config, db, seed
from .calc import dcf as DCF
from .services import lineage, quotes, research, statements, universe
from .services.permissions import allowed, audit, current_user, require


def _json_default(o):
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (datetime,)):
        return o.isoformat()
    return str(o)


class J(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, default=_json_default, ensure_ascii=False).encode("utf-8")


app = FastAPI(title="Meridiano Terminal API", default_response_class=J)
from .api_markets import router as markets_router  # noqa: E402
app.include_router(markets_router)
_sim: Optional[quotes.SimFeed] = None
_cache: dict = {}
CACHE_TTL = 300


def cached(key, fn):
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    val = fn()
    _cache[key] = (time.monotonic(), val)
    return val


@app.on_event("startup")
def startup():
    global _sim
    db.migrate()
    seed.seed()
    if config.SIM_FEED and _sim is None:
        _sim = quotes.SimFeed()
        _sim.start()


def _as_of(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    if len(v) == 10:  # data: fim do dia em UTC-3 (inclui tudo publicado até D)
        return datetime.fromisoformat(v + "T23:59:59-03:00")
    return datetime.fromisoformat(v)


def _issuer(issuer_id: str) -> dict:
    iss = db.q1("SELECT * FROM issuer WHERE id=%s", (issuer_id,))
    if not iss:
        raise HTTPException(404, detail={"error": "not_found", "message": "emissor não encontrado"})
    return iss


def _fund_source(iss: dict) -> str:
    return "SEC_EDGAR" if iss["reporting_std"] == "US-GAAP" else "CVM_DADOS"


@app.get("/api/health")
def health():
    return {"ok": True, "env": config.ENV, "data_mode": config.DATA_MODE, "sim_feed": config.SIM_FEED,
            "db": db.q1("SELECT version() v")["v"].split(",")[0], "now": datetime.now(timezone.utc).isoformat()}


@app.get("/api/me")
def me(user: str = Depends(current_user)):
    u = db.q1("SELECT * FROM app_user WHERE id=%s", (user,))
    return {**u, "entitlements": db.q("SELECT feed, field, can_view, can_export FROM entitlement WHERE user_id=%s", (user,)),
            "users": db.q("SELECT id, name, role FROM app_user ORDER BY id")}


@app.get("/api/commands")
def get_commands():
    return {"commands": commands.catalog(), "fields": _field_catalog()}


def _field_catalog():
    from .services.templates import SEC_TEMPLATE, CVM_STANDARD
    from .calc.metrics import METRICS
    out = [{"code": ln["key"], "label": ln["label"], "en": ln["en"], "statement": st, "kind": "field",
            "sec_tags": ln["tags"], "cvm": CVM_STANDARD.get(ln["key"])} for st, lines in SEC_TEMPLATE.items() for ln in lines if not ln.get("hidden")]
    out += [{"code": m.code, "label": m.name, "formula": m.formula, "unit": m.unit, "kind": "metric", "convention": m.convention, "version": m.version}
            for m in METRICS.values()]
    return out


@app.post("/api/command/parse")
def parse(body: dict = Body(...)):
    return commands.parse(body.get("text", ""))


@app.get("/api/search/index")
def search_index():
    return cached("search_index", universe.search_index)


@app.get("/api/find")
def find(q: str):
    return universe.find(q)


@app.get("/api/instruments/{instrument_id}/overview")
def overview(instrument_id: str, user: str = Depends(current_user)):
    ctx = universe.instrument_context(instrument_id)
    listing_tickers = [l["ticker"] for l in ctx["listings"]]
    qs = _filter_quotes(quotes.snapshot(listing_tickers + ["USDBRL"]), user)
    adr = []
    by_t = {x["ticker"]: x for x in qs}
    fx = by_t.get("USDBRL")
    for a in ctx["adr_terms"]:
        la = db.q1("SELECT ticker FROM listing WHERE instrument_id=%s AND valid_to IS NULL", (a["adr_id"],))
        lu = db.q1("SELECT ticker FROM listing WHERE instrument_id=%s AND valid_to IS NULL", (a["underlying_id"],))
        qa, qu = by_t.get(la["ticker"]), by_t.get(lu["ticker"])
        item = {"adr": la["ticker"], "underlying": lu["ticker"], "ratio": f"{a['adr_units']} ADS = {a['underlying_units']} {lu['ticker']}",
                "valid_from": str(a["valid_from"]), "source": a["source"]}
        if qa and qu and fx and qa.get("price") and qu.get("price") and fx.get("price"):
            from .calc.returns import AdrTerms, FxQuote, adr_implied_price, adr_premium
            implied = adr_implied_price(Decimal(qu["price"]), "BRL", AdrTerms(Decimal(a["adr_units"]), Decimal(a["underlying_units"]), "BRL"),
                                        FxQuote("USD", "BRL", Decimal(fx["price"])))
            item.update(local_price=qu["price"], local_time=qu.get("observed_at"), local_market=qu["market"], adr_price=qa["price"], adr_time=qa.get("observed_at"),
                        adr_market=qa["market"], fx=fx["price"], fx_ref=fx.get("observed_at"), fx_source="BCB PTAX venda (fim de dia)",
                        implied=str(implied.quantize(Decimal("0.0001"))), premium_pct=str((adr_premium(Decimal(qa["price"]), implied) * 100).quantize(Decimal("0.01"))),
                        convention="implícito = preço local × ações por ADS ÷ USD/BRL (BRL por USD)",
                        warning="Preços locais/ADR do feed SIMULADO; câmbio real (PTAX) de fim de dia — horários diferentes." )
        adr.append(item)
    return {**ctx, "quotes": qs, "adr_parity": adr, "tabs": research.tabs(ctx), "sector_pack": research.sector_pack(ctx["issuer"])}


@app.get("/api/issuers/{issuer_id}/statements")
def get_statement(issuer_id: str, statement: str = "IS", freq: str = "A", scope: str = "consolidated",
                  as_of: Optional[str] = None, view: str = "latest", user: str = Depends(current_user)):
    iss = _issuer(issuer_id)
    require(user, _fund_source(iss), "fundamentals", "view", {"issuer": issuer_id})
    if statement not in ("IS", "BS", "CF") or freq not in ("A", "Q", "LTM") or view not in ("latest", "original"):
        raise HTTPException(400, detail={"error": "bad_request", "message": "parâmetros inválidos"})
    t0 = time.perf_counter()
    res = cached(("st", issuer_id, statement, freq, scope, as_of, view),
                 lambda: statements.build(iss, statement, freq, scope, _as_of(as_of), view))
    return {**res, "server_ms": round((time.perf_counter() - t0) * 1000, 2)}


@app.get("/api/facts/{fact_id}")
def fact(fact_id: int, user: str = Depends(current_user)):
    L = lineage.fact_lineage(fact_id)
    if not L:
        raise HTTPException(404)
    require(user, L["source"]["code"], "fundamentals", "view", {"fact": fact_id})
    return L


@app.get("/api/facts/{fact_id}/reconcile")
def reconcile(fact_id: int, user: str = Depends(current_user)):
    fact(fact_id, user)
    return lineage.reconcile_fact(fact_id)


@app.get("/api/facts/{fact_id}/source", response_class=HTMLResponse)
def fact_source(fact_id: int, user: str = Depends(current_user)):
    L = fact(fact_id, user)
    if L["source"]["code"] == "CVM_DADOS":
        return HTMLResponse(lineage.render_cvm_rows(fact_id))
    if L["document"]["id"] and L["document"]["stored_copy"] and L["location"].get("ix_ids"):
        page = lineage.render_document(L["document"]["id"], L["location"]["ix_ids"])
        if page:
            return HTMLResponse(page, headers={"Content-Security-Policy": "script-src 'unsafe-inline'; default-src 'self' 'unsafe-inline' data:"})
    return HTMLResponse(f"""<!doctype html><meta charset=utf-8><body style="background:#0b0f14;color:#c8d3df;font:13px system-ui;padding:16px">
      Documento original não armazenado localmente para este fato. <a style="color:#ffb000" href="{L['document']['url']}" target=_blank rel=noopener>Abrir na SEC</a>
      <script>document.addEventListener('keydown',e=>{{if(e.key==='Escape')parent.postMessage({{ft:'doc-esc'}},'*')}});</script>""")


@app.get("/api/issuers/{issuer_id}/documents")
def documents(issuer_id: str, user: str = Depends(current_user)):
    iss = _issuer(issuer_id)
    require(user, _fund_source(iss), "documents", "view")
    return {"documents": db.q("""SELECT d.id, d.source, d.external_id, d.form, d.period_end, d.version, d.published_at, d.url,
                                        d.object_key IS NOT NULL stored, (SELECT count(*) FROM fact f WHERE f.document_id=d.id) n_facts,
                                        d.meta->>'published_precision' precision
                                 FROM document d WHERE d.issuer_id=%s ORDER BY d.published_at DESC""", (issuer_id,))}


@app.get("/api/documents/{doc_id}/view", response_class=HTMLResponse)
def doc_view(doc_id: str, h: str = "", user: str = Depends(current_user)):
    page = lineage.render_document(doc_id, [x for x in h.split(",") if x])
    if not page:
        raise HTTPException(404, detail={"error": "not_stored", "message": "cópia do documento não armazenada"})
    return HTMLResponse(page)


@app.get("/api/issuers/{issuer_id}/metrics")
def metrics(issuer_id: str, freq: str = "A", as_of: Optional[str] = None, user: str = Depends(current_user)):
    iss = _issuer(issuer_id)
    require(user, _fund_source(iss), "fundamentals", "view")
    return cached(("met", issuer_id, freq, as_of), lambda: research.issuer_metrics(issuer_id, freq, _as_of(as_of)))


@app.post("/api/compare")
def compare(body: dict = Body(...), user: str = Depends(current_user)):
    for it in body["instruments"]:
        require(user, _fund_source(_issuer(it["issuer_id"])), "fundamentals", "view")
    return research.compare(body["instruments"], body.get("ccy", "NATIVE"), body.get("freq", "A"), _as_of(body.get("as_of")))


@app.get("/api/macro/{code}")
def macro(code: str, as_of: Optional[str] = None, limit: int = 400, user: str = Depends(current_user)):
    s = research.macro_series(code.upper(), _as_of(as_of), limit)
    if not s:
        raise HTTPException(404, detail={"error": "not_found", "message": f"série {code} não cadastrada",
                                         "suggestions": [f"MACRO {x['code'].replace('.', ' ')}" for x in db.q("SELECT code FROM macro_series")]})
    require(user, s["source"], "macro", "view")
    return s


def _filter_quotes(items: List[dict], user: str) -> List[dict]:
    out = []
    for it in items:
        if it.get("source") and not allowed(user, it["source"], "quotes", "view"):
            it = {k: v for k, v in it.items() if k not in ("price", "prev_close", "change", "change_pct")}
            it.update(feed_state="no_permission", feed_label="sem permissão para este feed")
        out.append(it)
    return out


@app.get("/api/quotes")
def get_quotes(tickers: Optional[str] = None, user: str = Depends(current_user)):
    return {"quotes": _filter_quotes(quotes.snapshot(tickers.split(",") if tickers else None), user),
            "feeds": feeds(), "server_time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/feeds")
def feeds():
    rows = db.q("SELECT code, name, feed_class, delay_note, license FROM source")
    last = {r["source"]: r["t"] for r in db.q("SELECT source, max(observed_at) t FROM quote_last GROUP BY source")}
    runs = {r["connector"].split(":")[0]: r for r in db.q("""SELECT DISTINCT ON (split_part(connector,':',1)) connector, mode, status, finished_at
                                                              FROM ingestion_run ORDER BY split_part(connector,':',1), id DESC""")}
    return [{**r, "interrupted": quotes.STATE.interrupted.get(r["code"], False), "last_observation": last.get(r["code"]),
             "last_ingestion": runs.get(r["code"])} for r in rows]


@app.post("/api/admin/feeds/{source}/interrupt")
def interrupt(source: str, body: dict = Body(...), user: str = Depends(current_user)):
    if db.q1("SELECT role FROM app_user WHERE id=%s", (user,))["role"] not in ("admin", "analyst", "pm"):
        raise HTTPException(403)
    quotes.interrupt(source, bool(body.get("on", True)))
    return {"source": source, "interrupted": quotes.STATE.interrupted[source]}


@app.get("/api/stream")
async def stream(request: Request, since: int = 0):
    async def gen():
        last = since
        while True:
            if await request.is_disconnected():
                return
            evs = [e for e in quotes.STATE.events if e["seq"] > last]
            for e in evs:
                last = e["seq"]
                yield f"id: {e['seq']}\ndata: {json.dumps(e)}\n\n"
            if not evs:
                yield ": keepalive\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


DEFAULT_WATCH = ["PETR4", "PETR3", "VALE3", "PBR", "PBR.A", "VALE", "AAPL", "IBOV", "SPX", "USDBRL", "BRENT", "UST10Y", "DI1F27"]


@app.get("/api/watchlists/{name}")
def watchlist(name: str, user: str = Depends(current_user)):
    name = name.upper()
    with db.tx() as c:
        w = c.execute("SELECT * FROM watchlist WHERE user_id=%s AND name=%s", (user, name)).fetchone()
        if not w:
            w = c.execute("INSERT INTO watchlist(user_id,name) VALUES (%s,%s) RETURNING *", (user, name)).fetchone()
            for i, t in enumerate(DEFAULT_WATCH):
                l = c.execute("SELECT id, instrument_id FROM listing WHERE ticker=%s AND valid_to IS NULL OR (ticker=%s AND valid_to >= CURRENT_DATE)", (t, t)).fetchone()
                if l:
                    c.execute("INSERT INTO watchlist_item VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (w["id"], l["instrument_id"], l["id"], i))
        items = c.execute("""SELECT wi.position, l.ticker FROM watchlist_item wi JOIN listing l ON l.id=wi.listing_id
                             WHERE wi.watchlist_id=%s ORDER BY wi.position""", (w["id"],)).fetchall()
    tick = [i["ticker"] for i in items]
    qs = {x["ticker"]: x for x in _filter_quotes(quotes.snapshot(tick), user)}
    return {"name": name, "id": str(w["id"]), "items": [qs[t] for t in tick if t in qs]}


@app.post("/api/watchlists/{name}")
def watchlist_edit(name: str, body: dict = Body(...), user: str = Depends(current_user)):
    w = watchlist(name, user)
    with db.tx() as c:
        for t in body.get("add", []):
            tk, _, ex = t.partition(":")
            r = universe.resolve(tk, commands.EXCH_ALIASES.get(ex, ex) if ex else None)
            if not r:
                raise HTTPException(404, detail={"error": "not_found", "message": f"{t} não encontrado"})
            pos = c.execute("SELECT coalesce(max(position),0)+1 p FROM watchlist_item WHERE watchlist_id=%s", (w["id"],)).fetchone()["p"]
            c.execute("INSERT INTO watchlist_item VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING", (w["id"], r["instrument"]["id"], r["listing"]["id"], pos))
        for t in body.get("remove", []):
            c.execute("DELETE FROM watchlist_item wi USING listing l WHERE wi.listing_id=l.id AND wi.watchlist_id=%s AND l.ticker=%s", (w["id"], t.split(":")[0]))
    return watchlist(name, user)


@app.get("/api/thesis/{instrument_id}")
def thesis_get(instrument_id: str, user: str = Depends(current_user)):
    t = db.q1("SELECT * FROM thesis WHERE user_id=%s AND instrument_id=%s", (user, instrument_id))
    if not t:
        return {"thesis": None, "versions": []}
    vs = db.q("SELECT * FROM thesis_version WHERE thesis_id=%s ORDER BY version DESC", (t["id"],))
    return {"thesis": t, "versions": vs}


@app.post("/api/thesis/{instrument_id}")
def thesis_save(instrument_id: str, body: dict = Body(...), user: str = Depends(current_user)):
    with db.tx() as c:
        t = c.execute("SELECT * FROM thesis WHERE user_id=%s AND instrument_id=%s", (user, instrument_id)).fetchone()
        if not t:
            t = c.execute("INSERT INTO thesis(user_id,instrument_id,title,stance) VALUES (%s,%s,%s,%s) RETURNING *",
                          (user, instrument_id, body.get("title") or "Tese", body.get("stance", "neutral"))).fetchone()
        else:
            c.execute("UPDATE thesis SET title=%s, stance=%s WHERE id=%s", (body.get("title") or t["title"], body.get("stance", t["stance"]), t["id"]))
        v = c.execute("SELECT coalesce(max(version),0)+1 v FROM thesis_version WHERE thesis_id=%s", (t["id"],)).fetchone()["v"]
        dcf_payload = None
        if body.get("dcf_inputs"):
            inp = DCF.inputs_from_json(body["dcf_inputs"])
            dcf_payload = {"inputs": DCF.inputs_to_json(inp), "result": DCF.run(inp), "library_version": DCF.LIB_VERSION}
        c.execute("""INSERT INTO thesis_version(thesis_id,version,author,body,assumptions,dcf,context) VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                  (t["id"], v, user, body.get("body", ""), json.dumps(body.get("assumptions", [])), json.dumps(dcf_payload) if dcf_payload else None,
                   json.dumps(body.get("context", {}))))
    return thesis_get(instrument_id, user)


@app.get("/api/dcf/defaults/{issuer_id}")
def dcf_defaults(issuer_id: str, user: str = Depends(current_user)):
    require(user, _fund_source(_issuer(issuer_id)), "fundamentals", "view")
    return research.dcf_defaults(issuer_id)


@app.post("/api/dcf/run")
def dcf_run(body: dict = Body(...)):
    try:
        inp = DCF.inputs_from_json(body["inputs"])
        res = DCF.run(inp)
        w, g = inp.wacc, inp.g
        step = Decimal("0.01")
        sens = DCF.sensitivity(inp, [w + step * k for k in (-2, -1, 0, 1, 2)], [g + Decimal("0.005") * k for k in (-2, -1, 0, 1, 2)])
        sc = DCF.scenarios(inp)
        rev = DCF.reverse(inp, Decimal(str(body["target_price"]))) if body.get("target_price") else None
    except DCF.DcfError as e:
        raise HTTPException(422, detail={"error": "dcf_invalid", "message": str(e)})
    return {"result": res, "sensitivity": sens, "scenarios": sc, "reverse": rev}


@app.get("/api/state/{workspace}/{key:path}")
def state_get(workspace: str, key: str, user: str = Depends(current_user)):
    r = db.q1("SELECT state, updated_at FROM workspace_state WHERE user_id=%s AND workspace=%s AND scope_key=%s", (user, workspace, key))
    return r or {"state": None}


@app.put("/api/state/{workspace}/{key:path}")
def state_put(workspace: str, key: str, body: dict = Body(...), user: str = Depends(current_user)):
    db.q("""INSERT INTO workspace_state(user_id,workspace,scope_key,state) VALUES (%s,%s,%s,%s)
            ON CONFLICT (user_id,workspace,scope_key) DO UPDATE SET state=EXCLUDED.state, updated_at=now()""",
         (user, workspace, key, json.dumps(body)))
    return {"ok": True}


@app.get("/api/peers/{instrument_id}")
def peers_get(instrument_id: str, user: str = Depends(current_user)):
    r = db.q1("SELECT members FROM peer_group WHERE user_id=%s AND instrument_id=%s", (user, instrument_id))
    ins = db.q1("SELECT i.*, iss.sector_pack FROM instrument i LEFT JOIN issuer iss ON iss.id=i.issuer_id WHERE i.id=%s", (instrument_id,))
    if r:
        members, origin = r["members"], "editado pelo usuário"
    else:
        members = [x["id"] for x in db.q("""SELECT i.id FROM instrument i JOIN issuer iss ON iss.id=i.issuer_id
                                            WHERE i.id<>%s AND i.kind IN ('equity_common','equity_pref') AND iss.id<>%s""",
                                         (instrument_id, ins["issuer_id"]))]
        origin = "padrão: emissores com fundamentos carregados (edite para ajustar)"
    rows = db.q("""SELECT i.id, i.name, l.ticker, e.code exchange, iss.sector_pack FROM instrument i JOIN listing l ON l.instrument_id=i.id AND l.valid_to IS NULL
                   LEFT JOIN exchange e ON e.mic=l.exchange_mic LEFT JOIN issuer iss ON iss.id=i.issuer_id WHERE i.id = ANY(%s)""", (members,))
    return {"origin": origin, "members": rows}


@app.put("/api/peers/{instrument_id}")
def peers_put(instrument_id: str, body: dict = Body(...), user: str = Depends(current_user)):
    ids = []
    for t in body.get("tickers", []):
        tk, _, ex = t.partition(":")
        r = universe.resolve(tk, commands.EXCH_ALIASES.get(ex, ex) if ex else None)
        if r:
            ids.append(r["instrument"]["id"])
    db.q("""INSERT INTO peer_group(user_id,instrument_id,members) VALUES (%s,%s,%s)
            ON CONFLICT (user_id,instrument_id) DO UPDATE SET members=EXCLUDED.members, updated_at=now()""", (user, instrument_id, ids))
    return peers_get(instrument_id, user)


@app.get("/api/export/statement.csv")
def export_statement(issuer_id: str, statement: str = "IS", freq: str = "A", scope: str = "consolidated", as_of: Optional[str] = None,
                     user: str = Depends(current_user)):
    iss = _issuer(issuer_id)
    src = _fund_source(iss)
    require(user, src, "fundamentals", "export", {"issuer": issuer_id, "statement": statement, "freq": freq})
    t = statements.build(iss, statement, freq, scope, _as_of(as_of))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["# fonte", src, "emissor", iss["name"], "escopo", scope, "moeda", t["currency"], "unidade", "unidades monetárias (sem escala)",
                "as_of", as_of or "último conhecido", "exportado_em", datetime.now(timezone.utc).isoformat(), "por", user])
    w.writerow(["conta", "rótulo"] + [f"{c['label']} ({c['calendar']})" for c in t["columns"]] + ["fact_ids/fórmulas"])
    for r in t["rows"]:
        w.writerow([r["concept"], r["label"]] + [c.get("v", "") if c["state"] != "absent" else "" for c in r["cells"]]
                   + [";".join(str(c.get("fact_id") or c.get("formula") or "") for c in r["cells"])])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{iss["short_name"]}_{statement}_{freq}.csv"'})


@app.get("/api/export/macro.csv")
def export_macro(code: str, user: str = Depends(current_user)):
    s = research.macro_series(code.upper(), None, 100000)
    require(user, s["source"], "macro", "export", {"series": code})
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["data_referencia", "valor", "unidade", "publicado_em", "vintage", "fonte"])
    for o in s["observations"]:
        w.writerow([o["date"], o["value"] or "", s["unit"], o["published_at"], o["vintage"], s["source"]])
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8")


DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return HTMLResponse((DIST / "index.html").read_text(encoding="utf-8"))
