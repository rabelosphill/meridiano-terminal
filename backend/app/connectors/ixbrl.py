"""Parser mínimo de Inline XBRL (10-K/10-Q da SEC) para localizar fatos no documento original."""
import re
from decimal import Decimal
from typing import Dict, List, Optional

CTX_RE = re.compile(r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', re.S)
START_RE = re.compile(r"<xbrli:startDate>([\d-]+)</xbrli:startDate>")
END_RE = re.compile(r"<xbrli:endDate>([\d-]+)</xbrli:endDate>")
INST_RE = re.compile(r"<xbrli:instant>([\d-]+)</xbrli:instant>")
NF_RE = re.compile(r"<ix:nonFraction\s([^>]*)>(.*?)</ix:nonFraction>", re.S)
ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")


def parse_contexts(html: str) -> Dict[str, dict]:
    out = {}
    for cid, body in CTX_RE.findall(html):
        inst = INST_RE.search(body)
        out[cid] = {
            "dimensional": "<xbrli:segment>" in body,
            "start": None if inst else (START_RE.search(body).group(1) if START_RE.search(body) else None),
            "end": inst.group(1) if inst else (END_RE.search(body).group(1) if END_RE.search(body) else None),
        }
    return out


def parse_facts(html: str) -> List[dict]:
    """Retorna fatos numéricos sem dimensão, com id do elemento, texto exibido, escala e sinal."""
    ctx = parse_contexts(html)
    facts = []
    for attrs_s, inner in NF_RE.findall(html):
        a = dict(ATTR_RE.findall(attrs_s))
        c = ctx.get(a.get("contextRef", ""))
        if not c or c["dimensional"] or "id" not in a:
            continue
        shown = TAG_RE.sub("", inner).strip()
        facts.append({
            "id": a["id"], "name": a.get("name", ""), "start": c["start"], "end": c["end"],
            "shown": shown, "scale": int(a.get("scale", "0") or 0), "sign": a.get("sign", ""),
            "unit": a.get("unitRef", ""), "decimals": a.get("decimals"),
        })
    return facts


def displayed_value(f: dict) -> Optional[Decimal]:
    """Converte o texto exibido (ex.: '416,161') em valor numérico em unidades."""
    txt = f["shown"].replace(",", "").replace("$", "").strip()
    if txt in ("", "—", "-"):
        return Decimal(0)
    v = Decimal(txt) * (Decimal(10) ** f["scale"])
    return -v if f["sign"] == "-" else v


def index_by_key(facts: List[dict]) -> Dict[str, dict]:
    """chave 'concept|start|end' -> {ids:[...], scale}"""
    idx: Dict[str, dict] = {}
    for f in facts:
        concept = f["name"].split(":", 1)[-1]
        key = f"{concept}|{f['start'] or ''}|{f['end']}"
        e = idx.setdefault(key, {"ids": [], "scale": f["scale"], "shown": f["shown"]})
        e["ids"].append(f["id"])
    return idx
