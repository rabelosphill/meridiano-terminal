"""Comparação, métricas por emissor, premissas padrão de DCF, séries macro e cobertura de abas."""
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from ..calc import metrics as M
from ..db import q, q1
from . import statements as S
from .templates import SECTOR_PACKS


def issuer(issuer_id: str) -> dict:
    return q1("SELECT * FROM issuer WHERE id=%s", (issuer_id,))


def _d(cell: Optional[dict]) -> Optional[Decimal]:
    return Decimal(cell["v"]) if cell and cell.get("v") is not None else None


def _prov(cell: Optional[dict]) -> dict:
    if not cell:
        return {}
    return {k: cell.get(k) for k in ("fact_id", "basis", "formula", "inputs", "concept", "label") if cell.get(k) is not None}


def issuer_metrics(issuer_id: str, freq: str = "A", as_of: Optional[datetime] = None, n: int = 5) -> dict:
    iss = issuer(issuer_id)
    std = S.standardized(iss, freq, as_of, n)
    periods = sorted(std)[-n:]
    out = []
    for i, p in enumerate(periods):
        cur = std[p]
        prev = std.get(sorted(std)[sorted(std).index(p) - 1]) if sorted(std).index(p) > 0 else {}
        vals = {k: _d(c) for k, c in cur.items()}
        vals["revenue_prev"] = _d(prev.get("revenue")) if prev else None
        vals["equity_prev"] = _d(prev.get("equity")) if prev else None
        prov = {k: _prov(c) for k, c in cur.items()}
        row = {"period_end": p, "values": {k: (str(v) if v is not None else None) for k, v in vals.items()}, "provenance": prov, "metrics": {}}
        for code in ("revenue_growth", "gross_margin", "ebit_margin", "net_margin", "fcf", "fcf_margin", "total_debt", "net_debt", "roe", "roic"):
            row["metrics"][code] = M.compute(code, vals, prov)
        out.append(row)
    return {"issuer_id": issuer_id, "issuer": iss["short_name"], "freq": freq, "currency": "USD" if iss["reporting_std"] == "US-GAAP" else "BRL",
            "fiscal_year_end": iss["fiscal_year_end"], "periods": out, "library_version": M.LIB_VERSION}


def ptax(start: date, end: date, mode: str) -> Optional[dict]:
    if mode == "avg":
        r = q1("""SELECT avg(o.value) v, count(*) n, min(o.obs_date) a, max(o.obs_date) b FROM macro_observation o JOIN macro_series s ON s.id=o.series_id
                  WHERE s.code='BR.PTAX' AND o.obs_date BETWEEN %s AND %s AND o.value IS NOT NULL""", (start, end))
        return {"rate": r["v"], "n": r["n"], "from": str(r["a"]), "to": str(r["b"]), "convention": "PTAX venda média diária do período (fluxos)"} if r and r["v"] else None
    r = q1("""SELECT o.value v, o.obs_date d FROM macro_observation o JOIN macro_series s ON s.id=o.series_id
              WHERE s.code='BR.PTAX' AND o.obs_date <= %s AND o.value IS NOT NULL ORDER BY o.obs_date DESC LIMIT 1""", (end,))
    return {"rate": r["v"], "date": str(r["d"]), "convention": "PTAX venda de fechamento na data do balanço (saldos)"} if r else None


FLOW_KEYS = ["revenue", "gross_profit", "ebit", "net_income", "cfo", "capex"]
BAL_KEYS = ["cash", "total_assets", "equity", "debt_current", "debt_noncurrent"]


