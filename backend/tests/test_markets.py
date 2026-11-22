"""Testes de aceite 2–10 da estação gráfica/notícias (1 e 8 também verificados no navegador — ver README).
Séries marcadas TESTE são fictícias e existem só neste arquivo."""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.app import db
from backend.app.calc import alerts as AL
from backend.app.calc import ta
from backend.app.services import marketdata as MD

H = {"X-User": "ana"}


def _listing(t):
    return str(db.q1("SELECT id FROM listing WHERE ticker=%s AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)", (t,))["id"])


def _bars(closes, start=date(2026, 1, 5), highs=None, lows=None, vols=None):
    out, d = [], start
    for i, c in enumerate(closes):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        h = highs[i] if highs else c * 1.01
        l = lows[i] if lows else c * 0.99
        out.append({"session_date": d, "open": c, "high": h, "low": l, "close": c, "volume": (vols[i] if vols else 1000), "fin_volume": None, "vwap": None})
        d += timedelta(days=1)
    return out


# ---------- 2. notícia após o fechamento ----------
def test_2_after_close_news_keeps_real_time_and_maps_to_next_session(client):
    # 8-K item 2.02 (resultados) da Apple, aceito na SEC em 2026-11-02 21:30:23 UTC = 16:30:23 ET (após o fechamento 16:00)
    n = db.q1("""SELECT id, published_at FROM news_item WHERE outlet='Apple' AND headline LIKE %s AND published_at::date='2026-11-02'""",
              ("%Resultados operacionais%",))
    assert n and n["published_at"] == datetime(2026, 11, 2, 21, 30, 23, tzinfo=timezone.utc)
    r = MD.first_tradable_session(_listing("AAPL"), n["published_at"], "second")
    assert r["status"] == "após o fechamento" and r["session_date"] == "2026-11-03" and r["local_time"].startswith("2026-11-02T16:30:23")
    # 6-K da Petrobras aceito 2026-11-16 23:33:09 UTC = 20:33 BRT -> 1ª sessão B3 = 17/11
    p = db.q1("SELECT published_at FROM news_item WHERE external_id='0001292814-26-005335'")
    r2 = MD.first_tradable_session(_listing("PETR4"), p["published_at"], "second")
    assert r2["status"] == "após o fechamento" and r2["session_date"] == "2026-11-17"
    # a evidência da notícia mantém o instante original e aponta a sessão negociável separadamente
    nid = db.q1("SELECT id FROM news_item WHERE external_id='0001292814-26-005335'")["id"]
    d = client.get(f"/api/news/{nid}", headers=H).json()
    assert datetime.fromisoformat(d["item"]["published_at"]) == datetime(2026, 11, 16, 23, 33, 9, tzinfo=timezone.utc)
    rx = next(x for x in d["reactions"] if x["ticker"] == "PETR4")
    assert rx["tradable_session"]["session_date"] == "2026-11-17" and rx["tradable_session"]["status"] == "após o fechamento"


# ---------- 3. split ajustado sem queda artificial nem alerta falso ----------
def test_3_split_in_adjusted_series_no_artificial_drop_or_false_alert():
    closes = [100 + i * 0.1 for i in range(30)] + [25.8, 25.9, 26.0]           # TESTE: desdobramento 4:1 na barra 30
    raw = _bars(closes)
    split = {"id": 1, "kind": "split", "ex_date": raw[30]["session_date"], "ratio": Decimal(4), "amount": None, "currency": None, "source": "test"}
    adj = MD.adjust(raw, [split])["bars"]
    r_raw = float(raw[30]["close"]) / float(raw[29]["close"]) - 1
    r_adj = float(adj[30]["close"]) / float(adj[29]["close"]) - 1
    assert r_raw < -0.7 and abs(r_adj) < 0.01
    assert AL.evaluate("breakout_low", {"n": 20}, "close", "once_per_bar", raw)              # bruto: alerta falso
    assert not AL.evaluate("breakout_low", {"n": 20}, "close", "once_per_bar", adj)          # ajustado: nenhum
    with pytest.raises(MD.AdjustmentError):
        MD.adjust(adj, [split], already_adjusted=True)                                       # nunca ajusta duas vezes


# ---------- 4. média e RSI conferem com referência; zoom não altera ----------
WILDER = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820,
          46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439, 46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288, 44.1783,
          44.2181, 44.5672, 43.4205, 42.6628, 43.1314]
REF_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42, 39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77]


