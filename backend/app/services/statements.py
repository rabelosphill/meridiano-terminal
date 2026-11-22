"""Montagem de demonstrações a partir de fatos bitemporais.

freq: A (anual), Q (trimestre isolado), LTM (últimos 12 meses)
view: latest (última versão conhecida até as_of) | original (primeira divulgação)
as_of: instante de conhecimento — só entram fatos com published_at <= as_of.
"""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

from ..calc import periods as P
from ..db import q
from .templates import CVM_STANDARD, INSTANT_KEYS, SEC_TEMPLATE, cvm_match

STATEMENT_NAMES = {"IS": "Demonstração do resultado", "BS": "Balanço patrimonial", "CF": "Fluxo de caixa"}


def _days(s: Optional[date], e: date) -> int:
    return (e - s).days if s else 0


def _natural_code_key(code: str):
    return [int(x) if x.isdigit() else x for x in re.split(r"[.]", code)]


def _pick(versions: List[dict], view: str) -> dict:
    versions = sorted(versions, key=lambda f: (f["published_at"], f["id"]))
    return versions[0] if view == "original" else versions[-1]


def _cell_from_fact(f: Optional[dict], versions: List[dict], sign: int = 1) -> dict:
    if f is None:
        return {"state": "absent"}
    vals = {v["value"] for v in versions}
    v = f["value"]
    if v is not None and sign == -1:
        v = -v
    return {"state": "absent" if v is None else ("zero" if v == 0 else "value"), "v": None if v is None else str(v),
            "basis": f["basis"], "fact_id": f["id"], "restated": len(vals) > 1, "n_versions": len(versions),
            "published_at": f["published_at"].isoformat(), "sign_flipped": sign == -1, "label": f["label"]}


def _load(issuer_id: str, statement: str, scope: str, as_of: Optional[datetime], concepts: Optional[List[str]]) -> List[dict]:
    sql = """SELECT id, concept, label, period_type, period_start, period_end, fiscal_year, fiscal_period, value, unit, currency, scale,
                    basis, published_at, source, location->>'st_conta_fixa' AS fixa
             FROM fact WHERE issuer_id=%s AND statement=%s AND scope=%s"""
    args: list = [issuer_id, statement, scope]
    if as_of:
        sql += " AND published_at <= %s"
        args.append(as_of)
    if concepts:
        sql += " AND concept = ANY(%s)"
        args.append(concepts)
    return q(sql, args)


