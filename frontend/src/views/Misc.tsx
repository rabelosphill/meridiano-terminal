import { useEffect, useMemo, useState } from "react";
import { api, currentUser, post } from "../api";
import { openInGroup } from "../components/Watchlist";
import { dir, dt, num, signed, timeOnly } from "../format";
import { run } from "../nav";
import { useQuotes } from "../quotes";
import { Route } from "../store";

const norm = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toUpperCase();

export function Help({ route }: { route: Route }) {
  const [cat, setCat] = useState<any>(null);
  const [q, setQ] = useState(route.args?.q || "");
  useEffect(() => { api("/api/commands", { cacheMs: 600000 }).then(setCat); }, []);
  const n = norm(q);
  const cmds = useMemo(() => (cat?.commands || []).filter((c: any) => !n || norm(JSON.stringify(c)).includes(n)), [cat, n]);
  const fields = useMemo(() => (cat?.fields || []).filter((f: any) => !n || norm(JSON.stringify(f)).includes(n)), [cat, n]);
  return (
    <div className="view">
      <input className="field" style={{ width: "100%", padding: 6 }} placeholder="filtrar funções e campos (PT/EN)…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      <h3>Funções ({cmds.length})</h3>
      <table className="tbl"><thead><tr><th>Código</th><th>Sintaxe</th><th>Sinônimos</th><th>Ativos</th><th>Exemplo</th></tr></thead><tbody>
        {cmds.map((c: any) => (
          <tr key={c.code}><td className="mono"><b>{c.code}</b><div className="dim" style={{ fontSize: 11, whiteSpace: "normal", maxWidth: 260 }}>{c.description}</div></td>
            <td className="mono" style={{ fontSize: 11 }}>{c.syntax}</td><td className="dim mono" style={{ fontSize: 11 }}>{c.synonyms.join(" ")}</td>
            <td className="dim" style={{ fontSize: 11, whiteSpace: "normal" }}>{c.kinds ? c.kinds.join(", ") : "global"}</td>
            <td>{c.examples.map((e: string) => <button key={e} className="chip" style={{ marginRight: 4 }} onClick={() => run(e)}>{e}</button>)}</td></tr>
        ))}</tbody></table>
      <h3>Campos e métricas ({fields.length})</h3>
      <table className="tbl"><thead><tr><th>Código</th><th>Nome</th><th>Definição / origem</th></tr></thead><tbody>
        {fields.map((f: any) => (
          <tr key={f.kind + f.code}><td className="mono">{f.code}</td><td>{f.label} {f.en && <span className="dim">· {f.en}</span>}</td>
            <td className="dim mono" style={{ fontSize: 10.5, whiteSpace: "normal" }}>{f.kind === "metric" ? `${f.formula} [${f.unit}] v${f.version} — ${f.convention}` : `US-GAAP: ${f.sec_tags.join(" | ")}${f.cvm ? ` · CVM: ${f.cvm.code || f.cvm.parent + " /" + f.cvm.label_re + "/"}` : ""}`}</td></tr>
        ))}</tbody></table>
      <h3>Atalhos</h3>
      <div className="note"><span className="kbd">Ctrl/⌘ K</span> busca · <span className="kbd">Enter</span> executa · <span className="kbd">Esc</span> volta ao foco anterior · <span className="kbd">Alt 1/2/3</span> foca painel · <span className="kbd">PgUp/PgDn</span> rola o painel focado · <span className="kbd">setas</span> percorrem células · <span className="kbd">S</span> abre a fonte · <span className="kbd">Alt ←</span> comando anterior</div>
    </div>
  );
}

