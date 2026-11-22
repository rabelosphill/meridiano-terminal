"""DCF de FCFF descontado ao WACC, com ponte EV -> equity e validações.

FCFF_t = EBIT_t × (1 − t) + D&A_t − Capex_t − ΔNWC_t
TV_N   = FCFF_{N+1} / (WACC − g),  FCFF_{N+1} = FCFF_N × (1 + g)      (Gordon)
EV     = Σ FCFF_t / (1+WACC)^t + TV_N / (1+WACC)^N                     (desconto fim de período)
Equity = EV − dívida líquida − participação de não controladores + ajustes declarados
Por ação = Equity / ações plenamente diluídas (convenção: ações totais − tesouraria + diluição declarada).
"""
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional

from .metrics import LIB_VERSION

D = Decimal


class DcfError(ValueError):
    pass


@dataclass
class DcfInputs:
    currency: str
    basis: str                        # nominal | real
    base_revenue: D
    growth: List[D]                   # por ano projetado
    ebit_margin: List[D]
    tax_rate: D
    capex_pct_rev: D                  # positivo
    da_pct_rev: D
    nwc_pct_rev: D                    # capital de giro como % da receita (ΔNWC = pct × Δreceita)
    wacc: D
    g: D
    wacc_currency: str
    wacc_basis: str
    net_debt: D
    minorities: D = D(0)
    other_adjustments: Dict[str, D] = field(default_factory=dict)   # +/- declarados (ex.: provisões, investimentos)
    diluted_shares: D = D(1)
    share_convention: str = "ações totais − tesouraria (CVM composição do capital)"


def validate(i: DcfInputs):
    if i.currency != i.wacc_currency:
        raise DcfError(f"FCFF em {i.currency} descontado por WACC em {i.wacc_currency}")
    if i.basis != i.wacc_basis:
        raise DcfError(f"FCFF {i.basis} com WACC {i.wacc_basis}: bases devem coincidir")
    if i.wacc <= i.g:
        raise DcfError(f"WACC ({i.wacc}) deve ser maior que g ({i.g}) na perpetuidade")
    if not (len(i.growth) == len(i.ebit_margin) and len(i.growth) >= 1):
        raise DcfError("growth e ebit_margin devem ter o mesmo número de anos")
    if i.diluted_shares <= 0:
        raise DcfError("ações diluídas devem ser positivas")


def run(i: DcfInputs) -> dict:
    validate(i)
    rev_prev = i.base_revenue
    years, pv_sum = [], D(0)
    fcff = D(0)
    for t, (gr, mg) in enumerate(zip(i.growth, i.ebit_margin), start=1):
        rev = rev_prev * (1 + gr)
        ebit = rev * mg
        nopat = ebit * (1 - i.tax_rate)
        da = rev * i.da_pct_rev
        capex = rev * i.capex_pct_rev
        dnwc = (rev - rev_prev) * i.nwc_pct_rev
        fcff = nopat + da - capex - dnwc
        df = (1 + i.wacc) ** t
        pv = fcff / df
        pv_sum += pv
        years.append({"t": t, "revenue": rev, "ebit": ebit, "nopat": nopat, "da": da, "capex": capex, "dnwc": dnwc, "fcff": fcff, "discount_factor": df, "pv": pv})
        rev_prev = rev
    n = len(years)
    tv = fcff * (1 + i.g) / (i.wacc - i.g)
    pv_tv = tv / ((1 + i.wacc) ** n)
    ev = pv_sum + pv_tv
    adj_total = sum(i.other_adjustments.values(), D(0))
    equity = ev - i.net_debt - i.minorities + adj_total
    per_share = equity / i.diluted_shares
    return {
        "library_version": LIB_VERSION, "currency": i.currency, "basis": i.basis,
        "years": [{k: str(v) for k, v in y.items()} for y in years],
        "pv_explicit": str(pv_sum), "terminal_value": str(tv), "pv_terminal": str(pv_tv),
        "tv_share_of_ev": str(pv_tv / ev) if ev else None,
        "enterprise_value": str(ev),
        "bridge": [{"item": "Enterprise value", "value": str(ev)}, {"item": "(−) Dívida líquida", "value": str(-i.net_debt)},
                   {"item": "(−) Não controladores", "value": str(-i.minorities)}]
                  + [{"item": f"(±) {k}", "value": str(v)} for k, v in i.other_adjustments.items()]
                  + [{"item": "Equity value", "value": str(equity)}],
        "equity_value": str(equity), "diluted_shares": str(i.diluted_shares), "share_convention": i.share_convention,
        "per_share": str(per_share),
    }