def _norm_label(label: str) -> str:
    import unicodedata
    t = "".join(c for c in unicodedata.normalize("NFKD", label or "") if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\bdo exercicio\b", "do periodo", t)   # DFP diz 'exercício', ITR diz 'período'
    return re.sub(r"\s+", " ", t).strip()


def row_key(f: dict) -> str:
    """Identidade econômica da linha. Contas fixas (CVM ST_CONTA_FIXA='S') e tags XBRL: o próprio código.
    Contas livres ('N'): código-pai + rótulo normalizado, porque o código muda entre documentos
    (ex.: Vale 'Adições ao Imobilizado' foi 6.02.05 num DFP e 6.02.04 em outro)."""
    if f.get("fixa") == "N":
        parent = f["concept"].rsplit(".", 1)[0]
        return f"{parent}|{_norm_label(f['label'])}"
    return f["concept"]


def _group(facts: List[dict]) -> Dict[Tuple, List[dict]]:
    g: Dict[Tuple, List[dict]] = defaultdict(list)
    for f in facts:
        g[(row_key(f), f["unit"], f["period_start"], f["period_end"])].append(f)
    return g


def _columns(groups, statement: str, freq: str, n: int, fye: Tuple[int, int] = (12, 31)) -> List[dict]:
    """Determina colunas a partir dos fatos disponíveis."""
    fy_ends, q_ends = set(), set()
    fy_start_of = {}
    for (_, _, s, e) in groups:
        d = _days(s, e)
        if s and 350 <= d <= 380:
            fy_ends.add(e)
            fy_start_of[e] = s
        if s and (80 <= d <= 100 or 170 <= d <= 190 or 260 <= d <= 285 or 350 <= d <= 380):
            q_ends.add(e)
    if statement == "BS" or not q_ends:
        inst = {e for (_, _, s, e) in groups if s is None}
        q_ends |= inst
    if freq == "A":
        if not fy_ends:  # balanço: saldos na data de encerramento do exercício (±10 dias, p/ exercícios 52/53 semanas)
            fy_ends = {e for (_, _, s, e) in groups if s is None and abs((e - date(e.year, fye[0], min(fye[1], 28))).days) <= 10}
        ends = sorted(fy_ends)[-n:]
        return [{"id": e.isoformat(), "end": e.isoformat(), "start": fy_start_of.get(e, e - timedelta(days=364)).isoformat(),
                 "kind": "FY"} for e in ends]
    ends = sorted(q_ends)[-n:]
    return [{"id": e.isoformat(), "end": e.isoformat(), "kind": "Q" if freq == "Q" else "LTM"} for e in ends]


def _ytd_ending(per_concept: Dict[Tuple, List[dict]], e: date) -> Optional[Tuple[Tuple, date]]:
    best = None
    for (s, ee), _ in per_concept.items():
        if ee == e and s is not None and _days(s, e) <= 380:
            if best is None or _days(s, e) > _days(best, e):
                best = s
    return ((best, e), best) if best else None


def _pv(f: dict, kind: str) -> P.PeriodValue:
    # identidade = row_key (código fixo ou pai+rótulo normalizado); comparabilidade de rótulo já garantida no agrupamento
    return P.PeriodValue(start=f["period_start"], end=f["period_end"], value=f["value"], currency=f["currency"],
                         concept=row_key(f), label=_norm_label(f["label"]), fact_id=f["id"], kind=kind)


def _cell_for(per: Dict[Tuple, List[dict]], col: dict, freq: str, statement: str, view: str, sign: int, fixa: bool) -> dict:
    e = date.fromisoformat(col["end"])
    if statement == "BS":
        k = (None, e)
        return _cell_from_fact(_pick(per[k], view), per[k], sign) if k in per else {"state": "absent"}
    if freq == "A":
        k = (date.fromisoformat(col["start"]), e)
        cand = [kk for kk in per if kk[1] == e and kk[0] and 350 <= _days(kk[0], e) <= 380]
        if not cand:
            return {"state": "absent"}
        return _cell_from_fact(_pick(per[cand[0]], view), per[cand[0]], sign)
    if freq == "Q":
        disc = [kk for kk in per if kk[1] == e and kk[0] and 80 <= _days(kk[0], e) <= 100]
        if disc:
            return _cell_from_fact(_pick(per[disc[0]], view), per[disc[0]], sign)
        y = _ytd_ending(per, e)
        if not y:
            return {"state": "absent"}
        (s, _), start = y
        cur = _pick(per[(s, e)], view)
        prev_keys = sorted([kk for kk in per if kk[0] == s and kk[1] < e], key=lambda kk: kk[1])
        # o YTD anterior precisa terminar no trimestre imediatamente anterior (≈3 meses antes)
        if not prev_keys or not (80 <= (e - prev_keys[-1][1]).days <= 100):
            return {"state": "absent", "reason": "sem YTD do trimestre imediatamente anterior com a mesma conta/rótulo — trimestre não isolável"}
        prev = _pick(per[prev_keys[-1]], view)
        try:
            r = P.quarter_from_ytd(_pv(cur, "duration"), _pv(prev, "duration"), label_strict=not fixa)
        except P.NotComparable as ex:
            return {"state": "not_comparable", "reason": str(ex), "inputs": [cur["id"], prev["id"]]}
        v = r["value"] * sign if r.get("value") is not None else None
        return {"state": "absent" if v is None else ("zero" if v == 0 else "value"), "v": None if v is None else str(v), "basis": "calculated",
                "formula": r.get("formula"), "inputs": r.get("inputs", []), "sign_flipped": sign == -1,
                "restated": any(len({x["value"] for x in per[k]}) > 1 for k in [(s, e), prev_keys[-1]])}
    # LTM
    y = _ytd_ending(per, e)
    if not y:
        return {"state": "absent"}
    (s, _), _ = y
    cur = _pick(per[(s, e)], view)
    if 350 <= _days(s, e) <= 380:
        c = _cell_from_fact(cur, per[(s, e)], sign)
        c["formula"] = "LTM = exercício completo"
        return c
    fy_prev = [kk for kk in per if kk[0] and 350 <= _days(kk[0], kk[1]) <= 380 and abs((kk[1] - (s - timedelta(days=1))).days) <= 7]
    ytd_prev = [kk for kk in per if kk[0] and abs((kk[0] - (s - timedelta(days=364))).days) <= 7 and abs((kk[1] - (e - timedelta(days=364))).days) <= 7]
    if not fy_prev or not ytd_prev:
        return {"state": "absent", "reason": "faltam FY anterior ou YTD comparável"}
    try:
        r = P.ltm_flow(_pv(_pick(per[fy_prev[0]], view), "duration"), _pv(cur, "duration"), _pv(_pick(per[ytd_prev[0]], view), "duration"))
    except P.NotComparable as ex:
        return {"state": "not_comparable", "reason": str(ex)}
    v = r["value"] * sign if r.get("value") is not None else None
    return {"state": "absent" if v is None else ("zero" if v == 0 else "value"), "v": None if v is None else str(v), "basis": "calculated",
            "formula": r.get("formula"), "inputs": r.get("inputs", []), "sign_flipped": sign == -1}


def build(issuer: dict, statement: str, freq: str = "A", scope: str = "consolidated", as_of: Optional[datetime] = None,
          view: str = "latest", n: Optional[int] = None) -> dict:
    src = "SEC_EDGAR" if issuer["reporting_std"] == "US-GAAP" else "CVM_DADOS"
    n = n or (6 if freq == "A" else 8 if freq == "Q" else 4)
    if src == "SEC_EDGAR":
        tmpl = SEC_TEMPLATE[statement]
        concepts = sorted({t for ln in tmpl for t in ln["tags"]})
        facts = _load(issuer["id"], statement, scope, as_of, concepts)
        if statement == "BS":
            facts += [f for f in _load(issuer["id"], "OTHER", scope, as_of, ["DeferredIncomeTaxLiabilities", "CommonStockSharesOutstanding"])]
    else:
        facts = _load(issuer["id"], statement, scope, as_of, None)
    groups = _group(facts)
    cols = _columns(groups, statement, freq, n, _fye(issuer))
    by_concept: Dict[str, Dict[Tuple, List[dict]]] = defaultdict(dict)
    units: Dict[str, str] = {}
    for (c, u, s, e), fs in groups.items():
        by_concept[c][(s, e)] = fs
        units.setdefault(c, u)
    rows = []
    if src == "SEC_EDGAR":
        for ln in tmpl:
            if ln.get("hidden"):
                continue
            tag = next((t for t in ln["tags"] if t in by_concept), None)
            sign = ln.get("sign", 1)
            per = by_concept.get(tag, {}) if tag else {}
            cells = [_cell_for(per, col, freq, statement, view, sign, True) if per else {"state": "absent"} for col in cols]
            rows.append({"key": ln["key"], "concept": tag, "label": ln["label"], "label_en": ln["en"], "indent": ln.get("indent", 0),
                         "bold": ln.get("bold", False), "unit": ln.get("unit", "USD"), "note": ln.get("note", False), "sign": sign,
                         "candidates": ln["tags"], "cells": cells})
    else:
        std_by_code = {}
        for key, std in CVM_STANDARD.items():
            if "code" in std:
                std_by_code[std["code"]] = key
        latest_of = {rk: max((f for fs in per.values() for f in fs), key=lambda f: (f["published_at"], f["id"])) for rk, per in by_concept.items()}
        for rk in sorted(by_concept.keys(), key=lambda k: (_natural_code_key(latest_of[k]["concept"]), k)):
            latest = latest_of[rk]
            code = latest["concept"]
            depth = code.count(".")
            if depth > 3:
                continue
            per = by_concept[rk]
            fixa = (latest.get("fixa") or "S") == "S"
            cells = [_cell_for(per, col, freq, statement, view, 1, fixa) for col in cols]
            if all(c["state"] == "absent" for c in cells):
                continue
            key = std_by_code.get(code)
            if not key:
                for k, std in CVM_STANDARD.items():
                    if "label_re" in std and cvm_match(std, code, latest["label"]) and not any(r.get("key") == k for r in rows):
                        key = k
                        break
            codes_seen = sorted({f["concept"] for fs in per.values() for f in fs}, key=_natural_code_key)
            rows.append({"key": key, "concept": rk, "code": code, "codes_seen": codes_seen, "label": latest["label"], "indent": depth,
                         "bold": depth <= 1, "unit": "BRL", "fixa": fixa, "sign": 1, "cells": cells})
    # rótulos de período: fiscal x calendário
    for col in cols:
        e = date.fromisoformat(col["end"])
        if freq == "A":
            col["label"] = f"FY{_fy(issuer, e)}"
        elif freq == "Q":
            col["label"] = f"{_fq(issuer, e)}"
        else:
            col["label"] = f"LTM {e.strftime('%m/%y')}"
        col["calendar"] = f"{col.get('start', '')[:10]}→{col['end']}" if col.get("start") else col["end"]
    sample = next((f for f in facts), None)
    return {"issuer_id": str(issuer["id"]), "source": src, "statement": statement, "statement_name": STATEMENT_NAMES[statement],
            "freq": freq, "scope": scope, "view": view, "as_of": as_of.isoformat() if as_of else None,
            "currency": "USD" if src == "SEC_EDGAR" else "BRL",
            "display_scale": 6 if src == "SEC_EDGAR" else 6, "display_scale_label": "milhões" ,
            "source_scale_note": "SEC: valores XBRL em unidades; documento exibe em milhões" if src == "SEC_EDGAR"
            else "CVM: ESCALA_MOEDA=MIL (milhares de reais); convertido para unidades e exibido em milhões",
            "columns": cols, "rows": rows,
            "standard_std": "US-GAAP" if src == "SEC_EDGAR" else "IFRS (CPC)"}


def _fye(issuer: dict) -> Tuple[int, int]:
    f = issuer.get("fiscal_year_end") or "1231"
    return int(f[:2]), int(f[2:])


def _fy(issuer: dict, e: date) -> int:
    m, d = _fye(issuer)
    return e.year + (1 if (e.month, e.day) > (m, min(d, 28)) and (e - date(e.year, m, min(d, 28))).days > 10 else 0)


def _fq(issuer: dict, e: date) -> str:
    m, _ = _fye(issuer)
    fy = _fy(issuer, e)
    months_into = (e.month - m) % 12 or 12
    qn = max(1, min(4, round(months_into / 3)))
    return f"{qn}T{str(fy)[2:]}" if m == 12 else f"Q{qn} FY{str(fy)[2:]}"


def standardized(issuer: dict, freq: str = "A", as_of: Optional[datetime] = None, n: int = 5) -> Dict[str, Dict[str, dict]]:
    """{period_end: {key: cell}} para métricas e comparação."""
    out: Dict[str, Dict[str, dict]] = defaultdict(dict)
    for st in ("IS", "BS", "CF"):
        t = build(issuer, st, freq, "consolidated", as_of, "latest", n + 1)
        for r in t["rows"]:
            if not r.get("key"):
                continue
            for col, cell in zip(t["columns"], r["cells"]):
                out[col["end"]].setdefault(r["key"], {**cell, "concept": r["concept"], "label": r["label"]})
    return dict(out)
