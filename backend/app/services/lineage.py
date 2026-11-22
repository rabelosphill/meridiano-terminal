"""Linhagem: documento original -> payload -> fato -> célula -> exportação."""
import html
import json
from decimal import Decimal
from typing import List, Optional

from ..connectors import ixbrl
from ..db import q, q1
from ..storage import store

SCALE_LABEL = {0: "unidades", 3: "milhares", 6: "milhões", 9: "bilhões"}


def fact_lineage(fact_id: int) -> Optional[dict]:
    f = q1("""SELECT f.*, d.external_id doc_external_id, d.form doc_form, d.url doc_url, d.published_at doc_published_at,
                     d.version doc_ver, d.object_key doc_object_key, d.period_end doc_period_end, d.id doc_id,
                     r.request payload_request, r.sha256 payload_sha256, r.fetched_at payload_fetched_at, r.mode payload_mode,
                     s.name source_name, s.license source_license
              FROM fact f LEFT JOIN document d ON d.id=f.document_id LEFT JOIN raw_payload r ON r.id=f.raw_payload_id
              JOIN source s ON s.code=f.source WHERE f.id=%s""", (fact_id,))
    if not f:
        return None
    loc = f["location"]
    versions = q("""SELECT f.id, f.value, f.published_at, f.doc_version, d.external_id, d.form, f.location->>'ordem_exerc' ordem
                    FROM fact f LEFT JOIN document d ON d.id=f.document_id
                    WHERE f.issuer_id=%s AND f.concept=%s AND f.scope=%s AND f.period_end=%s
                      AND f.period_start IS NOT DISTINCT FROM %s AND f.unit=%s ORDER BY f.published_at, f.id""",
                 (f["issuer_id"], f["concept"], f["scope"], f["period_end"], f["period_start"], f["unit"]))
    scale = f["scale"]
    transformations = []
    if f["source"] == "CVM_DADOS":
        transformations.append(f"VL_CONTA {loc.get('vl_conta')} × 10^{scale} ({loc.get('escala')}) = {f['value']} {f['currency']} (unidades)")
        location_text = f"{loc.get('file')} · linha {loc.get('line')} · CD_CONTA {loc.get('cd_conta')} · {loc.get('ordem_exerc')}"
    else:
        transformations.append(f"companyfacts → valor XBRL em unidades ({f['value']} {f['unit']}); documento exibe em {SCALE_LABEL.get(scale, scale)} (scale={scale})")
        location_text = (f"{f['doc_form']} {f['doc_external_id']} · elemento ix #{loc['ix_ids'][0]}" if loc.get("ix_ids")
                         else f"{f['doc_form']} {f['doc_external_id']} · fato não localizado no HTML armazenado (somente companyfacts)")
    return {
        "fact_id": f["id"], "concept": f["concept"], "label": f["label"], "statement": f["statement"],
        "value": str(f["value"]) if f["value"] is not None else None, "state": "absent" if f["value"] is None else ("zero" if f["value"] == 0 else "value"),
        "unit": f["unit"], "currency": f["currency"], "scale": scale, "scale_label": SCALE_LABEL.get(scale, str(scale)),
        "period": {"type": f["period_type"], "start": f["period_start"].isoformat() if f["period_start"] else None, "end": f["period_end"].isoformat(),
                   "fiscal_year": f["fiscal_year"], "fiscal_period": f["fiscal_period"]},
        "scope": f["scope"], "basis": f["basis"],
        "source": {"code": f["source"], "name": f["source_name"], "license": f["source_license"]},
        "document": {"id": str(f["doc_id"]) if f["doc_id"] else None, "external_id": f["doc_external_id"], "form": f["doc_form"],
                     "url": f["doc_url"], "published_at": f["doc_published_at"].isoformat() if f["doc_published_at"] else None,
                     "version": f["doc_ver"], "stored_copy": bool(f["doc_object_key"]) or f["source"] == "CVM_DADOS"},
        "location": {**loc, "text": location_text},
        "payload": {"request": f["payload_request"], "sha256": f["payload_sha256"],
                    "fetched_at": f["payload_fetched_at"].isoformat() if f["payload_fetched_at"] else None, "mode": f["payload_mode"]},
        "published_at": f["published_at"].isoformat(), "ingested_at": f["ingested_at"].isoformat(),
        "transformations": transformations,
        "versions": [{"fact_id": v["id"], "value": str(v["value"]) if v["value"] is not None else None, "published_at": v["published_at"].isoformat(),
                      "document": v["external_id"], "form": v["form"], "doc_version": v["doc_version"], "ordem": v["ordem"]} for v in versions],
    }


