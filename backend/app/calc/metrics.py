"""Biblioteca de métricas determinística. Cada métrica declara fórmula, unidade, convenção,
campos necessários, versão e política para ausências. Aritmética em Decimal."""
from dataclasses import dataclass
from decimal import Decimal, getcontext
from typing import Callable, Dict, List, Optional

getcontext().prec = 34
LIB_VERSION = "1.0.0"


@dataclass(frozen=True)
class Metric:
    code: str
    name: str
    formula: str
    unit: str
    convention: str
    requires: List[str]
    missing_policy: str           # 'null' = retorna ausente e lista campos; nunca imputa zero
    version: str
    fn: Callable[[Dict[str, Decimal]], Optional[Decimal]]
    limitation: Optional[Callable[[Dict[str, Decimal]], Optional[str]]] = None


def _div(a: Decimal, b: Decimal) -> Optional[Decimal]:
    return None if b == 0 else a / b


def _neg_denominator(field: str, label: str):
    def check(v):
        return f"{label} ≤ 0: múltiplo sem significado econômico" if v.get(field) is not None and v[field] <= 0 else None
    return check


METRICS: Dict[str, Metric] = {m.code: m for m in [
    Metric("revenue_growth", "Crescimento da receita a/a", "receita_t / receita_{t-1} − 1", "%", "períodos equivalentes (FY vs FY, Q vs mesmo Q)",
           ["revenue", "revenue_prev"], "null", "1.0", lambda v: _div(v["revenue"], v["revenue_prev"]) - 1 if v["revenue_prev"] else None,
           _neg_denominator("revenue_prev", "Receita anterior")),
    Metric("gross_margin", "Margem bruta", "lucro_bruto / receita", "%", "mesmo período", ["gross_profit", "revenue"], "null", "1.0",
           lambda v: _div(v["gross_profit"], v["revenue"])),
    Metric("ebit_margin", "Margem operacional", "EBIT / receita", "%", "EBIT conforme demonstração (CVM 3.05 inclui equivalência patrimonial)",
           ["ebit", "revenue"], "null", "1.0", lambda v: _div(v["ebit"], v["revenue"])),
    Metric("net_margin", "Margem líquida", "lucro_líquido / receita", "%", "lucro consolidado", ["net_income", "revenue"], "null", "1.0",
           lambda v: _div(v["net_income"], v["revenue"])),
    Metric("fcf", "Fluxo de caixa livre (FCF simples)", "caixa_operacional + capex", "moeda",
           "Definição explícita: CFO − aquisições de imobilizado/intangível (capex com sinal negativo). Não deduz arrendamentos nem juros pagos em financiamento.",
           ["cfo", "capex"], "null", "1.0", lambda v: v["cfo"] + v["capex"]),
    Metric("fcf_margin", "Margem FCF", "FCF / receita", "%", "mesmo período", ["cfo", "capex", "revenue"], "null", "1.0",
           lambda v: _div(v["cfo"] + v["capex"], v["revenue"])),
    Metric("total_debt", "Dívida bruta", "dívida_CP + dívida_LP (+ commercial paper)", "moeda",
           "Saldo no fim do período; empréstimos e financiamentos; exclui arrendamentos (IFRS 16) salvo se o emissor os incluir na linha",
           ["debt_current", "debt_noncurrent"], "null", "1.0",
           lambda v: v["debt_current"] + v["debt_noncurrent"] + v.get("commercial_paper", Decimal(0))),
    Metric("net_debt", "Dívida líquida", "dívida_bruta − caixa_e_equivalentes", "moeda", "saldos na mesma data; não inclui aplicações de LP",
           ["debt_current", "debt_noncurrent", "cash"], "null", "1.0",
           lambda v: v["debt_current"] + v["debt_noncurrent"] + v.get("commercial_paper", Decimal(0)) - v["cash"]),
    Metric("roe", "ROE", "lucro_controladores / PL_médio", "%", "PL médio = (PL_t + PL_{t-1})/2; períodos anuais",
           ["net_income_parent", "equity", "equity_prev"], "null", "1.0",
           lambda v: _div(v["net_income_parent"], (v["equity"] + v["equity_prev"]) / 2),
           _neg_denominator("equity", "Patrimônio líquido")),
    Metric("roic", "ROIC", "EBIT × (1 − alíquota_efetiva) / (dívida_bruta + PL − caixa)", "%",
           "capital investido no fim do período; alíquota efetiva = IR / LAIR do período", ["ebit", "tax", "pretax", "debt_current", "debt_noncurrent", "equity", "cash"],
           "null", "1.0",
           lambda v: _div(v["ebit"] * (1 + _div(v["tax"], v["pretax"])) if v["pretax"] else v["ebit"],
                          v["debt_current"] + v["debt_noncurrent"] + v.get("commercial_paper", Decimal(0)) + v["equity"] - v["cash"]),
           lambda v: "LAIR ≤ 0: alíquota efetiva indefinida" if v.get("pretax") is not None and v["pretax"] <= 0 else None),
    Metric("pe", "P/L", "preço × ações / lucro_controladores_LTM", "x", "preço e lucro na mesma moeda", ["price", "shares", "net_income_parent"],
           "null", "1.0", lambda v: _div(v["price"] * v["shares"], v["net_income_parent"]), _neg_denominator("net_income_parent", "Lucro")),
    Metric("ev_ebit", "EV/EBIT", "(valor_de_mercado + dívida_líquida) / EBIT_LTM", "x", "mesma moeda", ["price", "shares", "net_debt", "ebit"],
           "null", "1.0", lambda v: _div(v["price"] * v["shares"] + v["net_debt"], v["ebit"]), _neg_denominator("ebit", "EBIT")),
]}


def compute(code: str, values: Dict[str, Optional[Decimal]], provenance: Optional[Dict[str, dict]] = None) -> dict:
    m = METRICS[code]
    missing = [f for f in m.requires if values.get(f) is None]
    out = {"metric": code, "name": m.name, "formula": m.formula, "unit": m.unit, "convention": m.convention,
           "version": f"{LIB_VERSION}/{m.version}", "missing_policy": m.missing_policy,
           "inputs": {f: {"value": str(values[f]) if values.get(f) is not None else None, **((provenance or {}).get(f, {}))} for f in m.requires},
           "missing": missing, "flags": []}
    if missing:
        out["value"] = None
        return out
    lim = m.limitation(values) if m.limitation else None
    if lim:
        out["flags"].append(lim)
    try:
        v = m.fn(values)
    except (ZeroDivisionError, TypeError):
        v = None
    out["value"] = None if v is None else str(v)
    return out
