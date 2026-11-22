// VALUE: múltiplos com preço oficial e fundamentos LTM + DCF/DCF reverso/cenários/matriz (reuso do DCF).
import { useEffect, useState } from "react";
import { api } from "../api";
import { dt, num } from "../format";
import { Route } from "../store";
import { Dcf } from "./Thesis";

export default function Value({ route }: { route: Route }) {
  const [v, setV] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setV(null); api(`/api/value/${route.listing_id}`).then(setV).catch((e) => setErr(e.message)); }, [route.listing_id]);
  return (
    <div className="view">
      <h3 style={{ marginTop: 0 }}>Múltiplos (LTM)</h3>
      {err && <div className="callout err">{err}</div>}
      {v && (
        <>
          <div className="note">Preço {num(v.price.value, 2)} em {dt(v.price.session)} — {v.price.source} · Ações {v.shares.value ? num(Number(v.shares.value) / 1e6, 1) + " mi" : "—"} ({v.shares.convention}) · fundamentos LTM até {dt(v.period)}</div>
          <table className="tbl"><thead><tr><th>Múltiplo</th><th>Valor</th><th>Fórmula</th><th>Alertas</th></tr></thead><tbody>
            {Object.entries(v.multiples).map(([k, m]: any) => <tr key={k}><td>{m.name}</td><td className="num mono">{m.value ? num(m.value, 2) + "x" : "—"}</td><td className="dim mono" style={{ fontSize: 10.5 }}>{m.formula}</td>
              <td className="down" style={{ fontSize: 11 }}>{(m.flags || []).join("; ")}{m.missing?.length ? `faltam: ${m.missing.join(", ")}` : ""}</td></tr>)}
          </tbody></table>
          {v.note && <div className="note">{v.note}</div>}
          <div className="note">Múltiplos forward e históricos exigem consenso licenciado e preços ajustados por proventos (não carregados).</div>
        </>
      )}
      <h3>DCF · DCF reverso · cenários · WACC × g</h3>
      {route.issuer_id ? <Dcf route={route} embedded /> : <div className="callout">Sem emissor com demonstrações.</div>}
    </div>
  );
}
