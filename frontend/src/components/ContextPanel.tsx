// Painel de contexto: inspetor de proveniência da célula, instrumentos fixados, estado dos feeds e fita de eventos.
import { useEffect, useRef, useState } from "react";
import { api, post } from "../api";
import { dir, dt, num, signed, timeOnly } from "../format";
import { useQuotes } from "../quotes";
import { set, useStore } from "../store";
import { IDoc, IPause, IPin, IPlay } from "./Icons";
import { NewsEvidence } from "../views/News";
import { run } from "../nav";

function EventEvidence() {
  const e = useStore((s) => s.selectedEvent);
  const route = useStore((s) => s.route);
  if (!e) return null;
  return (
    <div className="sect"><h4><span>Evento no gráfico</span><button className="ibtn" onClick={() => set({ selectedEvent: null })}>×</button></h4>
      <div className="kvs">
        <span className="k">Evento</span><span className="v"><b>{e.headline}</b></span>
        <span className="k">Tipo</span><span className="v">{e.type} · {e.relation === "macro" ? "relação macro" : "vínculo direto"}</span>
        <span className="k">Publicado</span><span className="v">{e.precision === "day" ? `${dt(e.published_at, "America/Sao_Paulo").slice(0, 8)} (fonte informa só o dia)` : `${dt(e.published_at, "America/New_York")} ET · ${dt(e.published_at, "America/Sao_Paulo")} BRT`}</span>
        <span className="k">1ª sessão negociável</span><span className="v">{dt(e.tradable_session.session_date)} — {e.tradable_session.status}</span>
        <span className="k">Fonte</span><span className="v">{e.source} {e.url && <a href={e.url} target="_blank" rel="noopener noreferrer">abrir original ↗</a>}</span>
      </div>
      <div style={{ display: "flex", gap: 6, padding: "0 10px 8px", flexWrap: "wrap" }}>
        {e.document_id && route?.ticker && <button className="btn" onClick={() => run(`${route.ticker} ${route.exchange} FIN Q IS`)}>Conferir fundamentos</button>}
        {route?.ticker && <button className="btn" onClick={() => run(`${route.ticker} ${route.exchange} EVENTS`)}>Todos os eventos</button>}
      </div>
    </div>
  );
}

function AssetNews() {
  const route = useStore((s) => s.route);
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    if (!route?.ticker || !route.issuer_id) { setItems([]); return; }
    let alive = true; const my = route.listing_id;
    api(`/api/news?tab=ticker&ticker=${route.ticker}&limit=12`).then((r) => { if (alive && my === route.listing_id) setItems(r.items); }).catch(() => setItems([]));
    return () => { alive = false; };
  }, [route?.listing_id]);
  if (!items.length) return null;
  return (
    <div className="sect"><h4><span>Notícias · {route?.ticker}</span></h4>
      <table className="tbl"><tbody>{items.map((n) => <tr key={n.id} style={{ cursor: "pointer" }} onClick={() => set({ selectedNews: n.id })}>
        <td className="mono dim" style={{ fontSize: 10, width: 62 }}>{dt(n.published_at, "America/Sao_Paulo").slice(0, 8)}</td><td style={{ whiteSpace: "normal", fontSize: 11 }}>{n.headline}</td></tr>)}</tbody></table>
    </div>
  );
}

function NewsPane() {
  const id = useStore((s) => s.selectedNews);
  if (!id) return null;
  return <div className="sect"><h4><span>Notícia / comunicado</span><button className="ibtn" onClick={() => set({ selectedNews: null })}>×</button></h4><NewsEvidence id={id} onClose={() => set({ selectedNews: null })} /></div>;
}