export function Find({ route }: { route: Route }) {
  const [r, setR] = useState<any>(null);
  useEffect(() => { api(`/api/find?q=${encodeURIComponent(route.args.q)}`).then(setR); }, [route.args.q]);
  if (!r) return <div className="note">buscando…</div>;
  return (
    <div className="view">
      <h3>Empresas ({r.companies.length})</h3>
      {r.companies.map((c: any) => (
        <div key={c.issuer_id} className="box" style={{ marginBottom: 6 }}><b>{c.name}</b> <span className="dim">{c.country}</span>
          <table className="tbl" style={{ marginTop: 4 }}><tbody>{c.listings.map((l: any) => (
            <tr key={l.listing_id} tabIndex={0} onClick={() => openInGroup(l)} onKeyDown={(e) => e.key === "Enter" && openInGroup(l)} style={{ cursor: "pointer" }}>
              <td className="mono">{l.ticker}</td><td>{l.exchange || "OTC"}</td><td>{l.name}</td><td className="dim">{l.kind}{l.class ? ` · ${l.class}` : ""}</td>
              <td className="dim">{l.active ? `desde ${l.valid_from}` : `histórico ${l.valid_from} → ${l.valid_to}`}</td></tr>))}</tbody></table>
        </div>
      ))}
      <h3>Instrumentos ({r.instruments.length})</h3>
      <table className="tbl"><tbody>{r.instruments.map((i: any) => <tr key={i.instrument_id}><td>{i.name}</td><td className="dim">{i.kind}</td><td className="mono">{i.listings.map((l: any) => l.ticker).join(", ")}</td></tr>)}</tbody></table>
      <h3>Listagens ({r.listings.length})</h3>
      <table className="tbl"><thead><tr><th>Ticker</th><th>Bolsa</th><th>Moeda</th><th>Vigência</th><th>Status</th></tr></thead><tbody>
        {r.listings.map((l: any) => <tr key={l.listing_id} tabIndex={0} onClick={() => openInGroup(l)} onKeyDown={(e) => e.key === "Enter" && openInGroup(l)} style={{ cursor: "pointer" }}>
          <td className="mono">{l.ticker}</td><td>{l.exchange || "—"}</td><td>{l.currency}</td><td className="dim">{l.valid_from} → {l.valid_to || "vigente"}</td><td>{l.status}</td></tr>)}</tbody></table>
    </div>
  );
}