def sensitivity(i: DcfInputs, waccs: List[D], gs: List[D]) -> dict:
    rows = []
    for w in waccs:
        row = []
        for g in gs:
            if w <= g:
                row.append(None)
                continue
            j = DcfInputs(**{**i.__dict__, "wacc": w, "g": g})
            row.append(run(j)["per_share"])
        rows.append({"wacc": str(w), "values": row})
    return {"g": [str(g) for g in gs], "rows": rows, "note": "célula vazia = WACC ≤ g (inválido)"}


def scenarios(i: DcfInputs, shocks: Optional[Dict[str, dict]] = None) -> Dict[str, dict]:
    shocks = shocks or {
        "pessimista": {"growth": D("-0.03"), "ebit_margin": D("-0.03"), "wacc": D("0.01")},
        "base": {},
        "otimista": {"growth": D("0.02"), "ebit_margin": D("0.02"), "wacc": D("-0.005")},
    }
    out = {}
    for name, s in shocks.items():
        j = DcfInputs(**{**i.__dict__,
                         "growth": [x + s.get("growth", D(0)) for x in i.growth],
                         "ebit_margin": [x + s.get("ebit_margin", D(0)) for x in i.ebit_margin],
                         "wacc": i.wacc + s.get("wacc", D(0))})
        r = run(j)
        out[name] = {"shock": {k: str(v) for k, v in s.items()}, "per_share": r["per_share"], "enterprise_value": r["enterprise_value"]}
    return out


def reverse(i: DcfInputs, target_per_share: D, lo: D = D("-0.5"), hi: D = D("1.0"), iters: int = 80) -> dict:
    """DCF reverso: crescimento anual constante implícito que iguala o valor por ação ao preço alvo."""
    def val(gr: D) -> D:
        j = DcfInputs(**{**i.__dict__, "growth": [gr] * len(i.growth)})
        return D(run(j)["per_share"])
    f_lo, f_hi = val(lo) - target_per_share, val(hi) - target_per_share
    if f_lo * f_hi > 0:
        return {"implied_growth": None, "note": "sem solução no intervalo [-50%, 100%] com as demais premissas"}
    for _ in range(iters):
        mid = (lo + hi) / 2
        f_mid = val(mid) - target_per_share
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return {"implied_growth": str((lo + hi) / 2), "target_per_share": str(target_per_share),
            "note": "crescimento anual constante nos anos explícitos; margens, WACC e g mantidos"}


def inputs_to_json(i: DcfInputs) -> dict:
    d = asdict(i)
    return {k: ([str(x) for x in v] if isinstance(v, list) else ({kk: str(vv) for kk, vv in v.items()} if isinstance(v, dict) else str(v)))
            for k, v in d.items()}


def inputs_from_json(d: dict) -> DcfInputs:
    dec = lambda x: D(str(x))
    return DcfInputs(
        currency=d["currency"], basis=d["basis"], base_revenue=dec(d["base_revenue"]),
        growth=[dec(x) for x in d["growth"]], ebit_margin=[dec(x) for x in d["ebit_margin"]],
        tax_rate=dec(d["tax_rate"]), capex_pct_rev=dec(d["capex_pct_rev"]), da_pct_rev=dec(d["da_pct_rev"]),
        nwc_pct_rev=dec(d["nwc_pct_rev"]), wacc=dec(d["wacc"]), g=dec(d["g"]),
        wacc_currency=d.get("wacc_currency", d["currency"]), wacc_basis=d.get("wacc_basis", d["basis"]),
        net_debt=dec(d["net_debt"]), minorities=dec(d.get("minorities", 0)),
        other_adjustments={k: dec(v) for k, v in d.get("other_adjustments", {}).items()},
        diluted_shares=dec(d["diluted_shares"]), share_convention=d.get("share_convention", "declarada pelo usuário"))
