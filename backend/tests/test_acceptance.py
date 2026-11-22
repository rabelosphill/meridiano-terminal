"""Critérios de aceite A–H (partes verificáveis no backend; E e o retorno por teclado de A são verificados no navegador — ver README)."""
from datetime import date
from decimal import Decimal

import httpx
import pytest

from backend.app import db
from backend.app.calc import dcf as DCF
from backend.app.calc import periods as P
from backend.app.calc.returns import (Action, AdrTerms, CurrencyMismatch, DoubleAdjustment, FxQuote, PriceSeries, adr_implied_price,
                                      cumulative, parity_ok, total_returns)

H = {"X-User": "ana"}


def _cell(client, issuer, statement, freq, concept, end, **kw):
    r = client.get(f"/api/issuers/{issuer}/statements", params={"statement": statement, "freq": freq, **kw}, headers=H)
    assert r.status_code == 200, r.text
    t = r.json()
    row = next(x for x in t["rows"] if x["concept"] == concept)
    col = next(i for i, c in enumerate(t["columns"]) if c["end"] == end)
    return t, row["cells"][col]


# ---------------- A: empresa BR e EUA -> conta -> fonte ----------------
@pytest.mark.parametrize("cmd,issuer,stmt,freq,concept,end", [
    ("PETR4 B3 FIN Q", "Petrobras", "IS", "Q", "3.01", "2026-09-30"),
    ("AAPL NASDAQ FIN A", "Apple", "IS", "A", "RevenueFromContractWithCustomerExcludingAssessedTax", "2026-09-26"),
])
def test_A_open_company_select_account_navigate_to_source(client, ids, cmd, issuer, stmt, freq, concept, end):
    p = client.post("/api/command/parse", json={"text": cmd}).json()
    assert p["ok"] and p["fn"] == "FIN" and p["args"]["freq"] == freq
    assert p["issuer_id"] == ids[issuer]
    _, cell = _cell(client, p["issuer_id"], stmt, freq, concept, end)
    assert cell["state"] == "value" and cell["basis"] == "reported" and cell["fact_id"]
    L = client.get(f"/api/facts/{cell['fact_id']}", headers=H).json()
    assert L["document"]["url"].startswith("http") and L["location"]["text"]
    src = client.get(f"/api/facts/{cell['fact_id']}/source", headers=H)
    assert src.status_code == 200
    if issuer == "Apple":
        assert L["location"]["ix_ids"][0] in src.text and "ft-hl" in src.text      # elemento iXBRL destacado no 10-K original
    else:
        assert f'id="target"' in src.text and str(L["location"]["line"]) in src.text  # linha do CSV original da CVM


# ---------------- B: reconciliação com o documento original ----------------
def test_B_reconcile_us_10k(client, ids):
    _, cell = _cell(client, ids["Apple"], "IS", "A", "RevenueFromContractWithCustomerExcludingAssessedTax", "2026-09-26")
    rec = client.get(f"/api/facts/{cell['fact_id']}/reconcile", headers=H).json()
    assert rec["ok"] is True
    assert rec["document_shows"] == "478,834" and rec["document_scale"] == 6          # escala: milhões
    assert rec["currency"] == "USD" and rec["scope"] == "consolidated"
    assert rec["period"] == ["2025-09-28", "2026-09-26"]                              # exercício fiscal 52/53 semanas
    assert Decimal(rec["fact_value"]) == Decimal("478834000000")


def test_B_reconcile_br_dfp(client, ids):
    _, cell = _cell(client, ids["Petrobras"], "IS", "A", "3.01", "2025-12-31")
    rec = client.get(f"/api/facts/{cell['fact_id']}/reconcile", headers=H).json()
    assert rec["ok"] is True
    assert rec["document_scale"] == "MIL" and rec["currency"] == "REAL"
    assert rec["scope"] == "DF Consolidado - Demonstração do Resultado"
    assert rec["period"] == ["2025-01-01", "2025-12-31"]
    assert Decimal(rec["fact_value"]) == Decimal("497549000") * 1000


