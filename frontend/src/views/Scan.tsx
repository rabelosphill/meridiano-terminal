// SCAN: filtros combináveis, explicação por ativo, exclusões declaradas, consulta salva e abertura do gráfico sem perder filtros.
import { useEffect, useState } from "react";
import { api, post, put } from "../api";
import { dt, num, pct } from "../format";
import { run } from "../nav";
import { fnKey, loadState, Route, saveState } from "../store";

const FIELDS: Record<string, string> = { avg_fin_volume: "Volume financeiro médio (R$)", close_vs_sma: "Fechamento vs SMA", return: "Retorno de preço",
  return_vs_bench: "Retorno vs benchmark", rsi: "RSI", rel_volume: "Volume relativo", breakout_high: "Rompimento de máxima (1=sim)", close: "Fechamento (R$)" };
const fmtv = (f: string, v: number | null) => v == null ? "—" : f === "avg_fin_volume" ? `R$ ${num(v / 1e6, 1)} mi` : ["close_vs_sma", "return", "return_vs_bench"].includes(f) ? pct(v, 1) : num(v, 2);

export default function Scan({ route }: { route: Route }) {
  const [spec, setSpec] = useState<any>(null);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<any[]>([]);
  const [showEx, setShowEx] = useState(false);
  const key = fnKey(route);
  useEffect(() => {
    loadState<any>(key).then(async (s) => {
      const sp = s?.spec || (await api("/api/scan/example"));
      setSpec(sp); if (s?.result) setRes(s.result); else exec(sp);
    });
    api("/api/scan/saved").then((r) => setSaved(r.queries));
  }, []);
  const exec = async (sp = spec) => { setBusy(true); const r = await post("/api/scan", sp); setRes(r); setBusy(false); saveState(key, { spec: sp, result: r }); };
  if (!spec) return <div className="note">carregando…</div>;
  const upd = (i: number, k: string, v: any) => setSpec({ ...spec, filters: spec.filters.map((f: any, j: number) => (j === i ? { ...f, [k]: v } : f)) });
  return (
    <div className="view">
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <b>{spec.name}</b>
        <label className="dim">data de corte <input type="date" className="field" value={spec.as_of || ""} onChange={(e) => setSpec({ ...spec, as_of: e.target.value || null })} /></label>
        <label className="dim">benchmark <input className="field" style={{ width: 70 }} value={spec.benchmark} onChange={(e) => setSpec({ ...spec, benchmark: e.target.value.toUpperCase() })} /></label>
        <button className="btn pri" onClick={() => exec()} disabled={busy}>{busy ? "rodando…" : "Rodar"}</button>
        <button className="btn" onClick={async () => { const n = prompt("Nome da consulta:", spec.name); if (n) { await put(`/api/scan/saved/${encodeURIComponent(n)}`, { ...spec, name: n }); setSaved((await api("/api/scan/saved")).queries); } }}>Salvar consulta</button>
        {saved.length > 0 && <select className="field" onChange={(e) => { const q = saved.find((x) => x.name === e.target.value); if (q) { setSpec(q.spec); exec(q.spec); } }} defaultValue="">
          <option value="" disabled>consultas salvas…</option>{saved.map((q) => <option key={q.name}>{q.name}</option>)}</select>}
        <button className="btn" onClick={async () => { const ex = await api("/api/scan/example"); setSpec(ex); exec(ex); }}>Exemplo</button>
      </div>
      <table className="tbl" style={{ marginTop: 6 }}><tbody>
        {spec.filters.map((f: any, i: number) => (
          <tr key={i}><td><select className="field" value={f.field} onChange={(e) => upd(i, "field", e.target.value)}>{Object.entries(FIELDS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></td>
            <td><label className="dim">n <input className="field" style={{ width: 48 }} value={f.n ?? ""} onChange={(e) => upd(i, "n", Number(e.target.value))} /></label></td>
            <td><select className="field" value={f.op} onChange={(e) => upd(i, "op", e.target.value)}>{[">", ">=", "<", "<="].map((o) => <option key={o}>{o}</option>)}</select></td>
            <td><input className="field" style={{ width: 110 }} value={f.value} onChange={(e) => upd(i, "value", Number(e.target.value))} /></td>
            <td><button className="btn" onClick={() => setSpec({ ...spec, filters: spec.filters.filter((_: any, j: number) => j !== i) })}>×</button></td></tr>
        ))}
      </tbody></table>
      <button className="btn" onClick={() => setSpec({ ...spec, filters: [...spec.filters, { field: "rsi", n: 14, op: "<", value: 70 }] })}>+ filtro</button>
      {res && (
        <>
          <div className="callout info">
            Corte <b>{dt(res.cut_date)}</b> · moeda {res.currency} · universo {res.universe_size} ações B3 · <b>{res.passed.length}</b> aprovadas · {res.failed} reprovadas · {res.excluded.length} excluídas.
            Benchmark: {res.benchmark.note}. {Object.entries(res.benchmark.returns).map(([n, r]) => `Retorno ${res.benchmark.ticker} ${n} sessões: ${pct(r as number, 1)}.`).join(" ")}
            <div className="dim" style={{ fontSize: 11 }}>Preço: {res.conventions.price}. Sessões: {res.conventions.sessions}. Fonte: {res.source}.</div>
          </div>
          <table className="tbl"><thead><tr><th>Ativo</th><th>Fechamento</th>{spec.filters.map((f: any, i: number) => <th key={i}>{FIELDS[f.field]} ({f.n})</th>)}<th>Por que entrou</th></tr></thead><tbody>
            {res.passed.map((r: any) => (
              <tr key={r.ticker} style={{ cursor: "pointer" }} tabIndex={0} onClick={() => run(`${r.ticker} B3 CHART 1D 1Y`)} onKeyDown={(e) => e.key === "Enter" && run(`${r.ticker} B3 CHART 1D 1Y`)}>
                <td className="mono">{r.ticker} <span className="dim" style={{ fontSize: 10.5 }}>{r.name}</span></td><td className="num mono">{num(r.close, 2)}</td>
                {r.why.map((w: any, i: number) => <td key={i} className="num mono up">{fmtv(w.field, w.value)} ✓</td>)}
                <td className="dim" style={{ fontSize: 10.5, whiteSpace: "normal", minWidth: 380, maxWidth: 520 }}>{r.why.map((w: any) => `${w.field} ${fmtv(w.field, w.value)} ${w.op} ${fmtv(w.field, w.threshold)}`).join(" · ")}{r.warnings?.length ? <div className="down">⚠ {r.warnings.join("; ")}</div> : null}</td>
              </tr>
            ))}
          </tbody></table>
          <button className="btn" style={{ marginTop: 6 }} onClick={() => setShowEx(!showEx)}>{showEx ? "ocultar" : "mostrar"} excluídos ({res.excluded.length})</button>
          {showEx && <table className="tbl"><tbody>{res.excluded.map((x: any) => <tr key={x.ticker}><td className="mono">{x.ticker}</td><td className="dim" style={{ whiteSpace: "normal" }}>{x.reason}</td></tr>)}</tbody></table>}
          <div className="note">Clique num ativo para abrir o gráfico; ao voltar (Alt ←) os filtros e o resultado continuam aqui.</div>
        </>
      )}
    </div>
  );
}

export function Events({ route }: { route: Route }) {
  const [ev, setEv] = useState<any[] | null>(null);
  useEffect(() => {
    const end = new Date().toISOString().slice(0, 10);
    api(`/api/events/${route.listing_id}?start=2025-01-01&end=${end}`).then((r) => setEv(r.events.reverse()));
  }, [route.listing_id]);
  if (!ev) return <div className="note">carregando…</div>;
  return (
    <div className="view">
      <div className="note">Instante de publicação (fonte) separado da 1ª sessão regular em que a informação pôde ser negociada. Precisão "dia" (CVM) é tratada como após o fechamento.</div>
      <table className="tbl"><thead><tr><th>Publicado</th><th>Tipo</th><th>Evento</th><th>1ª sessão negociável</th><th>Fonte</th></tr></thead><tbody>
        {ev.map((e) => <tr key={e.id} style={{ cursor: "pointer" }} onClick={() => run(`${route.ticker} ${route.exchange} CHART 1D 6M`).then(() => history.replaceState(null, "", `${location.hash}&cell=${encodeURIComponent("candle:" + e.tradable_session.session_date)}`))}>
          <td className="mono" style={{ fontSize: 10.5 }}>{e.precision === "day" ? dt(e.published_at, "America/Sao_Paulo").slice(0, 8) + " (dia)" : dt(e.published_at, "America/Sao_Paulo") + " BRT"}</td>
          <td>{e.type}</td><td style={{ whiteSpace: "normal" }}>{e.headline}</td>
          <td className="mono">{dt(e.tradable_session.session_date)} <span className="dim" style={{ fontSize: 10.5 }}>{e.tradable_session.status}</span></td>
          <td><a href={e.url} target="_blank" rel="noopener noreferrer" onClick={(x) => x.stopPropagation()}>{e.source} ↗</a></td></tr>)}
      </tbody></table>
    </div>
  );
}