def compare(items: List[dict], ccy: str = "NATIVE", freq: str = "A", as_of: Optional[datetime] = None) -> dict:
    cols = []
    for it in items:
        iss = issuer(it["issuer_id"])
        native = "USD" if iss["reporting_std"] == "US-GAAP" else "BRL"
        target = native if ccy == "NATIVE" else ccy
        mets = issuer_metrics(it["issuer_id"], freq, as_of, 4)
        periods = []
        for p in mets["periods"]:
            end = date.fromisoformat(p["period_end"])
            start = date(end.year - 1, end.month, min(end.day, 28)) if freq in ("A", "LTM") else end
            conv_flow = conv_bal = None
            if target != native:
                conv_flow, conv_bal = ptax(start, end, "avg"), ptax(start, end, "close")
            vals = {}
            for k in FLOW_KEYS + BAL_KEYS + ["fcf", "net_debt"]:
                raw = p["values"].get(k) if k not in ("fcf", "net_debt") else p["metrics"][k]["value"]
                if raw is None:
                    vals[k] = None
                    continue
                v = Decimal(raw)
                conv = conv_bal if k in BAL_KEYS or k == "net_debt" else conv_flow
                if target != native:
                    if not conv:
                        vals[k] = None
                        continue
                    v = v * conv["rate"] if native == "USD" else v / conv["rate"]
                vals[k] = str(v)
            periods.append({"period_end": p["period_end"], "fiscal_label": f"FY{S._fy(iss, end)}", "calendar": f"{start}→{end}",
                            "values": vals, "ratios": {m: p["metrics"][m]["value"] for m in ("gross_margin", "ebit_margin", "net_margin", "fcf_margin", "revenue_growth", "roe")},
                            "fx": {"flows": conv_flow, "balances": conv_bal} if target != native else None,
                            "flags": sorted({f for m in p["metrics"].values() for f in m["flags"]})})
        cols.append({"ticker": it["ticker"], "exchange": it["exchange"], "issuer": iss["short_name"], "native_currency": native, "currency": target,
                     "fiscal_year_end": iss["fiscal_year_end"], "standard": iss["reporting_std"], "periods": periods})
    return {"currency_mode": ccy, "freq": freq, "as_of": as_of.isoformat() if as_of else None, "columns": cols,
            "notes": ["Exercícios fiscais diferentes são mostrados com datas explícitas; não há realinhamento de calendário.",
                      "Conversão: fluxos pela PTAX média do período, saldos pela PTAX de fechamento (BCB SGS 1).",
                      "Padrões contábeis distintos (US-GAAP x IFRS): EBIT CVM (3.05) inclui equivalência patrimonial."]}