def test_B_reconcile_every_reported_cell_of_a_statement(client, ids):
    """Todas as células reportadas da DRE anual de ambos os países batem com o original."""
    for issuer, n_min in (("Petrobras", 20), ("Apple", 10)):
        t = client.get(f"/api/issuers/{ids[issuer]}/statements", params={"statement": "IS", "freq": "A"}, headers=H).json()
        fids = [c["fact_id"] for r in t["rows"] for c in r["cells"][-2:] if c.get("basis") == "reported" and c.get("fact_id")]
        checked = 0
        for fid in fids:
            rec = client.get(f"/api/facts/{fid}/reconcile", headers=H).json()
            if rec["ok"] is None:
                continue  # fato sem marcação ix no HTML (ex.: só no companyfacts)
            assert rec["ok"] is True, rec
            checked += 1
        assert checked >= n_min, (issuer, checked)


# ---------------- C: reapresentação fora da consulta histórica ----------------
def test_C_restatement_excluded_from_point_in_time_us(client, ids):
    # Apple: passivo fiscal diferido de 24/09/2022 divulgado 5.557 mi (10-K 2022) e reapresentado 7.139 mi (10-K 2023, 02/11/2023)
    _, before = _cell(client, ids["Apple"], "BS", "A", "DeferredIncomeTaxLiabilities", "2022-09-24", as_of="2023-06-30")
    _, after = _cell(client, ids["Apple"], "BS", "A", "DeferredIncomeTaxLiabilities", "2022-09-24")
    assert Decimal(before["v"]) == Decimal("5557000000")
    assert Decimal(after["v"]) == Decimal("7139000000") and after["restated"]
    # fluxo de caixa: variação de outros passivos FY2021 5.799 -> 7.475 mi
    _, b = _cell(client, ids["Apple"], "CF", "A", "IncreaseDecreaseInOtherOperatingLiabilities", "2021-09-25", as_of="2023-01-01")
    _, a = _cell(client, ids["Apple"], "CF", "A", "IncreaseDecreaseInOtherOperatingLiabilities", "2021-09-25")
    assert Decimal(b["v"]) == Decimal("5799000000") and Decimal(a["v"]) == Decimal("7475000000")


def test_C_restatement_excluded_from_point_in_time_br(client, ids):
    """Reapresentações reais no snapshot da CVM:
    - Vale: Provisões (2.01.06) em 31/12/2024 = 30.922 mi no DFP 2024; 28.027 mi como comparativo no DFP 2025 (recebido 12/03/2026).
    - Petrobras: Caixa gerado nas operações (6.01.01) FY2024 = 260.414 mi no DFP 2024; 260.492 mi no DFP 2025 (recebido 05/03/2026)."""
    _, v_before = _cell(client, ids["Vale"], "BS", "A", "2.01.06", "2024-12-31", as_of="2026-03-01")
    _, v_after = _cell(client, ids["Vale"], "BS", "A", "2.01.06", "2024-12-31")
    assert Decimal(v_before["v"]) == Decimal("30922000000") and Decimal(v_after["v"]) == Decimal("28027000000")
    assert v_after["restated"] and not v_before["restated"]
    _, p_before = _cell(client, ids["Petrobras"], "CF", "A", "6.01.01", "2024-12-31", as_of="2026-03-01")
    _, p_after = _cell(client, ids["Petrobras"], "CF", "A", "6.01.01", "2024-12-31")
    assert Decimal(p_before["v"]) == Decimal("260414000000") and Decimal(p_after["v"]) == Decimal("260492000000")
    # visão "como divulgado originalmente" devolve o valor da 1ª divulgação mesmo hoje
    _, p_orig = _cell(client, ids["Petrobras"], "CF", "A", "6.01.01", "2024-12-31", view="original")
    assert Decimal(p_orig["v"]) == Decimal("260414000000")
    # e nada publicado depois de D aparece: nenhuma coluna posterior ao último documento conhecido em D
    t, _ = _cell(client, ids["Petrobras"], "IS", "Q", "3.01", "2025-09-30", as_of="2025-11-30")
    assert max(c["end"] for c in t["columns"]) == "2025-09-30"


