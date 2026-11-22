"""Rastreador (SCAN): filtros combináveis com explicação por ativo, data de corte e exclusões declaradas.

Exemplo reproduzível (EXAMPLE_BR): ações brasileiras com volume financeiro médio de 20 sessões > R$ 10 mi,
fechamento acima da média de 200 sessões e retorno de PREÇO em 63 sessões acima do Ibovespa.
Ibovespa: não há licença para o índice; usamos o ETF BOVA11 (B3 COTAHIST) como proxy declarado.
"""
from datetime import date
from typing import Dict, List, Optional

from ..calc import ta
from ..db import q, q1

EXAMPLE_BR = {
    "name": "Liquidez + tendência + força vs Ibovespa",
    "universe": {"country": "BR", "kinds": ["equity_common", "equity_pref", "equity_unit"]},
    "as_of": None,
    "benchmark": "BOVA11",
    "filters": [
        {"field": "avg_fin_volume", "n": 20, "op": ">", "value": 10_000_000},
        {"field": "close_vs_sma", "n": 200, "op": ">", "value": 0},
        {"field": "return_vs_bench", "n": 63, "op": ">", "value": 0},
    ],
    "sort": {"field": "return", "n": 63, "desc": True},
}

FIELDS = {
    "avg_fin_volume": "volume financeiro médio (R$) das n sessões até a data de corte",
    "close_vs_sma": "fechamento ÷ SMA(n) − 1",
    "return": "retorno de preço em n sessões (fechamento/fechamento n sessões antes − 1)",
    "return_vs_bench": "retorno de preço em n sessões menos o do benchmark nas mesmas datas",
    "rsi": "RSI(n) de Wilder",
    "rel_volume": "volume ÷ média das n sessões anteriores",
    "breakout_high": "fechamento acima da maior máxima das n sessões anteriores (1 = sim)",
    "close": "último fechamento (R$)",
}


def _bars_by_listing(as_of: Optional[date], kinds: List[str], need: int) -> Dict[str, dict]:
    rows = q("""SELECT b.listing_id, l.ticker, i.name, i.kind, b.session_date, b.close, b.high, b.low, b.volume, b.fin_volume, b.location->>'dismes' dismes
                FROM price_bar b JOIN listing l ON l.id=b.listing_id JOIN instrument i ON i.id=l.instrument_id
                WHERE b.interval='1d' AND l.exchange_mic='BVMF' AND i.kind = ANY(%s) AND (%s::date IS NULL OR b.session_date <= %s)
                ORDER BY b.listing_id, b.session_date""", (kinds, as_of, as_of))
    out: Dict[str, dict] = {}
    for r in rows:
        e = out.setdefault(str(r["listing_id"]), {"ticker": r["ticker"], "name": r["name"], "kind": r["kind"], "bars": []})
        e["bars"].append(r)
    return out


def _value(field: str, n: int, bars: List[dict], bench: Dict[date, float]) -> Optional[float]:
    if field == "close":
        return float(bars[-1]["close"])
    if len(bars) < n + 1 and field not in ("avg_fin_volume", "close_vs_sma"):
        return None
    if field == "avg_fin_volume":
        w = bars[-n:]
        return sum(float(b["fin_volume"] or 0) for b in w) / n if len(w) == n else None
    if field == "close_vs_sma":
        if len(bars) < n:
            return None
        return float(bars[-1]["close"]) / (sum(float(b["close"]) for b in bars[-n:]) / n) - 1
    if field == "return":
        return float(bars[-1]["close"]) / float(bars[-1 - n]["close"]) - 1
    if field == "return_vs_bench":
        d0, d1 = bars[-1 - n]["session_date"], bars[-1]["session_date"]
        if d0 not in bench or d1 not in bench:
            return None
        return (float(bars[-1]["close"]) / float(bars[-1 - n]["close"]) - 1) - (bench[d1] / bench[d0] - 1)
    if field == "rsi":
        return ta.rsi([float(b["close"]) for b in bars], n)[-1]
    if field == "rel_volume":
        return ta.rel_volume([float(b["volume"] or 0) for b in bars], n)[-1]
    if field == "breakout_high":
        return 1.0 if float(bars[-1]["close"]) > max(float(b["high"]) for b in bars[-1 - n:-1]) else 0.0
    raise KeyError(field)


def suspected_events(bars: List[dict], lo: float = 0.6, hi: float = 1.67) -> List[dict]:
    """Salto de preço extremo entre sessões consecutivas COINCIDENTE com mudança do número de distribuição (DISMES)
    da B3 indica desdobramento/grupamento/bonificação sem fator de ajuste disponível — não usar em retornos."""
    out = []
    for a, b in zip(bars, bars[1:]):
        r = float(b["close"]) / float(a["close"])
        if (r < lo or r > hi) and a.get("dismes") != b.get("dismes"):
            out.append({"date": str(b["session_date"]), "from": float(a["close"]), "to": float(b["close"]), "dismes_from": a.get("dismes"), "dismes_to": b.get("dismes")})
    return out


