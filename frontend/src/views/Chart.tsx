// CHART: estação gráfica. Estado por usuário/instrumento (tipo, escala, base, estudos, benchmark, visão, candle),
// requisições canceladas ao trocar de ativo e respostas atrasadas descartadas.
import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, post, put } from "../api";
import ChartCanvas, { ChartHandle, Drawing, Evt, fmtP, StudyDef, View, evtGlyph } from "../components/ChartCanvas";
import { dt, num, signed, dir } from "../format";
import { readUrl, run, writeUrl } from "../nav";
import { fnKey, get, loadState, Route, saveState, set, useStore } from "../store";

const PALETTE = ["#e8b04a", "#8ab4ff", "#c08bff", "#46d3c3", "#ff9b9b", "#f5d76e"];
export const DEFAULT_STUDIES = [
  { key: "sma20", id: "sma", params: { n: 20 } }, { key: "sma200", id: "sma", params: { n: 200 } },
];
const TOOLS: [string, string][] = [["trend", "Tendência"], ["hline", "Horizontal"], ["channel", "Canal"], ["rect", "Retângulo"], ["fib", "Fibonacci"], ["measure", "Medir %"], ["note", "Anotação"]];

type CState = { type: "candle" | "ohlc" | "line" | "area"; log: boolean; basis: "adjusted" | "raw"; studies: { key: string; id: string; params: any }[];
  bench: string; showEvents: boolean; view?: View; candle?: string; sidebar: boolean };
const DEF: CState = { type: "candle", log: false, basis: "adjusted", studies: DEFAULT_STUDIES, bench: "BOVA11", showEvents: true, sidebar: true };

let reqSeq = 0;