def dcf_defaults(issuer_id: str) -> dict:
    iss = issuer(issuer_id)
    mets = issuer_metrics(issuer_id, "A", None, 3)
    last = mets["periods"][-1]
    v = {k: (Decimal(x) if x is not None else None) for k, x in last["values"].items()}
    ccy = mets["currency"]
    rev = v.get("revenue")
    shares = None
    shares_note = None
    if iss["reporting_std"] == "US-GAAP":
        r = q1("""SELECT value, id FROM fact WHERE issuer_id=%s AND concept='WeightedAverageNumberOfDilutedSharesOutstanding'
                  AND period_end=%s AND period_start IS NOT NULL ORDER BY published_at DESC LIMIT 1""", (issuer_id, last["period_end"]))
        if r:
            shares, shares_note = r["value"], f"média ponderada diluída do exercício (fato {r['id']}, 10-K)"
    else:
        lp = q1("""SELECT b.close FROM price_bar b JOIN listing l ON l.id=b.listing_id JOIN instrument i ON i.id=l.instrument_id
                   WHERE i.issuer_id=%s AND b.interval='1d' ORDER BY b.session_date DESC LIMIT 1""", (issuer_id,))
        so = shares_outstanding(issuer_id, Decimal(lp["close"]) if lp else None)
        shares, shares_note = so["value"], so["note"] + "; sem instrumentos dilutivos relevantes declarados"
    mino = q1("""SELECT value, id FROM fact WHERE issuer_id=%s AND concept='2.03.09' AND scope='consolidated' AND period_end=%s
                 ORDER BY published_at DESC LIMIT 1""", (issuer_id, last["period_end"])) if iss["reporting_std"] != "US-GAAP" else None
    tax_rate = (-(v["tax"]) / v["pretax"]) if v.get("tax") is not None and v.get("pretax") else Decimal("0.25")
    nd = Decimal(last["metrics"]["net_debt"]["value"]) if last["metrics"]["net_debt"]["value"] else Decimal(0)
    pct = lambda a: (abs(a) / rev).quantize(Decimal("0.0001")) if a is not None and rev else Decimal("0")
    ebit_m = (v["ebit"] / rev).quantize(Decimal("0.0001")) if v.get("ebit") is not None and rev else Decimal("0.2")
    return {
        "inputs": {
            "currency": ccy, "basis": "nominal", "base_revenue": str(rev), "growth": ["0.03"] * 5, "ebit_margin": [str(ebit_m)] * 5,
            "tax_rate": str(tax_rate.quantize(Decimal("0.0001"))), "capex_pct_rev": str(pct(v.get("capex"))), "da_pct_rev": str(pct(v.get("da"))),
            "nwc_pct_rev": "0.05", "wacc": "0.12" if ccy == "BRL" else "0.09", "g": "0.04" if ccy == "BRL" else "0.025",
            "wacc_currency": ccy, "wacc_basis": "nominal", "net_debt": str(nd), "minorities": str(mino["value"]) if mino else "0",
            "other_adjustments": {}, "diluted_shares": str(shares or 1), "share_convention": shares_note or "não disponível",
        },
        "provenance": {
            "base_revenue": last["provenance"].get("revenue"), "ebit_margin": "EBIT/receita do último exercício (dado reportado)",
            "tax_rate": "−IR/LAIR do último exercício", "capex_pct_rev": "|capex|/receita do último exercício", "da_pct_rev": "D&A/receita do último exercício",
            "net_debt": last["metrics"]["net_debt"], "minorities": {"fact_id": mino["id"]} if mino else None,
            "wacc": "PREMISSA DO USUÁRIO — valor inicial editável, não é estimativa de mercado", "g": "PREMISSA DO USUÁRIO",
            "growth": "PREMISSA DO USUÁRIO", "nwc_pct_rev": "PREMISSA DO USUÁRIO", "diluted_shares": shares_note,
        },
        "base_period": last["period_end"],
    }


def macro_series(code: str, as_of: Optional[datetime] = None, limit: int = 400) -> Optional[dict]:
    from ..connectors.macro import PUBLICATION_RULE
    s = q1("SELECT s.*, src.name source_name, src.license, src.url source_url FROM macro_series s JOIN source src ON src.code=s.source WHERE s.code=%s", (code,))
    if not s:
        return None
    sql = """SELECT DISTINCT ON (o.obs_date) o.obs_date, o.value, o.published_at, o.ingested_at, o.vintage, r.request, r.fetched_at, r.mode
             FROM macro_observation o LEFT JOIN raw_payload r ON r.id=o.raw_payload_id WHERE o.series_id=%s"""
    args: list = [s["id"]]
    if as_of:
        sql += " AND o.published_at <= %s"
        args.append(as_of)
    sql += " ORDER BY o.obs_date DESC, o.vintage DESC LIMIT %s"
    args.append(limit)
    obs = q(sql, args)
    return {"code": code, "name": s["name"], "unit": s["unit"], "frequency": s["frequency"], "source": s["source"], "source_name": s["source_name"],
            "source_key": s["source_key"], "license": s["license"], "notes": s["notes"], "publication_rule": PUBLICATION_RULE[code][0],
            "as_of": as_of.isoformat() if as_of else None,
            "observations": [{"date": str(o["obs_date"]), "value": str(o["value"]) if o["value"] is not None else None,
                              "published_at": o["published_at"].isoformat(), "ingested_at": o["ingested_at"].isoformat(), "vintage": o["vintage"],
                              "payload": o["request"], "payload_mode": o["mode"]} for o in obs]}


