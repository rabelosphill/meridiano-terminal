"""Biblioteca de estudos técnicos — determinística, com aquecimento explícito.

Convenções (expostas em STUDIES[*]['doc']):
- Fonte de preço padrão: fechamento. Observações ausentes não são preenchidas: se faltar uma barra do ativo, o
  estudo pula aquela data (não há forward-fill). Em comparações entre mercados, só entram datas com pregão em ambos.
- Valores dentro do aquecimento são None. O estudo é sempre calculado sobre o HISTÓRICO COMPLETO carregado; a janela
  visível/zoom apenas recorta a exibição — por isso um RSI ou média não muda ao aproximar o zoom.
- Wilder (RSI, ATR, ADX): suavização RMA com semente = média simples dos n primeiros valores.
- EMA: semente = média simples dos n primeiros valores; alfa = 2/(n+1).
- Volatilidade histórica: desvio-padrão amostral dos log-retornos × √252 (dias úteis).
"""
import math
from typing import Dict, List, Optional, Sequence

F = Optional[float]


def _f(x) -> F:
    return None if x is None else float(x)


def sma(x: Sequence[F], n: int) -> List[F]:
    out: List[F] = [None] * len(x)
    s, cnt = 0.0, 0
    for i, v in enumerate(x):
        s += v; cnt += 1
        if cnt > n:
            s -= x[i - n]; cnt = n
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(x: Sequence[F], n: int) -> List[F]:
    out: List[F] = [None] * len(x)
    start = next((i for i, v in enumerate(x) if v is not None), None)
    if start is None or len(x) - start < n:
        return out
    a = 2 / (n + 1)
    seed = sum(x[start:start + n]) / n
    out[start + n - 1] = seed
    prev = seed
    for i in range(start + n, len(x)):
        prev = a * x[i] + (1 - a) * prev
        out[i] = prev
    return out


def rma(x: Sequence[F], n: int) -> List[F]:
    """Média de Wilder."""
    out: List[F] = [None] * len(x)
    start = next((i for i, v in enumerate(x) if v is not None), None)
    if start is None or len(x) - start < n:
        return out
    prev = sum(x[start:start + n]) / n
    out[start + n - 1] = prev
    for i in range(start + n, len(x)):
        prev = (prev * (n - 1) + x[i]) / n
        out[i] = prev
    return out


def rsi(close: Sequence[float], n: int = 14) -> List[F]:
    gains: List[F] = [None] + [max(close[i] - close[i - 1], 0.0) for i in range(1, len(close))]
    losses: List[F] = [None] + [max(close[i - 1] - close[i], 0.0) for i in range(1, len(close))]
    ag, al = rma(gains, n), rma(losses, n)
    out: List[F] = []
    for g, l in zip(ag, al):
        if g is None or l is None:
            out.append(None)
        elif l == 0:
            out.append(100.0 if g > 0 else 50.0)
        else:
            out.append(100 - 100 / (1 + g / l))
    return out


def macd(close: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, List[F]]:
    ef, es = ema(close, fast), ema(close, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(ef, es)]
    sig = ema(line, signal)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return {"macd": line, "signal": sig, "hist": hist}


def true_range(h, l, c) -> List[F]:
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]


def atr(h, l, c, n: int = 14) -> List[F]:
    tr: List[F] = [None] + true_range(h, l, c)[1:]
    return rma(tr, n)


def adx(h, l, c, n: int = 14) -> Dict[str, List[F]]:
    L = len(c)
    pdm: List[F] = [None] + [(h[i] - h[i - 1]) if (h[i] - h[i - 1]) > (l[i - 1] - l[i]) and (h[i] - h[i - 1]) > 0 else 0.0 for i in range(1, L)]
    mdm: List[F] = [None] + [(l[i - 1] - l[i]) if (l[i - 1] - l[i]) > (h[i] - h[i - 1]) and (l[i - 1] - l[i]) > 0 else 0.0 for i in range(1, L)]
    tr: List[F] = [None] + true_range(h, l, c)[1:]
    str_, sp, sm = rma(tr, n), rma(pdm, n), rma(mdm, n)
    pdi = [100 * a / t if a is not None and t else None for a, t in zip(sp, str_)]
    mdi = [100 * a / t if a is not None and t else None for a, t in zip(sm, str_)]
    dx = [100 * abs(p - m) / (p + m) if p is not None and m is not None and (p + m) else (0.0 if p is not None else None) for p, m in zip(pdi, mdi)]
    return {"adx": rma(dx, n), "plus_di": pdi, "minus_di": mdi}