# ---------------- D: retornos, eventos e ADR ----------------
def test_D_split_and_dividend_do_not_create_artificial_return():
    # ambiente de TESTE (valores fictícios): split 4:1 real da Apple em 2020-08-31; preço cai 4x sem mudar valor
    s = PriceSeries([date(2020, 8, 28), date(2020, 8, 31), date(2020, 9, 1)], [Decimal("499.23"), Decimal("124.81"), Decimal("124.81")], "USD")
    split = Action("aapl-split-2020", "split", date(2020, 8, 31), ratio=Decimal(4))
    r = total_returns(s, [split])
    assert abs(r[0][1] - Decimal("0.00002")) < Decimal("0.0001")   # ~0%, não −75%
    # dividendo: preço ex cai exatamente o provento -> retorno total zero
    s2 = PriceSeries([date(2024, 1, 2), date(2024, 1, 3)], [Decimal("100"), Decimal("98")], "BRL")
    r2 = total_returns(s2, [Action("div1", "cash_dividend", date(2024, 1, 3), amount=Decimal("2"), currency="BRL")])
    assert r2[0][1] == 0
    assert cumulative(r2) == 0


def test_D_corporate_action_never_applied_twice():
    s = PriceSeries([date(2020, 8, 28), date(2020, 8, 31)], [Decimal("400"), Decimal("100")], "USD", adjusted=True)
    with pytest.raises(DoubleAdjustment):
        total_returns(s, [Action("x", "split", date(2020, 8, 31), ratio=Decimal(4))])
    s.adjusted = False
    with pytest.raises(DoubleAdjustment):
        a = Action("x", "split", date(2020, 8, 31), ratio=Decimal(4))
        total_returns(s, [a, a])


def test_D_adr_ratio_and_currency_inversions_fail(client, ids):
    terms_row = db.q1("""SELECT a.adr_units, a.underlying_units FROM adr_terms a JOIN listing l ON l.instrument_id=a.adr_id WHERE l.ticker='PBR'""")
    terms = AdrTerms(Decimal(terms_row["adr_units"]), Decimal(terms_row["underlying_units"]), "BRL")
    assert terms.underlying_units == 2          # 1 PBR = 2 PETR3 (cadastro)
    fx = FxQuote("USD", "BRL", Decimal("5.80"))
    local = Decimal("35.20")
    implied = adr_implied_price(local, "BRL", terms, fx)
    assert implied == Decimal("35.20") * 2 / Decimal("5.80")
    adr_market = implied * Decimal("1.004")
    assert parity_ok(adr_market, implied)
    inverted_ratio = adr_implied_price(local, "BRL", AdrTerms(Decimal(2), Decimal(1), "BRL"), fx)
    assert not parity_ok(adr_market, inverted_ratio)                 # razão invertida é detectada
    inverted_fx = FxQuote("BRL", "USD", Decimal("5.80"))             # cotação "5,80 USD por BRL" (errada)
    assert not parity_ok(adr_market, adr_implied_price(local, "BRL", terms, inverted_fx))
    with pytest.raises(CurrencyMismatch):
        adr_implied_price(local, "USD", terms, fx)                   # preço local na moeda errada
    with pytest.raises(CurrencyMismatch):
        FxQuote("EUR", "BRL", Decimal("6.2")).convert(Decimal(1), "BRL", "USD")