export default function Chart({ route }: { route: Route }) {
  const interval = route.args?.interval || "1D";
  const window_ = route.args?.window || "2Y";
  const [st, setSt] = useState<CState | null>(null);
  const [catalog, setCatalog] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [view, setView] = useState<View>({ from: 0, to: 100 });
  const [cursor, setCursor] = useState<number | null>(null);
  const [drawings, setDrawings] = useState<Drawing[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [tool, setTool] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [picker, setPicker] = useState(false);
  const [alertOpen, setAlertOpen] = useState(false);
  const [alerts, setAlerts] = useState<any>(null);
  const chart = useRef<ChartHandle>(null);
  const contrast = useStore((s) => (s as any).contrast);
  const key = fnKey(route);

  useEffect(() => { api("/api/studies", { cacheMs: 600000 }).then(setCatalog); }, []);
  useEffect(() => {
    setSt(null); setData(null);
    loadState<CState>(key).then((s) => setSt({ ...DEF, ...(s || {}) }));
  }, [key]);

  // dados: cancela requisição anterior e descarta resposta de outro ativo/época
  useEffect(() => {
    if (!st || !route.listing_id) return;
    const my = ++reqSeq; const ctl = new AbortController();
    const studies = st.studies.map((s) => ({ ...s, params: s.params }));
    const delay = new URLSearchParams(location.search).get("delay_" + route.ticker) || "0";
    const qs = new URLSearchParams({ interval, window: window_, basis: st.basis, studies: JSON.stringify(studies), bench: st.bench, delay_ms: delay });
    setErr(null);
    fetch(`/api/chart/${route.listing_id}?${qs}`, { signal: ctl.signal, headers: { "X-User": localStorage.getItem("meridiano.user") || "ana" } })
      .then((r) => r.json().then((j) => { if (!r.ok) throw new ApiError(r.status, j.detail); return j; }))
      .then((d) => {
        if (my !== reqSeq || d.listing.id !== get().route?.listing_id) { (window as any).__meridianoStale = ((window as any).__meridianoStale || 0) + 1; return; }
        setData(d);
        const n = d.bars.length;
        const urlCandle = readUrl().cell?.startsWith("candle:") ? readUrl().cell!.slice(7) : undefined;
        const candle = urlCandle || st.candle;
        const ci = candle ? d.bars.findIndex((b: any) => b.t === candle) : -1;
        const okView = st.view && isFinite(st.view.from) && isFinite(st.view.to) && st.view.to - st.view.from >= 5 && st.view.from < n && st.view.to <= n + 20;
        const v = okView && !urlCandle ? st.view! : { from: d.visible_from, to: n };
        if (ci >= 0 && (ci < v.from || ci >= v.to)) { const sp = v.to - v.from; setView({ from: Math.max(0, ci - sp / 2), to: Math.max(0, ci - sp / 2) + sp }); } else setView(v);
        setCursor(ci >= 0 ? ci : n - 1);
        setTimeout(() => chart.current?.focus(), 0);
      })
      .catch((e) => { if (e.name !== "AbortError" && my === reqSeq) setErr(e.detail || { message: e.message }); });
    api(`/api/drawings/${route.instrument_id}?basis=${st.basis}`).then((r) => { if (my === reqSeq) setDrawings(r.drawings.map((x: any) => ({ ...x, points: x.points }))); });
    return () => ctl.abort();
  }, [route.listing_id, interval, window_, st?.basis, JSON.stringify(st?.studies), st?.bench]);

  // persistência (debounced pelo saveState)
  useEffect(() => { if (st && data && data.bars.length && get().route === route) { saveState(key, { ...st, view, candle: cursor != null ? data.bars[cursor]?.t : undefined }); if (cursor != null && data.bars[cursor]) writeUrl(route, { cell: `candle:${data.bars[cursor].t}` }); } }, [st, view, cursor]);
  const saveDrawings = (d: Drawing[]) => { setDrawings(d); clearTimeout((window as any).__drawT); (window as any).__drawT = setTimeout(() => put(`/api/drawings/${route.instrument_id}`, { basis: st!.basis, drawings: d }), 400); };

  const defs: StudyDef[] = useMemo(() => (st?.studies || []).map((s, i) => {
    const c = catalog?.[s.id]; const ps = Object.entries(s.params || {}).filter(([, v]) => v != null).map(([, v]) => v).join(",");
    return { key: s.key, id: s.id, params: s.params, pane: (c?.pane || "own") as any, color: PALETTE[i % PALETTE.length], label: `${c?.label || s.id}${ps ? ` (${ps})` : ""}` };
  }), [st?.studies, catalog]);

  if (!st) return <div className="note">carregando…</div>;
  const set_ = (patch: Partial<CState>) => setSt({ ...st, ...patch });
  const bar = data && cursor != null ? data.bars[cursor] : null;
  const prev = data && cursor ? data.bars[cursor - 1] : null;
  const base = `${route.ticker} ${route.exchange || ""}`.trim();

  const saveAnalysis = async () => {
    const t = await api(`/api/thesis/${route.instrument_id}`);
    const v = t.versions?.[0];
    const ctx = { cmd: route.text, candle: bar?.t, studies: st.studies, bench: st.bench, basis: st.basis, drawings: drawings.length,
                  events: data.events.filter((e: Evt) => e.tradable_session?.session_date === bar?.t).map((e: Evt) => ({ id: e.id, headline: e.headline, source: e.source })) };
    await post(`/api/thesis/${route.instrument_id}`, { title: t.thesis?.title || `Análise ${route.ticker}`, stance: t.thesis?.stance || "neutral",
      body: (v?.body || "") + `\n\n[${new Date().toLocaleString("pt-BR")}] Análise gráfica em ${bar?.t}: fechamento ${bar?.c}; estudos ${defs.map((d) => d.label).join(", ")}.`,
      assumptions: v?.assumptions || [], context: ctx });
    setNote(`Análise salva na tese (candle ${bar?.t}). THESIS ${route.ticker}:${route.exchange} → "voltar ao ponto" reabre este candle.`);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="toolbar">
        <b className="mono">{route.ticker}</b>
        <div className="seg" title="duração de cada candle">{["5m", "1D", "1W", "1M"].map((i) => <button key={i} className={interval === i ? "on" : ""} onClick={() => run(`${base} CHART ${i === "5m" ? "5MIN" : i} ${i === "5m" ? "1D" : window_ === "1D" ? "2Y" : window_}`)}>{i === "5m" ? "5min" : i}</button>)}</div>
        <div className="seg" title="janela inicialmente exibida">{["3M", "6M", "YTD", "1Y", "2Y"].map((w) => <button key={w} className={window_ === w ? "on" : ""} onClick={() => { set_({ view: undefined }); run(`${base} CHART ${interval === "5m" ? "1D" : interval} ${w}`); }}>{w}</button>)}</div>
        <select className="field" value={st.type} onChange={(e) => set_({ type: e.target.value as any })} aria-label="tipo de gráfico">
          <option value="candle">Candles</option><option value="ohlc">Barras OHLC</option><option value="line">Linha</option><option value="area">Área</option></select>
        <div className="seg"><button className={!st.log ? "on" : ""} onClick={() => set_({ log: false })}>Linear</button><button className={st.log ? "on" : ""} onClick={() => set_({ log: true })}>Log</button></div>
        <div className="seg" title="ajuste de preço"><button className={st.basis === "adjusted" ? "on" : ""} onClick={() => set_({ basis: "adjusted" })}>Ajustado</button><button className={st.basis === "raw" ? "on" : ""} onClick={() => set_({ basis: "raw" })}>Bruto</button></div>
        <button className="btn" onClick={() => setPicker(!picker)}>Estudos ▾</button>
        <label className="dim">vs <input className="field" style={{ width: 70 }} value={st.bench} onChange={(e) => set_({ bench: e.target.value.toUpperCase() })} title="benchmark para força relativa/comparação" /></label>
        <button className={"btn" + (st.showEvents ? " pri" : "")} onClick={() => set_({ showEvents: !st.showEvents })}>Eventos</button>
        <button className="btn" onClick={() => setAlertOpen(!alertOpen)}>Alertas</button>
        <button className="btn" onClick={() => chart.current?.back()} title="voltar à visão anterior (Backspace)">↶ Visão</button>
        <button className="btn" onClick={() => set_({ sidebar: !st.sidebar })}>Desenhos {st.sidebar ? "◂" : "▸"}</button>
        <span style={{ flex: 1 }} />
        {data && <button className="btn pri" onClick={saveAnalysis}>Salvar análise</button>}
      </div>
      {picker && catalog && <StudyPicker catalog={catalog} studies={st.studies} onChange={(s) => set_({ studies: s })} onClose={() => setPicker(false)} />}
      {alertOpen && data && <AlertBox listingId={route.listing_id!} onFires={setAlerts} />}
      {data && (
        <div className="note" style={{ display: "flex", gap: 10, flexWrap: "wrap", borderBottom: "1px solid var(--line)", alignItems: "center" }}>
          {bar ? <span className="mono">
            {dt(bar.t)} · A {fmtP(bar.o)} · M {fmtP(bar.h)} · m {fmtP(bar.l)} · F <b style={{ color: "var(--fg)" }}>{fmtP(bar.c)}</b> · Vol {num((bar.v || 0) / 1e6, 1)} mi
            {prev && <span className={dir(bar.c - prev.c)}> · {signed(((bar.c / prev.c) - 1) * 100, 2, "%")}</span>}
            {defs.map((d) => { const s = data.studies[d.key]?.series; if (!s) return null; return <span key={d.key} style={{ color: d.color }}> · {d.label} {Object.values(s).map((x: any) => x[cursor!] == null ? "aquec." : fmtP(x[cursor!])).join("/")}</span>; })}
          </span> : null}
          <span className="badge eod" title={data.basis.note}>{data.basis.basis === "adjusted" ? "AJUSTADO" : "BRUTO"}</span>
          <span className={"badge " + (data.feed.daily?.state === "eod" ? "eod" : "warn")} title={data.feed.daily?.label}>{data.feed.daily?.label || data.feed.intraday?.label}</span>
          {data.feed.intraday && interval !== "1D" && <span className={"badge " + (data.feed.intraday.state === "interrupted" ? "interrupted" : "sim")}>{data.feed.intraday.label}</span>}
        </div>
      )}
      {note && <div className="callout info" onClick={() => setNote(null)}>{note}</div>}
      {err && <div className="callout err">{err.message}</div>}
      {alerts && <div className="callout info">Alerta: <b>{alerts.condition}</b> — {alerts.new_fires.length} disparo(s) no histórico {alerts.new_fires.slice(-3).map((f: any) => f.session_date).join(", ")} (política: {alerts.rule.dedupe}, modo {alerts.rule.mode}).</div>}
      <div style={{ flex: 1, minHeight: 0, display: "flex" }}>
        {st.sidebar && (
          <div style={{ width: 118, borderRight: "1px solid var(--line)", padding: 6, display: "flex", flexDirection: "column", gap: 4, overflow: "auto" }} aria-label="ferramentas de desenho">
            {TOOLS.map(([k, l]) => <button key={k} className={"btn" + (tool === k ? " pri" : "")} onClick={() => setTool(tool === k ? null : k)}>{l}</button>)}
            <div className="dim" style={{ fontSize: 10.5, marginTop: 6 }}>Objetos ({drawings.length}) · base {st.basis}</div>
            {drawings.map((d, i) => (
              <div key={i} className={selected === i ? "sel" : ""} style={{ fontSize: 10.5, display: "flex", gap: 2, alignItems: "center", background: selected === i ? "var(--bg-3)" : "none", borderRadius: 3, padding: "1px 2px" }}>
                <span style={{ flex: 1, cursor: "pointer" }} onClick={() => setSelected(i)}>{d.kind}{d.text ? `: ${d.text}` : ""}</span>
                <button className="ibtn" style={{ width: 16, height: 16 }} title={d.locked ? "desbloquear" : "bloquear"} onClick={() => saveDrawings(drawings.map((x, k) => (k === i ? { ...x, locked: !x.locked } : x)))}>{d.locked ? "🔒" : "🔓"}</button>
                <button className="ibtn" style={{ width: 16, height: 16 }} title={d.hidden ? "mostrar" : "ocultar"} onClick={() => saveDrawings(drawings.map((x, k) => (k === i ? { ...x, hidden: !x.hidden } : x)))}>{d.hidden ? "◌" : "●"}</button>
                <button className="ibtn" style={{ width: 16, height: 16 }} title="excluir" disabled={d.locked} onClick={() => { saveDrawings(drawings.filter((_, k) => k !== i)); setSelected(null); }}>×</button>
              </div>
            ))}
            {(drawings as any[]).some((d) => d.foreign_basis) && <div className="dim" style={{ fontSize: 10 }}>Alguns objetos pertencem a outra base de preço.</div>}
          </div>
        )}
        <div style={{ flex: 1, minWidth: 0, position: "relative" }}>
          {data && data.bars.length > 0 ? (
            <ChartCanvas ref={chart} bars={data.bars} studies={data.studies} defs={defs} events={data.events} drawings={drawings} type={st.type} log={st.log}
                         view={view} cursor={cursor} tool={tool} selected={selected} showEvents={st.showEvents} contrast={contrast}
                         onView={(v) => setView(v)} onCursor={setCursor} onEvent={(e) => set({ selectedEvent: e } as any)}
                         onDrawings={saveDrawings} onSelect={setSelected} onToolDone={() => setTool(null)} onLogInvalid={(m) => { setNote(m); set_({ log: false }); }} />
          ) : data ? <div className="callout">{data.feed.daily?.label || data.feed.intraday?.label}</div> : !err && <div className="note">carregando gráfico…</div>}
        </div>
      </div>
      {data && <div className="note" style={{ borderTop: "1px solid var(--line)" }}>
        Fonte {data.source} · {data.sessions_note} · {data.warmup_policy} · arraste = mover · roda = zoom no cursor · Shift+arraste = selecionar intervalo · duplo clique = janela padrão · Backspace = visão anterior · ←/→ candle · eventos: {["earnings", "filing", "dividend", "news", "macro"].map((t) => <span key={t} style={{ color: evtGlyph(t)[1], marginLeft: 4 }}>{evtGlyph(t)[0]}={({ earnings: "resultado", filing: "demonstração", dividend: "proventos", news: "comunicado", macro: "macro" } as any)[t]}</span>)}
      </div>}
    </div>
  );
}

function StudyPicker({ catalog, studies, onChange, onClose }: { catalog: any; studies: any[]; onChange: (s: any[]) => void; onClose: () => void }) {
  const groups: Record<string, string[]> = {};
  Object.entries(catalog).forEach(([k, v]: any) => (groups[v.group] ||= []).push(k));
  const add = (id: string) => onChange([...studies, { key: `${id}${Date.now() % 100000}`, id, params: { ...catalog[id].params } }]);
  return (
    <div className="box" style={{ margin: 6, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, maxHeight: 330, overflow: "auto" }}>
      <div>
        {Object.entries(groups).map(([g, ids]) => <div key={g}><div className="dim" style={{ fontSize: 10.5, marginTop: 4 }}>{g}</div>
          {ids.map((id) => <button key={id} className="chip" style={{ margin: 2 }} title={catalog[id].doc} onClick={() => add(id)}>+ {catalog[id].label}</button>)}</div>)}
      </div>
      <div>
        <div className="dim" style={{ fontSize: 10.5 }}>Ativos (fórmula, parâmetros, aquecimento)</div>
        {studies.map((s, i) => (
          <div key={s.key} style={{ borderBottom: "1px solid var(--line)", padding: "3px 0" }}>
            <b>{catalog[s.id]?.label}</b> <button className="ibtn" style={{ width: 16, height: 16 }} onClick={() => onChange(studies.filter((_, k) => k !== i))}>×</button>
            <div>{Object.entries(s.params || {}).map(([k, v]) => <label key={k} className="dim" style={{ marginRight: 6 }}>{k} <input className="field" style={{ width: k === "anchor" ? 100 : 46 }} type={k === "anchor" ? "date" : "text"} value={(v as any) ?? ""}
              onChange={(e) => onChange(studies.map((x, j) => j === i ? { ...x, params: { ...x.params, [k]: k === "anchor" || k === "bench" ? e.target.value : Number(e.target.value) || e.target.value } } : x))} /></label>)}</div>
            <div className="dim" style={{ fontSize: 10.5 }}>{catalog[s.id]?.doc}</div>
          </div>
        ))}
        <button className="btn" style={{ marginTop: 6 }} onClick={onClose}>Fechar</button>
      </div>
    </div>
  );
}

function AlertBox({ listingId, onFires }: { listingId: string; onFires: (r: any) => void }) {
  const [kind, setKind] = useState("breakout_high"); const [n, setN] = useState(20); const [level, setLevel] = useState(""); const [mode, setMode] = useState("close"); const [dedupe, setDedupe] = useState("once_per_bar");
  const create = async () => {
    const params: any = kind.startsWith("breakout") ? { n } : kind === "price_cross" ? { level: Number(level), dir: "up" } : kind === "ma_cross" ? { n, type: "sma", dir: "up" } : kind === "rsi_level" ? { n: 14, level: Number(level || 70), dir: "up" } : { n, k: Number(level || 2) };
    onFires(await post("/api/alerts", { listing_id: listingId, kind, params, mode, dedupe }));
  };
  return (
    <div className="toolbar">
      <select className="field" value={kind} onChange={(e) => setKind(e.target.value)}>
        <option value="breakout_high">Rompimento de máxima de N sessões</option><option value="breakout_low">Rompimento de mínima de N sessões</option>
        <option value="price_cross">Cruzamento de preço</option><option value="ma_cross">Cruzamento de média</option><option value="rsi_level">RSI cruza nível</option><option value="rel_volume">Volume relativo ≥ k</option></select>
      {(kind.startsWith("breakout") || kind === "ma_cross" || kind === "rel_volume") && <label className="dim">N <input className="field" style={{ width: 44 }} value={n} onChange={(e) => setN(Number(e.target.value) || 20)} /></label>}
      {(kind === "price_cross" || kind === "rsi_level" || kind === "rel_volume") && <label className="dim">nível/k <input className="field" style={{ width: 60 }} value={level} onChange={(e) => setLevel(e.target.value)} /></label>}
      <select className="field" value={mode} onChange={(e) => setMode(e.target.value)}><option value="close">no fechamento confirmado</option><option value="intrabar">intrabar</option></select>
      <select className="field" value={dedupe} onChange={(e) => setDedupe(e.target.value)}><option value="once_per_bar">1 vez por barra</option><option value="once">só a 1ª vez</option><option value="every">toda ocorrência</option></select>
      <button className="btn pri" onClick={create}>Criar e avaliar histórico</button>
    </div>
  );
}