def stochastic(h, l, c, k: int = 14, smooth: int = 3, d: int = 3) -> Dict[str, List[F]]:
    raw: List[F] = [None] * len(c)
    for i in range(k - 1, len(c)):
        hh, ll = max(h[i - k + 1:i + 1]), min(l[i - k + 1:i + 1])
        raw[i] = 100 * (c[i] - ll) / (hh - ll) if hh != ll else 50.0
    kk = _sma_opt(raw, smooth)
    return {"k": kk, "d": _sma_opt(kk, d)}


def _sma_opt(x: Sequence[F], n: int) -> List[F]:
    out: List[F] = [None] * len(x)
    for i in range(len(x)):
        w = x[max(0, i - n + 1):i + 1]
        if len(w) == n and all(v is not None for v in w):
            out[i] = sum(w) / n
    return out


def roc(close, n: int = 12) -> List[F]:
    return [None] * n + [100 * (close[i] / close[i - n] - 1) for i in range(n, len(close))]


def bollinger(close, n: int = 20, k: float = 2.0) -> Dict[str, List[F]]:
    mid = sma(close, n)
    up, lo = [None] * len(close), [None] * len(close)
    for i in range(n - 1, len(close)):
        w = close[i - n + 1:i + 1]
        sd = math.sqrt(sum((v - mid[i]) ** 2 for v in w) / n)   # desvio populacional (convenção de Bollinger)
        up[i], lo[i] = mid[i] + k * sd, mid[i] - k * sd
    return {"mid": mid, "upper": up, "lower": lo}


def hist_vol(close, n: int = 20, periods: int = 252) -> List[F]:
    lr: List[F] = [None] + [math.log(close[i] / close[i - 1]) for i in range(1, len(close))]
    out: List[F] = [None] * len(close)
    for i in range(n, len(close)):
        w = lr[i - n + 1:i + 1]
        m = sum(w) / n
        out[i] = math.sqrt(sum((v - m) ** 2 for v in w) / (n - 1)) * math.sqrt(periods) * 100
    return out


def rel_volume(vol, n: int = 20) -> List[F]:
    """Volume da barra ÷ média das n barras ANTERIORES (exclui a barra atual)."""
    return [None] * n + [vol[i] / (sum(vol[i - n:i]) / n) if sum(vol[i - n:i]) else None for i in range(n, len(vol))]


def obv(close, vol) -> List[F]:
    out = [0.0]
    for i in range(1, len(close)):
        out.append(out[-1] + (vol[i] if close[i] > close[i - 1] else -vol[i] if close[i] < close[i - 1] else 0))
    return out


def vwap_session(bars: List[dict]) -> Dict[str, object]:
    """Barras diárias: a sessão inteira é a barra -> VWAP de sessão. Reinicia a cada sessão por construção.
    B3: usa PREMED (média ponderada de TODOS os negócios da sessão, calculada pela bolsa). Sem PREMED: aproximação
    (H+L+C)/3, declarada no campo 'method'."""
    exact = all(b.get("vwap") is not None for b in bars)
    vals = [_f(b["vwap"]) if b.get("vwap") is not None else (_f(b["high"]) + _f(b["low"]) + _f(b["close"])) / 3 for b in bars]
    return {"values": vals, "method": "negócios individuais (PREMED da B3 = volume financeiro ÷ quantidade da sessão)" if exact
            else "aproximação por barras: preço típico (H+L+C)/3"}