def reconcile_fact(fact_id: int) -> dict:
    """Recompõe o valor a partir do documento original armazenado e compara com o fato."""
    L = fact_lineage(fact_id)
    f = q1("SELECT * FROM fact WHERE id=%s", (fact_id,))
    loc = f["location"]
    if f["source"] == "SEC_EDGAR":
        d = q1("SELECT object_key FROM document WHERE id=%s", (f["document_id"],))
        if not d or not d["object_key"] or not loc.get("ix_ids"):
            return {"ok": None, "reason": "documento original não armazenado ou fato sem marcação ix"}
        doc = store.get(d["object_key"]).decode("utf-8", "replace")
        el = next(x for x in ixbrl.parse_facts(doc) if x["id"] == loc["ix_ids"][0])
        shown = ixbrl.displayed_value(el)
        return {"ok": shown == f["value"], "document_shows": el["shown"], "document_scale": el["scale"], "document_sign": el["sign"] or "+",
                "recomputed": str(shown), "fact_value": str(f["value"]), "currency": "USD", "scope": f["scope"],
                "period": [str(f["period_start"]), str(f["period_end"])], "element": el["id"], "lineage": L}
    rp = q1("SELECT object_key, request FROM raw_payload WHERE id=%s", (f["raw_payload_id"],))
    lines = store.get(rp["object_key"]).decode("utf-8").splitlines()
    hdr = lines[0].split(";")
    row = next(dict(zip(hdr, l.split(";"))) for l in lines[1:] if l.split(";")[0] == str(loc["line"]))
    scale = {"MIL": 3, "UNIDADE": 0}[row["ESCALA_MOEDA"]]
    recomputed = Decimal(row["VL_CONTA"]) * (Decimal(10) ** scale)
    return {"ok": recomputed == f["value"], "document_shows": row["VL_CONTA"], "document_scale": row["ESCALA_MOEDA"], "currency": row["MOEDA"],
            "scope": row["GRUPO_DFP"], "period": [row.get("DT_INI_EXERC"), row["DT_FIM_EXERC"]], "cd_conta": row["CD_CONTA"], "ds_conta": row["DS_CONTA"],
            "recomputed": str(recomputed), "fact_value": str(f["value"]), "line": loc["line"], "file": loc["file"], "lineage": L}


VIEWER_JS = """
<style>.ft-hl{outline:3px solid #ffb000!important;background:rgba(255,176,0,.28)!important;scroll-margin:40vh}
.ft-hl-cur{outline:3px solid #ff3d00!important;background:rgba(255,80,0,.35)!important}</style>
<script>(function(){var ids=%s,i=0;function els(){return ids.map(function(x){return document.getElementById(x)}).filter(Boolean)}
function go(k){var e=els();if(!e.length)return;e.forEach(function(x){x.classList.add('ft-hl');x.classList.remove('ft-hl-cur')});i=(k+e.length)%%e.length;
e[i].classList.add('ft-hl-cur');e[i].scrollIntoView({block:'center'});parent.postMessage({ft:'doc-pos',i:i,n:e.length},'*')}
window.addEventListener('message',function(m){if(!m.data||!m.data.ft)return;if(m.data.ft==='next')go(i+1);if(m.data.ft==='prev')go(i-1)});
document.addEventListener('keydown',function(ev){if(ev.key==='Escape'){parent.postMessage({ft:'doc-esc'},'*')}if(ev.key==='n')go(i+1);if(ev.key==='N')go(i-1)});
var first=function(){go(0)};if(document.readyState!=='loading')first();else document.addEventListener('DOMContentLoaded',first);
window.addEventListener('load',first);setTimeout(first,250);setTimeout(first,900);})();</script>
"""