# ---------------- F: provedor interrompido e reprocessamento ----------------
def test_F_interrupted_feed_keeps_last_valid_value(client, ids):
    from backend.app.services import quotes
    from datetime import datetime, timezone, timedelta
    obs = datetime.now(timezone.utc) - timedelta(seconds=3)
    quotes.write_quote(ids["L:PETR4"], Decimal("32.10"), Decimal("31.90"), "SIM_DEV", "simulated", obs)
    quotes.interrupt("SIM_DEV", True)
    try:
        q = next(x for x in client.get("/api/quotes", headers=H).json()["quotes"] if x["ticker"] == "PETR4")
        assert q["price"] == "32.10" and q["feed_state"] == "interrupted"
        assert abs((datetime.fromisoformat(q["observed_at"]) - obs).total_seconds()) < 0.001   # hora ORIGINAL da observação
        assert q["market"]["state"] in ("open", "closed", "holiday")               # mercado é estado separado do feed
    finally:
        quotes.interrupt("SIM_DEV", False)
    # EOD: refresh periódico mantém a data de referência original da observação
    u = next(x for x in client.get("/api/quotes", headers=H).json()["quotes"] if x["ticker"] == "USDBRL")
    last = db.q1("SELECT max(obs_date) d FROM macro_observation o JOIN macro_series s ON s.id=o.series_id WHERE s.code='BR.PTAX'")["d"]
    assert u["feed_class"] == "eod" and u["observed_at"] == str(last)


def test_F_replay_batch_is_idempotent(loaded_db):
    from backend import worker
    n0 = db.q1("SELECT count(*) n FROM fact")["n"]
    m0 = db.q1("SELECT count(*) n FROM macro_observation")["n"]
    stats = worker.ingest("all", "snapshot")
    assert all(s["inserted"] == 0 for s in stats.values()), stats
    assert db.q1("SELECT count(*) n FROM fact")["n"] == n0
    assert db.q1("SELECT count(*) n FROM macro_observation")["n"] == m0


def test_F_revision_creates_new_vintage_not_overwrite(loaded_db):
    from backend.app.connectors import macro
    import json
    s = db.q1("SELECT id FROM macro_series WHERE code='BR.SELIC'")
    last = db.q1("SELECT obs_date, value FROM macro_observation WHERE series_id=%s ORDER BY obs_date DESC LIMIT 1", (s["id"],))
    d = last["obs_date"]
    payload = json.dumps([{"data": d.strftime("%d/%m/%Y"), "valor": str(last["value"] + Decimal("0.25"))}]).encode()
    st = macro.ingest("BR.SELIC", payload=payload)
    assert st["revisions"] == 1
    rows = db.q("SELECT value, vintage FROM macro_observation WHERE series_id=%s AND obs_date=%s ORDER BY vintage", (s["id"], d))
    assert [r["vintage"] for r in rows] == [1, 2] and rows[0]["value"] == last["value"]
    db.q("DELETE FROM macro_observation WHERE series_id=%s AND obs_date=%s AND vintage=2", (s["id"], d))   # limpa (ambiente de teste)


def test_F_retry_with_backoff_then_snapshot_fallback(monkeypatch):
    from backend.app.connectors.base import HttpClient, SourceUnavailable
    calls = {"n": 0}
    def flaky(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json={"ok": True})
    c = HttpClient("TEST", 100, transport=httpx.MockTransport(flaky), base_delay=0.01)
    assert c.get("https://example.test/x").json() == {"ok": True} and calls["n"] == 3
    dead = HttpClient("TEST", 100, transport=httpx.MockTransport(lambda r: httpx.Response(503)), max_retries=2, base_delay=0.01)
    with pytest.raises(SourceUnavailable):
        dead.get("https://example.test/y")
    # rede indisponível em modo auto -> conector usa snapshot identificado
    from backend.app.connectors import macro, base
    monkeypatch.setattr(base.HttpClient, "get", lambda self, url, params=None: (_ for _ in ()).throw(SourceUnavailable("offline")))
    st = macro.ingest("BR.IPCA", mode="auto")
    run = db.q1("SELECT mode FROM ingestion_run WHERE connector='BCB_SGS:BR.IPCA' ORDER BY id DESC LIMIT 1")
    assert run["mode"] == "snapshot" and st["inserted"] == 0