def vwap_intraday(bars: List[dict], session_key) -> Dict[str, object]:
    """Barras intradiárias: acumula desde a 1ª barra de cada sessão e REINICIA quando muda a sessão (session_key)."""
    out, pv, vv, cur = [], 0.0, 0.0, None
    for b in bars:
        s = session_key(b)
        if s != cur:
            pv, vv, cur = 0.0, 0.0, s
        tp = (_f(b["high"]) + _f(b["low"]) + _f(b["close"])) / 3
        v = _f(b.get("volume") or 0) or 0.0
        pv += tp * v; vv += v
        out.append(pv / vv if vv else tp)
    return {"values": out, "method": "aproximação por barras de 1 min: Σ(preço típico × volume) ÷ Σ volume desde a abertura da sessão"}


def anchored_vwap(bars: List[dict], anchor_idx: int) -> Dict[str, object]:
    exact = all(b.get("fin_volume") is not None and b.get("volume") for b in bars[anchor_idx:])
    out: List[F] = [None] * len(bars)
    num = den = 0.0
    for i in range(anchor_idx, len(bars)):
        b = bars[i]
        if exact:
            num += _f(b["fin_volume"]); den += _f(b["volume"])
        else:
            tp = (_f(b["high"]) + _f(b["low"]) + _f(b["close"])) / 3
            num += tp * _f(b.get("volume") or 0); den += _f(b.get("volume") or 0)
        out[i] = num / den if den else None
    return {"values": out, "method": "exato: Σ volume financeiro ÷ Σ quantidade (B3)" if exact else "aproximação por preço típico × volume"}


def align(a: List[dict], b: List[dict]) -> List[tuple]:
    """Interseção por data de sessão: um mercado fechado NÃO vira retorno zero no outro."""
    bm = {x["session_date"]: x for x in b}
    return [(x, bm[x["session_date"]]) for x in a if x["session_date"] in bm]


def relative_strength(a: List[dict], b: List[dict]) -> Dict[str, object]:
    pairs = align(a, b)
    ratio = [(str(x["session_date"]), _f(x["close"]) / _f(y["close"])) for x, y in pairs]
    base_a, base_b = (_f(pairs[0][0]["close"]), _f(pairs[0][1]["close"])) if pairs else (1, 1)
    b100 = [(str(x["session_date"]), 100 * _f(x["close"]) / base_a, 100 * _f(y["close"]) / base_b) for x, y in pairs]
    dropped = len(a) - len(pairs)
    return {"ratio": ratio, "base100": b100, "dropped_sessions": dropped,
            "note": f"{dropped} sessão(ões) sem pregão no benchmark foram excluídas (sem preencher com retorno zero)"}


def volume_profile(bars: List[dict], bins: int = 24) -> Dict[str, object]:
    lo = min(_f(b["low"]) for b in bars); hi = max(_f(b["high"]) for b in bars)
    step = (hi - lo) / bins if hi > lo else 1
    acc = [0.0] * bins
    for b in bars:
        l, h, v = _f(b["low"]), _f(b["high"]), _f(b.get("volume") or 0)
        i0, i1 = int((l - lo) / step), min(bins - 1, int((h - lo) / step))
        share = v / (i1 - i0 + 1)
        for i in range(i0, i1 + 1):
            acc[min(i, bins - 1)] += share
    return {"bins": [{"from": lo + i * step, "to": lo + (i + 1) * step, "volume": acc[i]} for i in range(bins)],
            "method": "APROXIMAÇÃO por candles: volume de cada barra distribuído uniformemente entre mínima e máxima (sem negócios individuais)"}