def render_document(doc_id: str, highlight: List[str]) -> Optional[str]:
    d = q1("SELECT * FROM document WHERE id=%s", (doc_id,))
    if not d or not d["object_key"]:
        return None
    raw = store.get(d["object_key"]).decode("utf-8", "replace")
    inj = VIEWER_JS % json.dumps([h for h in highlight if h.replace("-", "").replace("_", "").isalnum()])
    return raw.replace("</body>", inj + "</body>") if "</body>" in raw else raw + inj


def render_cvm_rows(fact_id: int, context: int = 12) -> Optional[str]:
    f = q1("SELECT * FROM fact WHERE id=%s", (fact_id,))
    if not f or f["source"] != "CVM_DADOS":
        return None
    rp = q1("SELECT object_key, request FROM raw_payload WHERE id=%s", (f["raw_payload_id"],))
    lines = store.get(rp["object_key"]).decode("utf-8").splitlines()
    hdr = lines[0].split(";")
    target = f["location"]["line"]
    body = [l.split(";") for l in lines[1:]]
    idx = next(i for i, r in enumerate(body) if r[0] == str(target))
    # ordem de leitura: colunas-chave primeiro (o arquivo armazenado permanece intacto)
    first = [c for c in ["SRC_LINE", "CD_CONTA", "DS_CONTA", "VL_CONTA", "ESCALA_MOEDA", "MOEDA", "GRUPO_DFP", "DT_INI_EXERC", "DT_FIM_EXERC",
                         "ORDEM_EXERC", "VERSAO", "DT_REFER", "ST_CONTA_FIXA"] if c in hdr]
    order = [hdr.index(c) for c in first] + [i for i, c in enumerate(hdr) if c not in first]
    hdr = [hdr[i] for i in order]
    body = [[r[i] if i < len(r) else "" for i in order] for r in body]
    lo = max(0, idx - context)
    rows_html = []
    for r in body[lo: idx + context + 1]:
        cls = ' class="ft-hl-cur" id="target"' if r[0] == str(target) else ""
        rows_html.append(f"<tr{cls}>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>")
    return f"""<!doctype html><meta charset="utf-8"><style>body{{font:12px ui-monospace,Menlo,monospace;background:#0b0f14;color:#c8d3df;margin:0}}
table{{border-collapse:collapse}}td,th{{border:1px solid #223;padding:2px 6px;white-space:nowrap}}th{{position:sticky;top:0;background:#141b24;color:#8fa3b8}}
.ft-hl-cur td{{background:#5a3b00;color:#fff}} .hd{{padding:8px;color:#8fa3b8}}</style>
<div class="hd">Arquivo original CVM: {html.escape(f['location']['file'])} — linha {target} (1 = cabeçalho). Origem: {html.escape(rp['request'])}<br>
Colunas reordenadas apenas para leitura (conta, valor, escala, moeda, escopo, período primeiro); o arquivo armazenado é byte a byte o original filtrado.</div>
<table><tr>{''.join(f'<th>{html.escape(h)}</th>' for h in hdr)}</tr>{''.join(rows_html)}</table>
<script>document.getElementById('target').scrollIntoView({{block:'center'}});document.addEventListener('keydown',function(e){{if(e.key==='Escape')parent.postMessage({{ft:'doc-esc'}},'*')}});parent.postMessage({{ft:'doc-pos',i:0,n:1}},'*')</script>"""