function Inspector() {
  const cell = useStore((s) => s.selectedCell);
  const factId = useStore((s) => s.selectedFact);
  const [L, setL] = useState<any>(null);
  const [rec, setRec] = useState<any>(null);
  const [inputs, setInputs] = useState<any[]>([]);
  useEffect(() => {
    setL(null); setRec(null); setInputs([]);
    if (factId) api(`/api/facts/${factId}`).then(setL).catch(() => {});
    if (cell?.basis === "calculated" && cell.inputs?.length) Promise.all(cell.inputs.map((i: number) => api(`/api/facts/${i}`))).then(setInputs).catch(() => {});
  }, [factId, cell?.pos?.r, cell?.pos?.c, cell?.statement, cell?.freq]);
  if (!cell) return <div className="note">Selecione uma célula de uma demonstração (Enter) para ver valor original, escala, período, escopo, documento, localização e transformações.</div>;
  const scaleTxt = (s: number) => ({ 0: "unidades", 3: "milhares", 6: "milhões" } as any)[s] || s;
  return (
    <div>
      <div className="kvs">
        <span className="k">Conta</span><span className="v">{cell.row.label} <span className="dim mono">{cell.row.concept}</span></span>
        <span className="k">Período</span><span className="v">{cell.col.label} <span className="dim">({cell.col.calendar})</span></span>
        <span className="k">Estado</span><span className="v">{cell.state === "absent" ? "ausente (não é zero)" : cell.state === "zero" ? "zero reportado" : cell.state === "not_comparable" ? "não comparável" : "valor"}
          {cell.basis && <span className={"badge " + (cell.basis === "calculated" ? "calc" : "")} style={{ marginLeft: 6 }}>{cell.basis === "calculated" ? "calculado pelo sistema" : cell.basis === "reported" ? "reportado" : cell.basis}</span>}</span>
        {cell.reason && (<><span className="k">Motivo</span><span className="v" style={{ color: "var(--warn)" }}>{cell.reason}</span></>)}
        {cell.formula && (<><span className="k">Fórmula</span><span className="v"><div className="formula">{cell.formula}</div></span></>)}
        {cell.sign_flipped && (<><span className="k">Sinal</span><span className="v">invertido p/ convenção do sistema (despesas e saídas negativas)</span></>)}
      </div>
      {L && (
        <div className="kvs">
          <span className="k">Valor original</span><span className="v mono">{L.location?.vl_conta ?? L.location?.shown ?? "—"} <span className="dim">({L.source.code === "CVM_DADOS" ? `escala ${L.location?.escala}` : `exibido em ${scaleTxt(L.scale)}`})</span></span>
          <span className="k">Valor (unid.)</span><span className="v mono">{num(L.value, 0)} {L.currency || L.unit}</span>
          <span className="k">Escopo</span><span className="v">{L.scope === "consolidated" ? "consolidado" : "individual"}{L.location?.grupo ? ` — ${L.location.grupo}` : ""}</span>
          <span className="k">Tag / conta</span><span className="v mono">{L.concept}</span>
          <span className="k">Documento</span><span className="v">{L.document.form} <span className="mono">{L.document.external_id}</span> v{L.document.version}</span>
          <span className="k">Divulgação</span><span className="v">{L.source.code === "CVM_DADOS" ? `${dt(L.published_at, "America/Sao_Paulo").slice(0, 8)} (precisão de dia, BRT)` : `${dt(L.published_at, "America/New_York")} ET · ${dt(L.published_at)} local`}</span>
          <span className="k">Ingestão</span><span className="v">{dt(L.ingested_at)} <span className="dim">({L.payload.mode})</span></span>
          <span className="k">Localização</span><span className="v mono" style={{ fontSize: 10.5 }}>{L.location.text}</span>
          <span className="k">Transformação</span><span className="v" style={{ fontSize: 11 }}>{L.transformations.join(" · ")}</span>
          <span className="k">Payload</span><span className="v mono" style={{ fontSize: 10, color: "var(--fg-3)" }}>{L.payload.request?.slice(0, 90)} · sha256 {L.payload.sha256?.slice(0, 12)}…</span>
          <span className="k">Licença</span><span className="v dim">{L.source.license}</span>
        </div>
      )}
      {inputs.length > 0 && (
        <div className="kvs"><span className="k">Entradas</span><span className="v">{inputs.map((x) => (
          <div key={x.fact_id} className="mono" style={{ fontSize: 10.5 }}>#{x.fact_id} {x.period.start}→{x.period.end} = {num(x.value)} <span className="dim">{x.document.form} {x.document.external_id}</span></div>))}</span></div>
      )}
      <div style={{ display: "flex", gap: 6, padding: "0 10px 8px", flexWrap: "wrap" }}>
        {factId && <button className="btn pri" onClick={() => set({ doc: { factId, returnTo: { row: cell.pos.r, col: cell.pos.c }, title: cell.row.label } })}><IDoc /> Abrir fonte <span className="kbd">S</span></button>}
        {factId && <button className="btn" onClick={() => api(`/api/facts/${factId}/reconcile`).then(setRec)}>Reconciliar com original</button>}
      </div>
      {rec && (
        <div className={"callout " + (rec.ok ? "info" : rec.ok === false ? "err" : "")}>
          {rec.ok === null ? rec.reason : <>
            <b>{rec.ok ? "Reconciliado" : "DIVERGENTE"}</b>: documento mostra <span className="mono">{rec.document_shows}</span> (escala {String(rec.document_scale)}{rec.document_sign === "-" ? ", sinal −" : ""}),
            recomposto <span className="mono">{num(rec.recomputed)}</span> = fato <span className="mono">{num(rec.fact_value)}</span> · {rec.currency} · {rec.scope} · {rec.period?.join(" → ")}</>}
        </div>
      )}
      {L?.versions?.length > 1 && (
        <div className="sect"><h4><span>Versões deste valor ({L.versions.length})</span></h4>
          <table className="tbl"><thead><tr><th>Publicado</th><th>Documento</th><th>Valor</th><th>Δ</th></tr></thead><tbody>
            {L.versions.map((v: any, i: number) => {
              const d = i > 0 && v.value !== null && L.versions[i - 1].value !== null ? Number(v.value) - Number(L.versions[i - 1].value) : null;
              return <tr key={v.fact_id} className={v.fact_id === L.fact_id ? "sel" : ""}><td>{dt(v.published_at, L.source.code === "CVM_DADOS" ? "America/Sao_Paulo" : "America/New_York").slice(0, 8)}</td><td className="mono" style={{ fontSize: 10.5 }}>{v.form} {v.document}{v.ordem ? ` (${v.ordem})` : ""}</td>
                <td className="num">{num(v.value)}</td><td className={"num " + (d ? dir(d) : "")}>{d ? signed(d / 1e6, 0, " mi") : ""}</td></tr>;
            })}</tbody></table>
        </div>
      )}
    </div>
  );
}

function Pinned() {
  const { quotes } = useQuotes();
  const link = useStore((s) => s.linkA);
  const fixed = ["BRENT", "USDBRL", "UST10Y"];
  const rows = [...fixed.map((t) => ({ t, grp: "fixo" })), ...(link?.ticker && !fixed.includes(link.ticker) ? [{ t: link.ticker, grp: "grupo A" }] : [])];
  return (
    <table className="tbl"><tbody>
      {rows.map(({ t, grp }) => {
        const q = quotes[t];
        return <tr key={t}><td><span className="mono">{t}</span> <span className="dim2" style={{ fontSize: 10 }}>{grp === "fixo" ? <IPin /> : "⛓ A"}</span></td>
          <td className="num mono">{q?.price ? num(q.price, q.kind === "gov_bond" ? 2 : 2) : "—"}</td>
          <td className={"num mono " + dir(q?.change_pct)} style={{ fontSize: 11 }}>{q?.change_pct ? signed(q.change_pct, 2, "%") : ""}</td>
          <td className="dim" style={{ fontSize: 10 }} title={q?.feed_label}>{q?.feed_class === "eod" ? `EOD ${dt(q.observed_at)}` : q?.feed_class === "simulated" ? "SIM " + timeOnly(q.observed_at) : q?.feed_state}</td></tr>;
      })}
    </tbody></table>
  );
}

function Feeds() {
  const { feeds } = useQuotes();
  const toggle = (code: string, on: boolean) => post(`/api/admin/feeds/${code}/interrupt`, { on });
  return (
    <table className="tbl"><tbody>
      {feeds.filter((f) => !["USER", "SYSTEM"].includes(f.code)).map((f) => (
        <tr key={f.code}><td className="mono" style={{ fontSize: 11 }}>{f.code}</td>
          <td><span className={"badge " + (f.interrupted ? "interrupted" : f.feed_class === "simulated" ? "sim" : "eod")}>{f.interrupted ? "interrompido" : f.feed_class}</span></td>
          <td className="dim" style={{ fontSize: 10.5 }}>{f.last_observation ? timeOnly(f.last_observation) : f.last_ingestion ? `ingest. ${f.last_ingestion.mode}` : ""}</td>
          <td>{f.code === "SIM_DEV" && <button className="btn" style={{ padding: "0 6px", fontSize: 10.5 }} onClick={() => toggle(f.code, !f.interrupted)}>{f.interrupted ? "restaurar" : "interromper"}</button>}</td></tr>
      ))}
    </tbody></table>
  );
}

function Tape() {
  const { tape } = useQuotes();
  const [paused, setPaused] = useState(false);
  const [shown, setShown] = useState<typeof tape>([]);
  const box = useRef<HTMLDivElement>(null);
  const atTop = () => (box.current?.scrollTop || 0) < 4;
  // pausado ou rolado: novidades ficam no contador, sem deslocar o que está sendo lido
  useEffect(() => { if (!paused && atTop()) setShown(tape.slice(0, 120)); }, [tape, paused]);
  const pending = shown.length && tape.length ? tape.findIndex((t) => t.seq === shown[0].seq) : tape.length;
  const latest = () => { setShown(tape.slice(0, 120)); setPaused(false); if (box.current) box.current.scrollTop = 0; };
  return (
    <div>
      <div style={{ display: "flex", gap: 6, padding: "0 10px 4px", alignItems: "center" }}>
        <button className="btn" onClick={() => setPaused(!paused)} aria-pressed={paused}>{paused ? <><IPlay /> retomar</> : <><IPause /> pausar</>}</button>
        <span className="dim" style={{ fontSize: 11 }}>{paused ? "pausado" : "ao vivo"} · eventos do feed simulado e de estado</span>
      </div>
      {pending > 0 && <div className="newbar" role="button" tabIndex={0} onClick={latest} onKeyDown={(e) => e.key === "Enter" && latest()}>{pending} novidade{pending > 1 ? "s" : ""} — ir para o mais recente</div>}
      <div className="tape" ref={box} tabIndex={0} aria-label="Fita de eventos">
        {shown.map((t) => (
          <div className="ti" key={t.seq}><span className="dim">{timeOnly(t.at)}</span><span>{t.type === "quote" ? t.ticker : t.source}</span>
            <span className={t.type === "feed" ? (t.state === "interrupted" ? "down" : "up") : ""}>{t.type === "quote" ? num(t.price, 2) : t.state}</span></div>
        ))}
      </div>
    </div>
  );
}

export default function ContextPanel() {
  return (
    <div>
      <NewsPane />
      <EventEvidence />
      <div className="sect"><h4><span>Fonte da célula</span></h4><Inspector /></div>
      <AssetNews />
      <div className="sect"><h4><span>Fixados · grupo A</span><span className="dim2" style={{ flex: 0, whiteSpace: "nowrap", letterSpacing: 0, textTransform: "none" }}>fixos não seguem o ativo</span></h4><Pinned /></div>
      <div className="sect"><h4><span>Feeds</span></h4><Feeds /></div>
      <div className="sect"><h4><span>Fita</span></h4><Tape /></div>
    </div>
  );
}