STUDIES = {
    "sma": {"group": "Tendência", "label": "Média simples", "params": {"n": 20}, "warmup": lambda p: p["n"] - 1, "pane": "price",
            "doc": "SMA(n) = média aritmética dos n últimos fechamentos."},
    "ema": {"group": "Tendência", "label": "Média exponencial", "params": {"n": 9}, "warmup": lambda p: p["n"] - 1, "pane": "price",
            "doc": "EMA(n): α = 2/(n+1); semente = SMA dos n primeiros fechamentos."},
    "macd": {"group": "Tendência", "label": "MACD", "params": {"fast": 12, "slow": 26, "signal": 9}, "warmup": lambda p: p["slow"] + p["signal"] - 2,
             "pane": "own", "doc": "MACD = EMA(rápida) − EMA(lenta); sinal = EMA(sinal) do MACD; histograma = MACD − sinal."},
    "adx": {"group": "Tendência", "label": "ADX ±DI", "params": {"n": 14}, "warmup": lambda p: 2 * p["n"] - 1, "pane": "own",
            "doc": "Wilder: +DM/−DM e TR suavizados por RMA(n); DX = 100·|+DI−−DI|/(+DI+−DI); ADX = RMA(n) do DX."},
    "rsi": {"group": "Momentum", "label": "RSI / IFR", "params": {"n": 14}, "warmup": lambda p: p["n"], "pane": "own",
            "doc": "Wilder: ganhos e perdas médios por RMA(n), semente SMA; RSI = 100 − 100/(1+G/P)."},
    "stoch": {"group": "Momentum", "label": "Estocástico", "params": {"k": 14, "smooth": 3, "d": 3}, "warmup": lambda p: p["k"] + p["smooth"] + p["d"] - 3,
              "pane": "own", "doc": "%K lento = SMA(smooth) de 100·(C−LL)/(HH−LL) em k barras; %D = SMA(d) de %K."},
    "roc": {"group": "Momentum", "label": "Taxa de variação", "params": {"n": 12}, "warmup": lambda p: p["n"], "pane": "own",
            "doc": "ROC(n) = 100·(C/C[n] − 1)."},
    "bb": {"group": "Volatilidade", "label": "Bandas de Bollinger", "params": {"n": 20, "k": 2}, "warmup": lambda p: p["n"] - 1, "pane": "price",
           "doc": "Média SMA(n) ± k desvios-padrão POPULACIONAIS dos n fechamentos."},
    "atr": {"group": "Volatilidade", "label": "ATR", "params": {"n": 14}, "warmup": lambda p: p["n"], "pane": "own",
            "doc": "Wilder: RMA(n) do true range = max(H−L, |H−C₋₁|, |L−C₋₁|)."},
    "hv": {"group": "Volatilidade", "label": "Volatilidade histórica", "params": {"n": 20}, "warmup": lambda p: p["n"], "pane": "own",
           "doc": "Desvio-padrão amostral de n log-retornos diários × √252, em % a.a."},
    "volma": {"group": "Volume", "label": "Média de volume", "params": {"n": 20}, "warmup": lambda p: p["n"] - 1, "pane": "volume",
              "doc": "SMA(n) da quantidade negociada."},
    "relvol": {"group": "Volume", "label": "Volume relativo", "params": {"n": 20}, "warmup": lambda p: p["n"], "pane": "own",
               "doc": "Volume da barra ÷ média das n barras anteriores (exclui a atual)."},
    "obv": {"group": "Volume", "label": "OBV", "params": {}, "warmup": lambda p: 0, "pane": "own",
            "doc": "Acumula +volume em alta e −volume em queda do fechamento."},
    "vwap": {"group": "Volume", "label": "VWAP de sessão", "params": {}, "warmup": lambda p: 0, "pane": "price",
             "doc": "Reinicia a cada sessão. B3 diária: PREMED (todos os negócios). Intradiário: Σ(preço típico×vol)/Σvol desde a abertura."},
    "avwap": {"group": "Volume", "label": "VWAP ancorado", "params": {"anchor": None}, "warmup": lambda p: 0, "pane": "price",
              "doc": "Desde a data-âncora escolhida: Σ volume financeiro ÷ Σ quantidade (exato na B3)."},
    "rs": {"group": "Força relativa", "label": "Razão ação/benchmark", "params": {"bench": "BOVA11"}, "warmup": lambda p: 0, "pane": "own",
           "doc": "Preço do ativo ÷ preço do benchmark nas datas com pregão em ambos. Não confundir com RSI."},
    "cmp": {"group": "Força relativa", "label": "Comparação base 100", "params": {"bench": "BOVA11"}, "warmup": lambda p: 0, "pane": "own",
            "doc": "Ativo e benchmark rebaseados a 100 na 1ª data comum."},
    "vprofile": {"group": "Adicionais", "label": "Perfil de volume (aprox.)", "params": {"bins": 24}, "warmup": lambda p: 0, "pane": "price",
                 "doc": "Aproximação por candles; requer negócios individuais para o perfil exato."},
}