def test_4_rsi_and_sma_match_reference_and_zoom_does_not_change(client):
    r = ta.rsi(WILDER, 14)
    assert all(v is None for v in r[:14])                                                    # aquecimento declarado
    assert [round(v, 2) for v in r[14:]] == REF_RSI                                          # tabela de referência (Wilder/StockCharts)
    s = ta.sma(WILDER, 10)
    assert s[8] is None and abs(s[9] - sum(WILDER[:10]) / 10) < 1e-12 and abs(s[-1] - sum(WILDER[-10:]) / 10) < 1e-12
    lid = _listing("PETR4")
    st = json.dumps([{"id": "rsi", "params": {"n": 14}}, {"id": "sma", "key": "sma200", "params": {"n": 200}}])
    a = client.get(f"/api/chart/{lid}", params={"window": "3M", "studies": st}, headers=H).json()
    b = client.get(f"/api/chart/{lid}", params={"window": "2Y", "studies": st}, headers=H).json()
    assert a["bars"][-1]["t"] == b["bars"][-1]["t"] and a["visible_from"] != b["visible_from"]
    for k, s in (("rsi", "rsi"), ("sma200", "sma")):
        assert a["studies"][k]["series"][s][-1] == b["studies"][k]["series"][s][-1]
    closes = [x["c"] for x in b["bars"]]
    assert abs(b["studies"]["sma200"]["series"]["sma"][-1] - sum(closes[-200:]) / 200) < 1e-9


# ---------- 5. VWAP de sessão ----------
def test_5_vwap_session_resets_and_declares_method(client):
    lid = _listing("PETR4")
    d = client.get(f"/api/chart/{lid}", params={"window": "1M", "studies": json.dumps([{"id": "vwap"}])}, headers=H).json()
    vw = d["studies"]["vwap"]
    assert "negócios individuais" in vw["method"]
    bar = db.q1("SELECT vwap, fin_volume, volume FROM price_bar WHERE listing_id=%s AND interval='1d' ORDER BY session_date DESC LIMIT 1", (lid,))
    assert abs(vw["series"]["vwap"][-1] - float(bar["vwap"])) < 1e-9
    assert abs(float(bar["fin_volume"]) / float(bar["volume"]) - float(bar["vwap"])) < 0.01                  # PREMED = VOLTOT/QUATOT
    # intradiário (TESTE): reinicia na abertura da sessão seguinte
    mk = lambda s, p, v: {"session": s, "high": p, "low": p, "close": p, "volume": v}
    bars = [mk("D1", 10, 100), mk("D1", 12, 100), mk("D2", 20, 50), mk("D2", 22, 50)]
    r = ta.vwap_intraday(bars, lambda b: b["session"])
    assert r["values"] == [10, 11, 20, 21] and "aproximação" in r["method"]


# ---------- 6. alerta de rompimento ----------
def test_6_breakout_uses_only_previous_sessions_and_dedupes(client):
    highs = [10] * 20 + [10.5, 10.6, 10.7]
    bars = _bars([9.9] * 20 + [10.4, 10.55, 10.65], highs=highs)
    # na barra 20 a máxima é 10.5 mas o FECHAMENTO 10.4 > máx. das 20 anteriores (10) -> dispara; a própria barra não entra na janela
    hits = AL.evaluate("breakout_high", {"n": 20}, "close", "once_per_bar", bars)
    assert hits[0]["session_date"] == str(bars[20]["session_date"]) and hits[0]["reference"] == 10
    assert [h["reference"] for h in hits] == [10, 10.5, 10.6]                                 # referência = máximas ANTERIORES
    assert len(AL.evaluate("breakout_high", {"n": 20}, "close", "once", bars)) == 1           # política 'once'
    ticks = AL.evaluate_ticks("breakout_high", {"n": 20}, "once_per_bar", bars[:20], [9.95, 10.01, 10.2, 10.3])
    assert len(ticks) == 1 and ticks[0]["tick"] == 10.01                                      # intrabar: 1 disparo por barra
    lid = _listing("PETR4")
    a = client.post("/api/alerts", json={"listing_id": lid, "kind": "breakout_high", "params": {"n": 20}, "mode": "close", "dedupe": "once_per_bar"}, headers=H).json()
    assert "20 sessões anteriores (exclui a sessão atual)" in a["condition"] and len(a["new_fires"]) > 0
    again = client.post(f"/api/alerts/{a['rule']['id']}/evaluate", headers=H).json()
    assert again["new_fires"] == []                                                           # reavaliar não duplica disparos
    n = db.q1("SELECT count(*) n, count(DISTINCT bar_ts) d FROM alert_event WHERE rule_id=%s", (a["rule"]["id"],))
    assert n["n"] == n["d"]