const MK_GROUPS: [string, string[]][] = [
  ["Brasil — ações e índice", ["PETR4", "PETR3", "VALE3", "IBOV"]],
  ["EUA — ações, ADRs e índice", ["AAPL", "PBR", "PBR.A", "VALE", "SPX"]],
  ["Câmbio, juros e commodities", ["USDBRL", "DI1F27", "UST10Y", "BRENT"]],
];
export function Markets() {
  const { quotes } = useQuotes();
  const [paused, setPaused] = useState(false);
  const [frozen, setFrozen] = useState<any>(null);
  const [macro, setMacro] = useState<any[]>([]);
  useEffect(() => { Promise.all(["BR.SELIC", "BR.IPCA", "BR.PTAX", "US.UST10Y", "GLOBAL.BRENT"].map((c) => api(`/api/macro/${c}?limit=2`).catch(() => null))).then((x) => setMacro(x.filter(Boolean))); }, []);
  const view = paused && frozen ? frozen : quotes;
  const changed = paused && frozen ? Object.keys(quotes).filter((k) => quotes[k]?.observed_at !== frozen[k]?.observed_at).length : 0;
  const mB3 = quotes["PETR4"]?.market, mUS = quotes["AAPL"]?.market;
  return (
    <div>
      <div className="toolbar">
        <span>B3: <span className={"badge " + (mB3?.state || "")}>{mB3?.label || "—"}</span> <span className="dim mono">{mB3 ? timeOnly(mB3.local_time, "America/Sao_Paulo") : ""}</span></span>
        <span>NYSE/Nasdaq: <span className={"badge " + (mUS?.state || "")}>{mUS?.label || "—"}</span> <span className="dim mono">{mUS ? timeOnly(mUS.local_time, "America/New_York") : ""}</span></span>
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={() => { setFrozen(quotes); setPaused(!paused); }}>{paused ? "retomar" : "pausar"}</button>
        {paused && changed > 0 && <button className="btn pri" onClick={() => setFrozen(quotes)}>{changed} atualizações — ir para o mais recente</button>}
      </div>
      <div className="callout"><b>Cotações de ações, ADRs, índices e DI são SIMULADAS</b> (ambiente dev, sem contrato de bolsa). USD/BRL (PTAX/BCB), Brent (EIA/FRED) e UST 10Y (H.15/FRED) são dados oficiais de fim de dia com a data de referência original.</div>
      <div className="mkt-grid">
        {MK_GROUPS.map(([g, ts]) => (
          <div key={g} className="box" style={{ padding: 0 }}>
            <div className="ph"><span className="t">{g}</span></div>
            <table className="tbl"><thead><tr><th>Ativo</th><th>Último</th><th>Var.</th><th>Var. %</th><th>Obs.</th><th>Feed</th></tr></thead><tbody>
              {ts.map((t) => {
                const q = view[t];
                if (!q) return <tr key={t}><td className="mono">{t}</td><td colSpan={5} className="dim">sem cobertura</td></tr>;
                return <tr key={t} tabIndex={0} onClick={() => openInGroup(q)} onKeyDown={(e) => e.key === "Enter" && openInGroup(q)} style={{ cursor: "pointer" }}>
                  <td><span className="mono">{t}</span> <span className="dim" style={{ fontSize: 10.5 }}>{q.name}</span></td>
                  <td className="num mono">{q.price ? num(q.price, Number(q.price) > 1000 ? 0 : 2) : "—"}</td>
                  <td className={"num mono " + dir(q.change)}>{q.change ? signed(q.change, 2) : ""}</td>
                  <td className={"num mono " + dir(q.change_pct)}>{q.change_pct ? signed(q.change_pct, 2, "%") : ""}</td>
                  <td className="dim mono" style={{ fontSize: 10.5 }}>{q.observed_at ? (q.observed_at.length > 10 ? timeOnly(q.observed_at, q.market?.timezone) : dt(q.observed_at)) : ""}</td>
                  <td><span className={"badge " + (q.feed_state === "interrupted" ? "interrupted" : q.feed_class === "simulated" ? "sim" : "eod")} title={q.feed_label}>{q.feed_state === "interrupted" ? "INTERROMPIDO" : q.feed_class === "simulated" ? "SIM" : q.feed_class?.toUpperCase()}</span></td></tr>;
              })}</tbody></table>
          </div>
        ))}
        <div className="box" style={{ padding: 0 }}>
          <div className="ph"><span className="t">Macro — fonte oficial</span></div>
          <table className="tbl"><thead><tr><th>Série</th><th>Valor</th><th>Unidade</th><th>Referência</th><th>Fonte</th></tr></thead><tbody>
            {macro.map((m) => <tr key={m.code} tabIndex={0} style={{ cursor: "pointer" }} onClick={() => run(`MACRO ${m.code.replace(".", " ")}`)}>
              <td>{m.name}</td><td className="num mono">{num(m.observations[0]?.value, 2)}</td><td className="dim">{m.unit}</td><td className="mono">{dt(m.observations[0]?.date)}</td><td className="dim">{m.source}</td></tr>)}
          </tbody></table>
        </div>
      </div>
      <div className="note">Próximos no monitor (dependem de contrato/conector): curva DI completa (B3), Treasuries por vencimento (U.S. Treasury), breadth, heatmaps e maiores movimentos (feed de bolsa), calendário econômico.</div>
    </div>
  );
}