def compute(study: str, params: dict, bars: List[dict], bench: Optional[List[dict]] = None) -> dict:
    p = {**STUDIES[study]["params"], **{k: v for k, v in (params or {}).items() if v is not None}}
    c = [_f(b["close"]) for b in bars]
    h = [_f(b["high"]) for b in bars]
    l = [_f(b["low"]) for b in bars]
    v = [_f(b.get("volume") or 0) for b in bars]
    meta = {"study": study, "params": p, "warmup_bars": STUDIES[study]["warmup"](p), "doc": STUDIES[study]["doc"],
            "price_source": "fechamento", "missing_policy": "sem preenchimento; aquecimento = None"}
    if study == "sma":
        return {**meta, "series": {"sma": sma(c, int(p["n"]))}}
    if study == "ema":
        return {**meta, "series": {"ema": ema(c, int(p["n"]))}}
    if study == "macd":
        return {**meta, "series": macd(c, int(p["fast"]), int(p["slow"]), int(p["signal"]))}
    if study == "adx":
        return {**meta, "series": adx(h, l, c, int(p["n"]))}
    if study == "rsi":
        return {**meta, "series": {"rsi": rsi(c, int(p["n"]))}, "levels": [30, 70]}
    if study == "stoch":
        return {**meta, "series": stochastic(h, l, c, int(p["k"]), int(p["smooth"]), int(p["d"])), "levels": [20, 80]}
    if study == "roc":
        return {**meta, "series": {"roc": roc(c, int(p["n"]))}}
    if study == "bb":
        return {**meta, "series": bollinger(c, int(p["n"]), float(p["k"]))}
    if study == "atr":
        return {**meta, "series": {"atr": atr(h, l, c, int(p["n"]))}}
    if study == "hv":
        return {**meta, "series": {"hv": hist_vol(c, int(p["n"]))}, "annualization": "√252, % a.a."}
    if study == "volma":
        return {**meta, "series": {"volma": sma(v, int(p["n"]))}}
    if study == "relvol":
        return {**meta, "series": {"relvol": rel_volume(v, int(p["n"]))}, "levels": [1]}
    if study == "obv":
        return {**meta, "series": {"obv": obv(c, v)}}
    if study == "vwap":
        r = vwap_session(bars)
        return {**meta, "series": {"vwap": r["values"]}, "method": r["method"]}
    if study == "avwap":
        anchor = p.get("anchor")
        idx = next((i for i, b in enumerate(bars) if str(b["session_date"]) >= str(anchor)), 0) if anchor else max(0, len(bars) - 60)
        r = anchored_vwap(bars, idx)
        return {**meta, "series": {"avwap": r["values"]}, "method": r["method"], "anchor": str(bars[idx]["session_date"]) if bars else None}
    if study in ("rs", "cmp"):
        if not bench:
            return {**meta, "error": "benchmark sem dados"}
        r = relative_strength(bars, bench)
        bm = {d: (ra, ) for d, ra in r["ratio"]}
        b100 = {d: (x, y) for d, x, y in r["base100"]}
        dates = [str(b["session_date"]) for b in bars]
        if study == "rs":
            return {**meta, "series": {"ratio": [bm.get(d, (None,))[0] for d in dates]}, "note": r["note"]}
        return {**meta, "series": {"asset": [b100.get(d, (None, None))[0] for d in dates], "bench": [b100.get(d, (None, None))[1] for d in dates]}, "note": r["note"]}
    if study == "vprofile":
        return {**meta, **volume_profile(bars, int(p["bins"]))}
    raise KeyError(study)