# ---------- 7. data de corte ----------
def test_7_historical_cutoff_hides_later_publications(client):
    lid = _listing("PETR4")
    d = client.get(f"/api/chart/{lid}", params={"as_of": "2026-11-11", "window": "3M"}, headers=H).json()
    assert d["bars"][-1]["t"] <= "2026-11-11"
    assert all(e["published_at"][:10] <= "2026-11-11" or e["published_at"][:10] == "2026-11-12" and False for e in d["events"])
    assert not any("Unaudited Condensed" in e["headline"] and "2026-11-12" in e["published_at"] for e in d["events"])   # ITR 3T26 6-K de 12/11
    n = client.get("/api/news", params={"tab": "ticker", "ticker": "PETR4", "as_of": "2026-11-11"}, headers=H).json()
    assert n["items"] and max(i["published_at"] for i in n["items"]) <= "2026-11-12T03:00"     # nada após 11/11 23:59 BRT
    t = client.get(f"/api/issuers/{db.q1('SELECT id FROM issuer WHERE short_name=%s', ('Petrobras',))['id']}/statements",
                   params={"statement": "IS", "freq": "Q", "as_of": "2026-11-09"}, headers=H).json()
    assert max(c["end"] for c in t["columns"]) == "2026-06-30"                                 # ITR 3T26 (recebido 10/11) ainda não existia


# ---------- 10. feed intradiário indisponível ----------
def test_10_intraday_outage_keeps_daily_history(client):
    from backend.app.services import quotes
    lid = _listing("PETR4")
    quotes.interrupt("SIM_DEV", True)
    try:
        i = client.get(f"/api/chart/{lid}", params={"interval": "5m", "window": "1D"}, headers=H).json()
        assert i["bars"] == [] and i["feed"]["intraday"]["state"] == "interrupted" and "histórico diário segue disponível" in i["feed"]["intraday"]["label"]
        d = client.get(f"/api/chart/{lid}", params={"interval": "1D", "window": "1Y"}, headers=H).json()
        last = db.q1("SELECT max(session_date) d FROM price_bar WHERE listing_id=%s AND interval='1d'", (lid,))["d"]
        assert d["bars"] and d["feed"]["daily"]["state"] == "eod" and d["feed"]["daily"]["last_session"] == str(last)
        assert d["feed"]["daily"]["granularity"] == "diário" and d["feed"]["intraday"]["state"] == "interrupted"
    finally:
        quotes.interrupt("SIM_DEV", False)


# ---------- 9. layout salvo (lado servidor) ----------
def test_9_saved_layout_roundtrip(client):
    state = {"layout": {"sizes": [14, 70, 16], "collapsed": [True, False, False], "maximized": None}, "cmd": "PETR4 B3 CHART 1D 6M",
             "fnKey": "fn:x:CHART", "fnState": {"type": "candle", "log": True, "basis": "adjusted", "bench": "BOVA11",
                                               "studies": [{"key": "rsi1", "id": "rsi", "params": {"n": 14}}], "view": {"from": 10, "to": 140}, "candle": "2026-11-12"},
             "cell": "candle:2026-11-12"}
    client.put("/api/layouts/Teste 9", json=state, headers=H)
    r = client.get("/api/layouts", headers=H).json()
    assert set(r["builtin"]) == {"Visão Geral", "Gráfico", "Balanço", "Notícias", "Mesa Brasil–EUA"}
    assert next(x for x in r["saved"] if x["name"] == "Teste 9")["state"] == state
    iid = client.post("/api/command/parse", json={"text": "PETR4 B3 CHART"}).json()["instrument_id"]
    dr = [{"kind": "trend", "points": [{"t": "2026-09-01", "p": 40}, {"t": "2026-11-12", "p": 44.7}]}, {"kind": "fib", "points": [{"t": "2026-08-01", "p": 38}, {"t": "2026-10-01", "p": 58}], "locked": True}]
    got = client.put(f"/api/drawings/{iid}", json={"basis": "adjusted", "drawings": dr}, headers=H).json()["drawings"]
    assert [g["kind"] for g in got] == ["trend", "fib"] and got[1]["locked"] is True
    assert client.get(f"/api/drawings/{iid}?basis=adjusted", headers={"X-User": "paulo"}).json()["drawings"] == []   # por usuário


# ---------- extras: rastreador reproduzível e catálogo de notícias ----------
def test_scan_example_is_reproducible(client):
    ex = client.get("/api/scan/example").json()
    a = client.post("/api/scan", json={**ex, "as_of": "2026-11-19"}, headers=H).json()
    b = client.post("/api/scan", json={**ex, "as_of": "2026-11-19"}, headers=H).json()
    assert a["cut_date"] == "2026-11-19" and [x["ticker"] for x in a["passed"]] == [x["ticker"] for x in b["passed"]]
    for p in a["passed"]:
        f = {w["field"]: w for w in p["why"]}
        assert f["avg_fin_volume"]["value"] > 10_000_000 and f["close_vs_sma"]["value"] > 0 and f["return_vs_bench"]["value"] > 0
    assert any("histórico insuficiente" in x["reason"] for x in a["excluded"])
    assert "BOVA11" in a["benchmark"]["note"]


def test_news_catalog_marks_contract_sources(client):
    c = client.get("/api/news-catalog").json()["catalog"]
    assert any(x["source"] == "Reuters" and x["status"] == "depende de contrato" for x in c)
    assert any(x["source"].startswith("SEC EDGAR") and x["status"] == "integrado" for x in c)