export function Filings({ route }: { route: Route }) {
  const [docs, setDocs] = useState<any[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { api(`/api/issuers/${route.issuer_id}/documents`).then((r) => setDocs(r.documents)).catch((e) => setErr(e.message)); }, [route.issuer_id]);
  if (err) return <div className="callout err">{err}</div>;
  if (!docs) return <div className="note">carregando…</div>;
  return (
    <div className="view">
      <div className="note">Instante de divulgação = aceite do filing (SEC, horário de Nova York) ou DT_RECEB (CVM, precisão de dia). Versões reapresentadas aparecem como documentos próprios.</div>
      <table className="tbl"><thead><tr><th>Formulário</th><th>Período</th><th>Versão</th><th>Divulgado</th><th>Fatos</th><th>Cópia local</th><th>Original</th></tr></thead><tbody>
        {docs.map((d) => <tr key={d.id}><td className="mono">{d.form} <span className="dim">{d.external_id}</span></td><td className="mono">{dt(d.period_end)}</td>
          <td className="num">{d.version}</td><td className="mono">{dt(d.published_at)}</td><td className="num">{d.n_facts}</td>
          <td>{d.stored ? <a href={`/api/documents/${d.id}/view`} target="_blank" rel="noopener">abrir cópia</a> : d.source === "CVM_DADOS" ? <span className="dim">CSV estruturado</span> : <span className="dim2">—</span>}</td>
          <td><a href={d.url} target="_blank" rel="noopener noreferrer">{d.source === "SEC_EDGAR" ? "SEC" : "CVM/ENET"} ↗</a></td></tr>)}
      </tbody></table>
    </div>
  );
}