def _need(spec) -> int:
    return max([f.get("n", 1) + 1 for f in spec["filters"]] + [spec.get("sort", {}).get("n", 1) + 1])


def run(spec: dict) -> dict:
    as_of = date.fromisoformat(spec["as_of"]) if spec.get("as_of") else None
    kinds = spec.get("universe", {}).get("kinds", EXAMPLE_BR["universe"]["kinds"])
    need = _need(spec)
    data = _bars_by_listing(as_of, kinds, need)
    bt = spec.get("benchmark", "BOVA11")
    brow = q("""SELECT b.session_date, b.close FROM price_bar b JOIN listing l ON l.id=b.listing_id WHERE l.ticker=%s AND b.interval='1d'
                AND (%s::date IS NULL OR b.session_date <= %s) ORDER BY b.session_date""", (bt, as_of, as_of))
    bench = {r["session_date"]: float(r["close"]) for r in brow}
    cut = max(bench) if bench else as_of
    passed, excluded, failed = [], [], 0
    for lid, e in data.items():
        bars = [b for b in e["bars"] if b["session_date"] <= cut] if cut else e["bars"]
        if not bars or bars[-1]["session_date"] != cut:
            excluded.append({"ticker": e["ticker"], "reason": f"sem negócio na data de corte {cut} (última sessão {bars[-1]['session_date'] if bars else '—'})"})
            continue
        if len(bars) < need:
            excluded.append({"ticker": e["ticker"], "reason": f"histórico insuficiente: {len(bars)} sessões < {need} necessárias"})
            continue
        suspect = suspected_events(bars[-need:])
        if suspect and any(f["field"] in ("return", "return_vs_bench", "close_vs_sma", "rsi", "breakout_high") for f in spec["filters"]):
            excluded.append({"ticker": e["ticker"], "reason": "provável evento corporativo não ajustado na janela: " + "; ".join(
                f"{x['date']} fechamento {x['from']} → {x['to']} (distribuição {x['dismes_from']}→{x['dismes_to']})" for x in suspect)})
            continue
        checks, ok = [], True
        for f in spec["filters"]:
            v = _value(f["field"], int(f.get("n", 1)), bars, bench)
            res = v is not None and ((v > f["value"]) if f["op"] == ">" else (v < f["value"]) if f["op"] == "<" else (v >= f["value"]) if f["op"] == ">=" else (v <= f["value"]))
            checks.append({"field": f["field"], "n": f.get("n"), "value": v, "op": f["op"], "threshold": f["value"], "pass": res})
            ok = ok and res
        if not ok:
            failed += 1
            continue
        s = spec.get("sort")
        extreme = [f"{b['session_date']}: {float(a['close'])} → {float(b['close'])}" for a, b in zip(bars[-need:], bars[-need + 1:])
                   if abs(float(b["close"]) / float(a["close"]) - 1) > 0.4]
        passed.append({"warnings": [f"movimento diário > 40% sem mudança de distribuição — verificar: {x}" for x in extreme],
                       "listing_id": lid, "ticker": e["ticker"], "name": e["name"], "kind": e["kind"], "close": float(bars[-1]["close"]),
                       "sort_value": _value(s["field"], int(s.get("n", 1)), bars, bench) if s else None, "why": checks})
    if spec.get("sort"):
        passed.sort(key=lambda r: (r["sort_value"] is None, -(r["sort_value"] or 0) if spec["sort"].get("desc", True) else (r["sort_value"] or 0)))
    bench_ret = {}
    for f in spec["filters"]:
        if f["field"] == "return_vs_bench" and len(brow) > f["n"]:
            bench_ret[f["n"]] = float(brow[-1]["close"]) / float(brow[-1 - f["n"]]["close"]) - 1
    return {"spec": spec, "cut_date": str(cut), "currency": "BRL", "universe_size": len(data), "passed": passed, "failed": failed,
            "excluded": excluded, "benchmark": {"ticker": bt, "note": "Ibovespa representado pelo ETF BOVA11 (proxy: inclui taxa e erro de rastreamento); índice oficial requer licença B3",
                                                "returns": bench_ret},
            "conventions": {"price": "fechamento bruto B3 (sem ajuste por proventos)", "sessions": "contadas em pregões da B3 até a data de corte, inclusive",
                            "fields": {f["field"]: FIELDS[f["field"]] for f in spec["filters"]}},
            "source": "B3 COTAHIST (mercado à vista, lote padrão)"}