# ---------------- G: exportação sem permissão, inclusive via API direta ----------------
def test_G_export_permission_enforced_on_api(client, ids):
    p = {"issuer_id": ids["Petrobras"], "statement": "IS", "freq": "A"}
    ok = client.get("/api/export/statement.csv", params=p, headers={"X-User": "ana"})
    assert ok.status_code == 200 and "3.01" in ok.text
    denied = client.get("/api/export/statement.csv", params=p, headers={"X-User": "bia"})
    assert denied.status_code == 403 and denied.json()["detail"]["field"] == "fundamentals"
    assert client.get("/api/export/macro.csv", params={"code": "BR.SELIC"}, headers={"X-User": "bia"}).status_code == 200
    # sem cabeçalho de usuário desconhecido também não passa
    assert client.get("/api/export/statement.csv", params=p, headers={"X-User": "mallory"}).status_code == 401
    log = db.q1("SELECT allowed FROM audit_log WHERE user_id='bia' AND action LIKE 'export:CVM_DADOS%%' ORDER BY id DESC LIMIT 1")
    assert log["allowed"] is False
    # visualização de feed sem permissão: preço removido
    q = next(x for x in client.get("/api/quotes", headers={"X-User": "bia"}).json()["quotes"] if x["ticker"] == "PETR4")
    assert "price" not in q and q["feed_state"] == "no_permission"


# ---------------- Comandos, universo, cálculos ----------------
def test_commands_synonyms_incompatible_and_ticker_change(client):
    p = client.post("/api/command/parse", json={"text": "petr4 b3 demonstracoes t dfc"}).json()
    assert p["ok"] and p["fn"] == "FIN" and p["args"] == {"freq": "Q", "statement": "CF"}
    bad = client.post("/api/command/parse", json={"text": "USDBRL FIN"}).json()
    assert not bad["ok"] and bad["error"] == "incompatible" and "moeda" in bad["message"] and "MACRO BR PTAX" in bad["suggestions"]
    fb = client.post("/api/command/parse", json={"text": "FB NASDAQ OVERVIEW"}).json()
    meta = client.post("/api/command/parse", json={"text": "META NASDAQ OVERVIEW"}).json()
    assert fb["instrument_id"] == meta["instrument_id"] and "META" in fb["notice"]      # chave persistente sobrevive à troca de ticker
    f = client.get("/api/find", params={"q": "petrobras"}).json()
    assert {l["ticker"] for l in f["listings"]} >= {"PETR3", "PETR4", "PBR", "PBR.A"}
    assert client.post("/api/command/parse", json={"text": "MACRO BR SELIC"}).json()["args"]["code"] == "BR.SELIC"


def test_balances_never_summed_and_ytd_validation():
    with pytest.raises(P.NotComparable):
        P.sum_balances()
    b = [P.PeriodValue(None, date(2026, m, 28), Decimal(m), kind="instant") for m in (3, 6, 9)]
    assert P.ltm_balance(b)["value"] == Decimal(9)
    q3 = P.PeriodValue(date(2026, 1, 1), date(2026, 9, 30), Decimal(90), concept="6.01", label="Caixa")
    h1 = P.PeriodValue(date(2026, 1, 1), date(2026, 6, 30), Decimal(55), concept="6.01", label="Caixa")
    assert P.quarter_from_ytd(q3, h1)["value"] == Decimal(35)
    other_year = P.PeriodValue(date(2025, 1, 1), date(2025, 6, 30), Decimal(50), concept="6.01", label="Caixa")
    with pytest.raises(P.NotComparable):
        P.quarter_from_ytd(q3, other_year)
    relabeled = P.PeriodValue(date(2026, 1, 1), date(2026, 6, 30), Decimal(55), concept="6.01", label="Caixa e investimentos")
    with pytest.raises(P.NotComparable):
        P.quarter_from_ytd(q3, relabeled)


def test_absence_is_not_zero(client, ids):
    t = client.get(f"/api/issuers/{ids['Petrobras']}/statements", params={"statement": "IS", "freq": "A"}, headers=H).json()
    states = {c["state"] for r in t["rows"] for c in r["cells"]}
    assert "zero" in states and "value" in states
    t2 = client.get(f"/api/issuers/{ids['Vale']}/statements", params={"statement": "CF", "freq": "Q"}, headers=H).json()
    assert any(c["state"] == "absent" and c.get("reason") for r in t2["rows"] for c in r["cells"])