TABS = [("summary", "Resumo"), ("business", "Negócio"), ("financials", "Demonstrações"), ("cash", "Caixa"), ("debt", "Dívida"),
        ("estimates", "Estimativas"), ("valuation", "Valuation"), ("peers", "Pares"), ("holders", "Acionistas"), ("events", "Eventos"),
        ("options", "Opções"), ("documents", "Documentos"), ("thesis", "Tese")]


def tabs(ctx: dict) -> List[dict]:
    has_fund = bool(ctx.get("coverage"))
    kind = ctx["instrument"]["kind"]
    req = {
        "estimates": "Requer contrato de consenso (ex.: LSEG I/B/E/S, FactSet, S&P Capital IQ). Nenhum consenso é exibido sem licença.",
        "holders": "Requer conector de Formulário de Referência (CVM, item 15) / 13F (SEC) — próximo ciclo.",
        "options": "Requer feed de opções licenciado (B3 UMDF / OPRA). Modelo do instrumento já suporta strike, vencimento e multiplicador.",
        "business": None, "events": None,
    }
    out = []
    for code, label in TABS:
        enabled = True
        reason = None
        if code in ("financials", "cash", "debt", "valuation", "documents") and not has_fund:
            enabled, reason = False, "Sem demonstrações carregadas para este emissor (cobertura: SEC EDGAR p/ EUA, CVM p/ Brasil)."
        if code in ("estimates", "holders", "options"):
            enabled, reason = False, req[code]
        if code == "peers" and kind not in ("equity_common", "equity_pref", "adr"):
            enabled, reason = False, "Pares se aplicam a ações."
        out.append({"code": code, "label": label, "enabled": enabled, "requires": reason})
    return out


def sector_pack(iss: Optional[dict]) -> Optional[dict]:
    if not iss:
        return None
    p = SECTOR_PACKS.get(iss["sector_pack"], SECTOR_PACKS["generic"])
    return {"code": iss["sector_pack"], "label": p["label"],
            "priority": [{"key": k, "label": l, "available": req is None, "requires": req} for k, l, req in p["priority"]]}


def shares_outstanding(issuer_id: str, price: Optional[Decimal] = None) -> dict:
    """Ações em circulação (total − tesouraria) da composição do capital da CVM.
    A CVM não informa a escala: se preço × ações ÷ PL < 0,01 e ×1000 der um P/VP plausível (0,05–50),
    a quantidade foi informada em milhares — corrigimos e SINALIZAMOS como inferido."""
    t = q1("SELECT value, period_end, id FROM fact WHERE issuer_id=%s AND concept='shares_total' ORDER BY period_end DESC, published_at DESC LIMIT 1", (issuer_id,))
    if not t:
        return {"value": None, "note": "composição do capital não disponível"}
    tr = q1("SELECT value FROM fact WHERE issuer_id=%s AND concept='shares_treasury' AND period_end=%s ORDER BY published_at DESC LIMIT 1", (issuer_id, t["period_end"]))
    v = t["value"] - (tr["value"] if tr else 0)
    note = f"ações totais − tesouraria em {t['period_end']} (CVM composição do capital, fato {t['id']})"
    eq = q1("SELECT value FROM fact WHERE issuer_id=%s AND concept='2.03' AND scope='consolidated' ORDER BY period_end DESC, published_at DESC LIMIT 1", (issuer_id,))
    if price and eq and eq["value"] and eq["value"] > 0 and v > 0:
        pb = price * v / eq["value"]
        if pb < Decimal("0.01") and Decimal("0.05") <= pb * 1000 <= 50:
            v = v * 1000
            note += " · ESCALA INFERIDA: quantidade informada em milhares (P/VP implausível na escala unitária)"
    return {"value": v, "note": note, "as_of": str(t["period_end"])}