function Spark({ pts }: { pts: number[] }) {
  if (pts.length < 2) return null;
  const w = 600, h = 120, mn = Math.min(...pts), mx = Math.max(...pts), sx = w / (pts.length - 1), sy = mx === mn ? 1 : (h - 8) / (mx - mn);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${(i * sx).toFixed(1)},${(h - 4 - (p - mn) * sy).toFixed(1)}`).join("");
  return <svg className="spark" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: "100%", height: 120 }} role="img" aria-label="evolução da série">
    <path d={d} fill="none" stroke="var(--accent)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    <text x="4" y="12" fill="var(--fg-3)" fontSize="10">{num(mx, 2)}</text><text x="4" y={h - 4} fill="var(--fg-3)" fontSize="10">{num(mn, 2)}</text></svg>;
}

export function Macro({ route }: { route: Route }) {
  const [s, setS] = useState<any>(null);
  const [asOf, setAsOf] = useState("");
  const [err, setErr] = useState<any>(null);
  useEffect(() => { setErr(null); api(`/api/macro/${route.args.code}?limit=600${asOf ? "&as_of=" + asOf : ""}`).then(setS).catch((e) => setErr(e.detail)); }, [route.args.code, asOf]);
  const exp = async () => {
    const r = await fetch(`/api/export/macro.csv?code=${route.args.code}`, { headers: { "X-User": currentUser() } });
    if (!r.ok) return setErr((await r.json()).detail);
    const a = document.createElement("a"); a.href = URL.createObjectURL(await r.blob()); a.download = `${route.args.code}.csv`; a.click();
  };
  if (err && !s) return <div className="callout err">{err.message}{err.suggestions && <div className="chips" style={{ marginTop: 6, display: "flex", gap: 6 }}>{err.suggestions.map((x: string) => <button key={x} className="chip" onClick={() => run(x)}>{x}</button>)}</div>}</div>;
  if (!s) return <div className="note">carregando…</div>;
  const obs = s.observations;
  return (
    <div className="view">
      <div style={{ display: "flex", gap: 16, alignItems: "baseline", flexWrap: "wrap" }}>
        <h3 style={{ margin: 0 }}>{s.name}</h3>
        <span className="px mono" style={{ fontSize: 18 }}>{num(obs[0]?.value, 2)}</span><span className="dim">{s.unit}</span>
        <span>ref. <b className="mono">{dt(obs[0]?.date)}</b></span><span className="dim">publicado {dt(obs[0]?.published_at)}</span>
        <span style={{ flex: 1 }} />
        <label className="dim">Como se sabia em <input type="date" className="field" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></label>
        <button className="btn" onClick={exp}>Exportar CSV</button>
      </div>
      {err && <div className="callout err">{err.message}</div>}
      <div className="kvs" style={{ padding: "8px 0" }}>
        <span className="k">Fonte</span><span className="v">{s.source_name} — chave {s.source_key}</span>
        <span className="k">Frequência</span><span className="v">{s.frequency}</span>
        <span className="k">Publicação</span><span className="v">{s.publication_rule}</span>
        <span className="k">Notas</span><span className="v">{s.notes}</span>
        <span className="k">Licença</span><span className="v dim">{s.license}</span>
        <span className="k">Payload</span><span className="v mono dim" style={{ fontSize: 10.5 }}>{obs[0]?.payload} ({obs[0]?.payload_mode})</span>
      </div>
      <Spark pts={obs.slice().reverse().map((o: any) => Number(o.value)).filter((x: number) => isFinite(x))} />
      <table className="tbl"><thead><tr><th>Data de referência</th><th>Valor</th><th>Publicado</th><th>Vintage</th></tr></thead><tbody>
        {obs.slice(0, 120).map((o: any) => <tr key={o.date}><td className="mono">{dt(o.date)}</td><td className="num mono">{o.value === null ? <span className="dim" title="ausente na fonte (não é zero)">ausente</span> : num(o.value, 2)}</td>
          <td className="mono dim">{dt(o.published_at)}</td><td className="num">{o.vintage}</td></tr>)}
      </tbody></table>
    </div>
  );
}

export function Watch({ route }: { route: Route }) {
  const [w, setW] = useState<any>(null);
  const [add, setAdd] = useState("");
  const { quotes } = useQuotes();
  const load = () => api(`/api/watchlists/${route.args.name}`).then(setW);
  useEffect(() => {
    const ops: string[] = route.args.ops || [];
    const a = ops.filter((o) => o.startsWith("+")).map((o) => o.slice(1)), r = ops.filter((o) => o.startsWith("-")).map((o) => o.slice(1));
    (a.length || r.length ? post(`/api/watchlists/${route.args.name}`, { add: a, remove: r }).then((x) => { setW(x); window.dispatchEvent(new Event("meridiano:watch")); }) : load());
  }, [route.text, JSON.stringify(route.args.ops)]);
  const edit = async (body: any) => { setW(await post(`/api/watchlists/${route.args.name}`, body)); window.dispatchEvent(new Event("meridiano:watch")); };
  if (!w) return <div className="note">carregando…</div>;
  return (
    <div className="view">
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <input className="field" placeholder="TICKER:BOLSA" value={add} onChange={(e) => setAdd(e.target.value.toUpperCase())} onKeyDown={(e) => e.key === "Enter" && add && edit({ add: [add] }).then(() => setAdd(""))} />
        <button className="btn" onClick={() => add && edit({ add: [add] }).then(() => setAdd(""))}>Adicionar</button>
        <span className="dim">Lista persistente de {currentUser()} · {w.items.length} itens</span>
      </div>
      <table className="tbl"><thead><tr><th>Ativo</th><th>Nome</th><th>Último</th><th>Var. %</th><th>Feed</th><th>Obs.</th><th></th></tr></thead><tbody>
        {w.items.map((it: any) => { const q = quotes[it.ticker] || it; return (
          <tr key={it.ticker}><td className="mono" style={{ cursor: "pointer" }} onClick={() => openInGroup(it)}>{it.ticker}</td><td className="dim">{it.name}</td>
            <td className="num mono">{q.price ? num(q.price, 2) : "—"}</td><td className={"num mono " + dir(q.change_pct)}>{q.change_pct ? signed(q.change_pct, 2, "%") : ""}</td>
            <td><span className={"badge " + (q.feed_class === "simulated" ? "sim" : "eod")}>{q.feed_label}</span></td><td className="mono dim">{q.observed_at?.slice(0, 19).replace("T", " ")}</td>
            <td><button className="btn" onClick={() => edit({ remove: [it.ticker] })}>remover</button></td></tr>); })}
      </tbody></table>
    </div>
  );
}