def _inp(**kw):
    base = dict(currency="BRL", basis="nominal", base_revenue=Decimal(1000), growth=[Decimal("0.05")] * 5, ebit_margin=[Decimal("0.2")] * 5,
                tax_rate=Decimal("0.34"), capex_pct_rev=Decimal("0.08"), da_pct_rev=Decimal("0.06"), nwc_pct_rev=Decimal("0.1"),
                wacc=Decimal("0.12"), g=Decimal("0.04"), wacc_currency="BRL", wacc_basis="nominal", net_debt=Decimal(200), diluted_shares=Decimal(100))
    base.update(kw)
    return DCF.DcfInputs(**base)


def test_dcf_validations_bridge_matrix_reverse():
    with pytest.raises(DCF.DcfError):
        DCF.run(_inp(g=Decimal("0.12")))
    with pytest.raises(DCF.DcfError):
        DCF.run(_inp(wacc_currency="USD"))
    with pytest.raises(DCF.DcfError):
        DCF.run(_inp(wacc_basis="real"))
    r = DCF.run(_inp())
    assert Decimal(r["equity_value"]) == Decimal(r["enterprise_value"]) - 200
    assert Decimal(r["per_share"]) == Decimal(r["equity_value"]) / 100
    m = DCF.sensitivity(_inp(), [Decimal("0.04"), Decimal("0.12")], [Decimal("0.04")])
    assert m["rows"][0]["values"][0] is None                     # WACC = g inválido
    rev = DCF.reverse(_inp(), Decimal(r["per_share"]))
    assert abs(Decimal(rev["implied_growth"]) - Decimal("0.05")) < Decimal("0.0001")


def test_dcf_defaults_from_real_fundamentals(client, ids):
    d = client.get(f"/api/dcf/defaults/{ids['Petrobras']}", headers=H).json()
    assert d["inputs"]["currency"] == "BRL" and Decimal(d["inputs"]["base_revenue"]) == Decimal("497549000000")
    assert "PREMISSA DO USUÁRIO" in d["provenance"]["wacc"]
    res = client.post("/api/dcf/run", json={"inputs": d["inputs"], "target_price": "35"}).json()
    assert Decimal(res["result"]["per_share"]) > 0 and res["reverse"] is not None


def test_thesis_versions_keep_author_time_and_context(client, ids):
    iid = client.post("/api/command/parse", json={"text": "PETR4 B3 OVERVIEW"}).json()["instrument_id"]
    body = {"title": "Petrobras: dividendos", "stance": "long", "body": "v1", "assumptions": [{"label": "Brent", "value": "75", "unit": "USD/bbl"}],
            "context": {"cmd": "PETR4 B3 FIN Q IS", "cell": {"concept": "3.01", "period": "2026-09-30"}}}
    client.post(f"/api/thesis/{iid}", json=body, headers={"X-User": "paulo"})
    r = client.post(f"/api/thesis/{iid}", json={**body, "body": "v2"}, headers={"X-User": "paulo"}).json()
    assert [v["version"] for v in r["versions"]] == [2, 1] and r["versions"][0]["author"] == "paulo"
    assert r["versions"][1]["body"] == "v1" and r["versions"][0]["context"]["cell"]["concept"] == "3.01"
    assert client.get(f"/api/thesis/{iid}", headers={"X-User": "ana"}).json()["thesis"] is None   # tese é por usuário


def test_compare_explicit_currency_and_period(client, ids):
    ins = [{"ticker": "PETR4", "exchange": "B3", "issuer_id": ids["Petrobras"]}, {"ticker": "AAPL", "exchange": "NASDAQ", "issuer_id": ids["Apple"]}]
    r = client.post("/api/compare", json={"instruments": ins, "ccy": "USD"}, headers=H).json()
    petr, aapl = r["columns"]
    assert petr["currency"] == "USD" and petr["native_currency"] == "BRL" and aapl["fiscal_year_end"] == "0930"
    p = petr["periods"][-1]
    assert p["fx"]["flows"]["convention"].startswith("PTAX venda média") and p["fx"]["balances"]["convention"].startswith("PTAX venda de fechamento")
