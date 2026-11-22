// FIN: demonstrações com proveniência por célula, consulta "como se sabia em D", versões e exportação.
import { useEffect, useRef, useState } from "react";
import { api, ApiError, currentUser } from "../api";
import DocViewer from "../components/DocViewer";
import StatementGrid, { GridHandle } from "../components/StatementGrid";
import { CCY_SYM } from "../format";
import { readUrl, run, writeUrl } from "../nav";
import { fnKey, get, loadState, Route, saveState, set, useStore } from "../store";

const ST = [["IS", "DRE"], ["BS", "Balanço"], ["CF", "Fluxo de caixa"]];
const FQ = [["A", "Anual"], ["Q", "Trimestral"], ["LTM", "LTM"]];
type Saved = { scope: string; view: string; asOf: string; cells: Record<string, { concept: string; period: string; scroll: number }> };

export default function Fin({ route }: { route: Route }) {
  const freq = route.args?.freq || "A";
  const statement = route.args?.statement || "IS";
  const [scope, setScope] = useState("consolidated");
  const [view, setView] = useState("latest");
  const [asOf, setAsOf] = useState("");
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [cur, setCur] = useState({ r: 0, c: 0 });
  const [initialScroll, setInitialScroll] = useState<number | undefined>(undefined);
  const [ready, setReady] = useState(false);
  const saved = useRef<Saved>({ scope: "consolidated", view: "latest", asOf: "", cells: {} });
  const grid = useRef<GridHandle>(null);
  const doc = useStore((s) => s.doc);
  const inspected = useStore((s) => s.selectedCell?.pos);
  const sk = `${statement}:${freq}:${scope}`;
  const t0 = useRef(0);

  // restaura estado salvo (por usuário/workspace/instrumento/função)
  useEffect(() => {
    setReady(false);
    loadState<Saved>(fnKey(route)).then((s) => {
      if (s) { saved.current = { ...saved.current, ...s }; setScope(s.scope || "consolidated"); setView(s.view || "latest"); setAsOf(s.asOf || ""); }
      setReady(true);
    });
  }, [route.instrument_id]);

  useEffect(() => {
    if (!ready || !route.issuer_id) return;
    setErr(null);
    t0.current = performance.now();
    const qs = new URLSearchParams({ statement, freq, scope, view, ...(asOf ? { as_of: asOf } : {}) });
    api(`/api/issuers/${route.issuer_id}/statements?${qs}`, { cacheMs: 300000 }).then((d) => {
      setData(d);
      // posição: URL (compartilhável) > estado salvo > topo
      const url = readUrl();
      const pick = url.cell ? { concept: url.cell.split("@")[0], period: url.cell.split("@")[1], scroll: undefined as any } : saved.current.cells[sk];
      let pos = { r: 0, c: Math.max(0, d.columns.length - 1) };
      if (pick) {
        const r = d.rows.findIndex((x: any) => x.concept === pick.concept);
        const c = d.columns.findIndex((x: any) => x.end === pick.period);
        if (r >= 0) pos = { r, c: c >= 0 ? c : pos.c };
      }
      setInitialScroll(pick?.scroll ?? Math.max(0, pos.r * 22 - 120));
      setCur(pos);
      (window as any).__meridianoPerf.lastFinMs = performance.now() - t0.current;
      requestAnimationFrame(() => { (window as any).__meridianoPerf.lastFinPaintMs = performance.now() - t0.current; });
      if (!get().doc) setTimeout(() => grid.current?.focus(), 0);
    }).catch((e: ApiError) => setErr(e.detail || { message: e.message }));
  }, [ready, route.issuer_id, statement, freq, scope, view, asOf]);

  // persiste posição e opções; URL carrega comando + célula (sem dados privados)
  const persist = (pos = cur, scroll?: number) => {
    if (!data?.rows[pos.r] || get().route !== route) return;   // timer atrasado de tela já fechada não toca a URL
    const cell = { concept: data.rows[pos.r].concept, period: data.columns[pos.c]?.end, scroll: scroll ?? grid.current?.scrollTop() ?? 0 };
    saved.current = { scope, view, asOf, cells: { ...saved.current.cells, [sk]: cell } };
    saveState(fnKey(route), saved.current);
    writeUrl(route, { cell: `${cell.concept}@${cell.period}` });
  };
  useEffect(() => { if (data) persist(); }, [cur, scope, view, asOf]);

  // ao fechar o documento, foco volta exatamente para a célula de origem
  const prevDoc = useRef(doc);
  useEffect(() => {
    if (prevDoc.current && !doc) setTimeout(() => grid.current?.focus(), 0);
    prevDoc.current = doc;
  }, [doc]);

  const cellAt = (p: { r: number; c: number }) => data?.rows[p.r]?.cells[p.c];
  const inspect = (p: { r: number; c: number }) => {
    const row = data.rows[p.r], col = data.columns[p.c], cell = row.cells[p.c];
    set({ selectedFact: cell.fact_id ?? cell.inputs?.[0] ?? null, selectedCell: { ...cell, pos: p, row: { concept: row.concept, label: row.label, unit: row.unit }, col, statement, freq, scope, source: data.source, currency: data.currency } });
  };
  const openSource = (p: { r: number; c: number }) => {
    const cell = cellAt(p);
    inspect(p);
    const fid = cell?.fact_id ?? cell?.inputs?.[0];
    if (!fid) return;
    set({ doc: { factId: fid, returnTo: { row: p.r, col: p.c }, title: data.rows[p.r].label } });
  };
  const exportCsv = async () => {
    const qs = new URLSearchParams({ issuer_id: route.issuer_id!, statement, freq, scope, ...(asOf ? { as_of: asOf } : {}) });
    const r = await fetch(`/api/export/statement.csv?${qs}`, { headers: { "X-User": currentUser() } });
    if (!r.ok) { const j = await r.json(); setErr(j.detail); return; }
    const blob = await r.blob();
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${route.ticker}_${statement}_${freq}.csv`; a.click();
  };
  const go = (f: string, s: string) => run(`${route.ticker} ${route.exchange || ""} FIN ${f} ${s}`);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", position: "relative" }}>
      <div className="toolbar">
        <div className="seg" role="tablist" aria-label="Demonstração">{ST.map(([k, l]) => <button key={k} className={statement === k ? "on" : ""} onClick={() => go(freq, k)}>{l}</button>)}</div>
        <div className="seg" aria-label="Periodicidade">{FQ.map(([k, l]) => <button key={k} className={freq === k ? "on" : ""} onClick={() => go(k, statement)}>{l}</button>)}</div>
        {data?.source === "CVM_DADOS" && (
          <div className="seg" aria-label="Escopo"><button className={scope === "consolidated" ? "on" : ""} onClick={() => setScope("consolidated")}>Consolidado</button><button className={scope === "individual" ? "on" : ""} onClick={() => setScope("individual")}>Individual</button></div>
        )}
        <div className="seg" aria-label="Versão" title="Reapresentações: última versão conhecida vs. como divulgado originalmente">
          <button className={view === "latest" ? "on" : ""} onClick={() => setView("latest")}>Última versão</button>
          <button className={view === "original" ? "on" : ""} onClick={() => setView("original")}>Como divulgado</button>
        </div>
        <label className="dim" title="Consulta histórica: só informações publicadas até esta data">Como se sabia em
          <input className="field" type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} style={{ marginLeft: 4 }} />
        </label>
        {asOf && <button className="btn" onClick={() => setAsOf("")}>hoje</button>}
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={exportCsv} title="Exporta valores em unidades com IDs de fatos (requer permissão)">Exportar CSV</button>
      </div>
      {data && (
        <div className="note fin-legend" style={{ display: "flex", gap: 12, flexWrap: "wrap", borderBottom: "1px solid var(--line)" }}>
          <span><b style={{ color: "var(--fg-2)" }}>{data.statement_name}</b> · {data.scope === "consolidated" ? "consolidado" : "individual"} · {data.standard_std}</span>
          <span>Unidade: <b style={{ color: "var(--fg-2)" }}>{CCY_SYM[data.currency]} milhões</b> (ações em milhões; LPA em {CCY_SYM[data.currency]})</span>
          <span>Fonte: {data.source === "SEC_EDGAR" ? "SEC EDGAR XBRL" : "CVM Dados Abertos (DFP/ITR)"}</span>
          {data.as_of && <span className="badge warn">como se sabia em {data.as_of.slice(0, 10)}</span>}
          <span><span style={{ color: "var(--calc)" }}>ƒ itálico</span> calculado · <span style={{ color: "var(--restated)" }}>↺</span> reapresentado · — ausente · 0 zero · <span style={{ color: "var(--warn)" }}>n/c</span> não comparável</span>
          <span className="dim2">Datas fiscais no cabeçalho; data de encerramento abaixo. <span className="kbd">Enter</span> inspeciona · <span className="kbd">S</span> abre a fonte</span>
        </div>
      )}
      {err && <div className="callout err">{err.message || "erro"} {err.error === "forbidden" && <span className="dim">(verificado no servidor — a API também recusa chamadas diretas)</span>}</div>}
      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        {data && (
          <StatementGrid key={`${route.issuer_id}:${sk}:${view}:${asOf}`} ref={grid} rows={data.rows} cols={data.columns} cur={cur} inspected={inspected}
                         initialScroll={initialScroll} onMove={setCur} onInspect={inspect} onSource={openSource}
                         onScroll={(t) => { clearTimeout((window as any).__finScrollT); (window as any).__finScrollT = setTimeout(() => persist(cur, t), 250); }} />
        )}
        {!data && !err && <div className="note">carregando…</div>}
        {doc && <DocViewer factId={doc.factId} onClose={() => set({ doc: null })} />}
      </div>
    </div>
  );
}
