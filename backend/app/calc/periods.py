"""Conversões de período com validação: acumulado no ano (YTD) -> trimestre isolado; LTM.

Regras:
- Só subtrai YTDs do MESMO exercício (mesma data de início), mesmo escopo, mesma moeda/escala,
  e mesma conta (código + rótulo). Contas livres (ST_CONTA_FIXA='N') que mudaram de rótulo -> não comparável.
- Saldos (balanço) NUNCA são somados ou subtraídos entre períodos: LTM de saldo = último saldo.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import List, Optional


class NotComparable(Exception):
    pass


@dataclass
class PeriodValue:
    start: Optional[date]
    end: date
    value: Optional[Decimal]
    scope: str = "consolidated"
    currency: Optional[str] = None
    concept: str = ""
    label: str = ""
    fact_id: Optional[int] = None
    kind: str = "duration"          # duration | instant
    extra: dict = field(default_factory=dict)


def _check(a: PeriodValue, b: PeriodValue, label_strict: bool = True):
    if a.kind != "duration" or b.kind != "duration":
        raise NotComparable("saldo patrimonial não pode ser convertido por diferença de períodos")
    if a.start != b.start:
        raise NotComparable(f"exercícios diferentes: início {a.start} vs {b.start}")
    if a.scope != b.scope:
        raise NotComparable(f"escopos diferentes: {a.scope} vs {b.scope}")
    if a.currency != b.currency:
        raise NotComparable(f"moedas diferentes: {a.currency} vs {b.currency}")
    if a.concept != b.concept:
        raise NotComparable(f"contas diferentes: {a.concept} vs {b.concept}")
    if label_strict and a.label.strip().lower() != b.label.strip().lower():
        raise NotComparable(f"conta {a.concept} mudou de rótulo entre documentos: '{b.label}' vs '{a.label}'")


def quarter_from_ytd(cur: PeriodValue, prev: Optional[PeriodValue], label_strict: bool = True) -> dict:
    """cur = YTD até o fim do trimestre; prev = YTD até o trimestre anterior (None se Q1)."""
    if cur.value is None:
        return {"value": None, "formula": None, "missing": [f"{cur.concept} YTD {cur.end}"]}
    if prev is None:
        months = (cur.end.year - cur.start.year) * 12 + cur.end.month - cur.start.month + 1
        if months != 3:
            raise NotComparable("falta o YTD do trimestre anterior")
        return {"value": cur.value, "formula": f"Q = YTD({cur.start}→{cur.end})", "inputs": [cur.fact_id]}
    _check(cur, prev, label_strict)
    if prev.value is None:
        return {"value": None, "formula": None, "missing": [f"{prev.concept} YTD {prev.end}"]}
    return {"value": cur.value - prev.value,
            "formula": f"YTD({cur.start}→{cur.end}) − YTD({prev.start}→{prev.end})",
            "inputs": [cur.fact_id, prev.fact_id]}


def ltm_flow(fy_prev: PeriodValue, ytd_cur: PeriodValue, ytd_prev: PeriodValue) -> dict:
    """LTM = FY anterior + YTD atual − YTD do mesmo período do ano anterior."""
    for a, b in ((ytd_cur, ytd_prev),):
        if a.concept != b.concept or a.scope != b.scope or a.currency != b.currency:
            raise NotComparable("YTDs não comparáveis para LTM")
    if fy_prev.kind != "duration":
        raise NotComparable("LTM de saldo: use o último saldo")
    if any(x.value is None for x in (fy_prev, ytd_cur, ytd_prev)):
        return {"value": None, "missing": [x.end.isoformat() for x in (fy_prev, ytd_cur, ytd_prev) if x.value is None]}
    return {"value": fy_prev.value + ytd_cur.value - ytd_prev.value,
            "formula": f"FY({fy_prev.end}) + YTD({ytd_cur.end}) − YTD({ytd_prev.end})",
            "inputs": [fy_prev.fact_id, ytd_cur.fact_id, ytd_prev.fact_id]}


def ltm_balance(balances: List[PeriodValue]) -> dict:
    """Saldo em LTM = saldo mais recente. Somar 4 balanços é proibido."""
    if not balances:
        return {"value": None, "missing": ["saldo"]}
    if any(b.kind != "instant" for b in balances):
        raise NotComparable("ltm_balance recebe apenas saldos")
    last = max(balances, key=lambda b: b.end)
    return {"value": last.value, "formula": f"saldo em {last.end} (último disponível; saldos não são somados)", "inputs": [last.fact_id]}


def sum_balances(*_args, **_kw):
    raise NotComparable("Somar saldos patrimoniais de trimestres diferentes não tem significado econômico")
