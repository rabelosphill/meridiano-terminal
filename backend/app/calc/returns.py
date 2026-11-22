"""Retornos com eventos corporativos, conversão de ADR e estatísticas de risco.

Convenções:
- Preços de entrada são NÃO ajustados (como negociados). Cada evento é aplicado uma única vez;
  série já marcada como ajustada é rejeitada (evita ajuste duplo).
- Retorno total diário: (P_t × fator_split_t + D_t) / P_{t-1} − 1, com fator_split = novas/antigas
  quando t é a data ex do split e D_t o dividendo por ação na data ex.
- FX tipado: Quote(base, quote, rate) significa 1 base = rate quote. USD/BRL 5,80 = 1 USD vale 5,80 BRL.
"""
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple


class CurrencyMismatch(Exception):
    pass


class DoubleAdjustment(Exception):
    pass


@dataclass(frozen=True)
class FxQuote:
    base: str
    quote: str
    rate: Decimal
    observed_at: str = ""

    def convert(self, amount: Decimal, from_ccy: str, to_ccy: str) -> Decimal:
        if (from_ccy, to_ccy) == (self.base, self.quote):
            return amount * self.rate
        if (from_ccy, to_ccy) == (self.quote, self.base):
            return amount / self.rate
        raise CurrencyMismatch(f"cotação {self.base}/{self.quote} não converte {from_ccy}->{to_ccy}")


@dataclass(frozen=True)
class AdrTerms:
    adr_units: Decimal
    underlying_units: Decimal
    underlying_ccy: str
    adr_ccy: str = "USD"

    def __post_init__(self):
        if self.adr_units <= 0 or self.underlying_units <= 0:
            raise ValueError("razão de ADR deve ser positiva")


@dataclass
class PriceSeries:
    dates: List[date]
    prices: List[Decimal]
    currency: str
    adjusted: bool = False


@dataclass(frozen=True)
class Action:
    id: str
    kind: str              # split | cash_dividend
    ex_date: date
    ratio: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None


def adr_implied_price(local_price: Decimal, local_ccy: str, terms: AdrTerms, fx: FxQuote) -> Decimal:
    """Preço implícito do ADR = preço local × (ações subjacentes por ADR) convertido p/ moeda do ADR."""
    if local_ccy != terms.underlying_ccy:
        raise CurrencyMismatch(f"preço local em {local_ccy}, subjacente negocia em {terms.underlying_ccy}")
    per_adr_local = local_price * terms.underlying_units / terms.adr_units
    return fx.convert(per_adr_local, local_ccy, terms.adr_ccy)


def adr_premium(adr_price: Decimal, implied: Decimal) -> Decimal:
    return adr_price / implied - 1


def parity_ok(adr_price: Decimal, implied: Decimal, tolerance: Decimal = Decimal("0.05")) -> bool:
    """Prêmio/desconto acima da tolerância indica razão ou moeda invertida (ou mercado com problema)."""
    return abs(adr_premium(adr_price, implied)) <= tolerance


def total_returns(series: PriceSeries, actions: Sequence[Action]) -> List[Tuple[date, Decimal]]:
    if series.adjusted:
        raise DoubleAdjustment("série já ajustada: eventos corporativos não podem ser reaplicados")
    seen = set()
    by_date: Dict[date, List[Action]] = {}
    for a in actions:
        if a.id in seen:
            raise DoubleAdjustment(f"evento {a.id} repetido")
        seen.add(a.id)
        if a.kind == "cash_dividend" and a.currency and a.currency != series.currency:
            raise CurrencyMismatch(f"dividendo em {a.currency}, preço em {series.currency}")
        by_date.setdefault(a.ex_date, []).append(a)
    out = []
    for i in range(1, len(series.dates)):
        d = series.dates[i]
        p0, p1 = series.prices[i - 1], series.prices[i]
        factor, div = Decimal(1), Decimal(0)
        for a in by_date.get(d, []):
            if a.kind == "split":
                factor *= a.ratio
            elif a.kind == "cash_dividend":
                div += a.amount * factor
        out.append((d, (p1 * factor + div) / p0 - 1))
    return out


def cumulative(rets: Sequence[Tuple[date, Decimal]]) -> Decimal:
    acc = Decimal(1)
    for _, r in rets:
        acc *= (1 + r)
    return acc - 1


def volatility(rets: Sequence[Decimal], periods_per_year: int = 252) -> float:
    xs = [float(r) for r in rets]
    if len(xs) < 2:
        return float("nan")
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) * math.sqrt(periods_per_year)


def max_drawdown(levels: Sequence[float]) -> float:
    peak, mdd = -float("inf"), 0.0
    for x in levels:
        peak = max(peak, x)
        mdd = min(mdd, x / peak - 1)
    return mdd


def beta(asset: Sequence[float], bench: Sequence[float]) -> float:
    n = min(len(asset), len(bench))
    a, b = asset[:n], bench[:n]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)
    var = sum((y - mb) ** 2 for y in b) / (n - 1)
    return cov / var
