"""Alertas com condição matemática explícita, modo intrabar × fechamento confirmado e política de deduplicação.

Rompimento: a janela de referência são as N sessões ANTERIORES — a barra avaliada nunca entra no máximo/mínimo.
Deduplicação: 'once' = só o primeiro disparo da regra; 'once_per_bar' = no máximo 1 por barra; 'every' = toda avaliação
que satisfaz a condição (útil só intrabar).
"""
from typing import Dict, List, Optional

from . import ta


def describe(kind: str, p: dict, mode: str) -> str:
    when = "no fechamento confirmado" if mode == "close" else "durante a barra (intrabar)"
    if kind == "breakout_high":
        ref = "fechamento" if mode == "close" else "máxima corrente"
        return f"{ref} da sessão acima da maior máxima das {p['n']} sessões anteriores (exclui a sessão atual), {when}"
    if kind == "breakout_low":
        ref = "fechamento" if mode == "close" else "mínima corrente"
        return f"{ref} da sessão abaixo da menor mínima das {p['n']} sessões anteriores (exclui a sessão atual), {when}"
    if kind == "price_cross":
        return f"preço cruza {'para cima' if p.get('dir', 'up') == 'up' else 'para baixo'} de {p['level']} {when}: anterior {'≤' if p.get('dir','up')=='up' else '≥'} nível e atual {'>' if p.get('dir','up')=='up' else '<'} nível"
    if kind == "ma_cross":
        return f"fechamento cruza {'acima' if p.get('dir', 'up') == 'up' else 'abaixo'} da média {p.get('type','sma').upper()}({p['n']}) {when}"
    if kind == "rsi_level":
        return f"RSI({p.get('n', 14)}) cruza {'acima' if p.get('dir', 'up') == 'up' else 'abaixo'} de {p['level']} {when}"
    if kind == "rel_volume":
        return f"volume ÷ média das {p.get('n', 20)} sessões anteriores ≥ {p['k']} {when}"
    return kind


def _hit(kind: str, p: dict, mode: str, bars: List[dict], i: int, cache: dict) -> Optional[dict]:
    b, prev = bars[i], bars[i - 1] if i > 0 else None
    c = float(b["close"]); h = float(b["high"]); l = float(b["low"])
    if kind in ("breakout_high", "breakout_low"):
        n = int(p["n"])
        if i < n:
            return None
        window = bars[i - n:i]                         # apenas sessões anteriores
        if kind == "breakout_high":
            ref = max(float(x["high"]) for x in window)
            val = c if mode == "close" else h
            return {"value": val, "reference": ref} if val > ref else None
        ref = min(float(x["low"]) for x in window)
        val = c if mode == "close" else l
        return {"value": val, "reference": ref} if val < ref else None
    if kind == "price_cross":
        L, up = float(p["level"]), p.get("dir", "up") == "up"
        if prev is None:
            return None
        pc = float(prev["close"])
        cur = c if mode == "close" else (h if up else l)
        return {"value": cur, "level": L} if (up and pc <= L < cur) or (not up and pc >= L > cur) else None
    if kind == "ma_cross":
        key = ("ma", p.get("type", "sma"), int(p["n"]))
        if key not in cache:
            closes = [float(x["close"]) for x in bars]
            cache[key] = (ta.ema if p.get("type") == "ema" else ta.sma)(closes, int(p["n"]))
        m = cache[key]
        if prev is None or m[i] is None or m[i - 1] is None:
            return None
        up = p.get("dir", "up") == "up"
        pc = float(prev["close"])
        return {"value": c, "ma": m[i]} if (up and pc <= m[i - 1] and c > m[i]) or (not up and pc >= m[i - 1] and c < m[i]) else None
    if kind == "rsi_level":
        key = ("rsi", int(p.get("n", 14)))
        if key not in cache:
            cache[key] = ta.rsi([float(x["close"]) for x in bars], int(p.get("n", 14)))
        r = cache[key]
        if r[i] is None or r[i - 1] is None:
            return None
        L, up = float(p["level"]), p.get("dir", "up") == "up"
        return {"rsi": r[i]} if (up and r[i - 1] <= L < r[i]) or (not up and r[i - 1] >= L > r[i]) else None
    if kind == "rel_volume":
        key = ("rv", int(p.get("n", 20)))
        if key not in cache:
            cache[key] = ta.rel_volume([float(x["volume"] or 0) for x in bars], int(p.get("n", 20)))
        rv = cache[key][i]
        return {"rel_volume": rv} if rv is not None and rv >= float(p["k"]) else None
    raise KeyError(kind)


def evaluate(kind: str, params: dict, mode: str, dedupe: str, bars: List[dict], already_fired: Optional[set] = None) -> List[dict]:
    """Avalia a regra barra a barra (backtest ou nova barra). Retorna disparos já deduplicados."""
    fired = set(already_fired or set())
    out = []
    cache: dict = {}
    for i in range(len(bars)):
        hit = _hit(kind, params, mode, bars, i, cache)
        if not hit:
            continue
        key = str(bars[i]["session_date"])
        if dedupe == "once" and (fired or out):
            break
        if dedupe == "once_per_bar" and key in fired:
            continue
        fired.add(key)
        out.append({"session_date": key, **hit})
    return out


def evaluate_ticks(kind: str, params: dict, dedupe: str, history: List[dict], ticks: List[float]) -> List[dict]:
    """Intrabar: avalia cada tick como máxima/mínima corrente da barra em formação."""
    out = []
    hi = lo = None
    for t in ticks:
        hi = t if hi is None else max(hi, t)
        lo = t if lo is None else min(lo, t)
        bar = {"session_date": "intrabar", "open": ticks[0], "high": hi, "low": lo, "close": t, "volume": 0}
        hit = _hit(kind, params, "intrabar", history + [bar], len(history), {})
        if hit:
            if dedupe in ("once", "once_per_bar") and out:
                continue
            out.append({"tick": t, **hit})
    return out
