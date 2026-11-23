// NEWS: abas, ordem cronológica no Ao Vivo, histórias agrupadas, tipo editorial, vínculo com ativos (direto/setorial/macro),
// "novas manchetes" sem deslocar a leitura, e "Ver reação no gráfico".
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { dt } from "../format";
import { run } from "../nav";
import { Route, set, useStore } from "../store";

const TABS: [string, string][] = [["top", "Principais do Dia"], ["live", "Ao Vivo"], ["br", "Brasil"], ["us", "EUA"], ["asia", "Ásia"], ["eu", "Europa"],
  ["bridge", "Ponte Brasil–EUA"], ["watchlist", "Minha Watchlist"], ["portfolio", "Minha Carteira"]];
export const KIND: Record<string, string> = { official_release: "comunicado oficial", regulatory_filing: "documento regulatório", central_bank: "banco central",
  report: "reportagem", analysis: "análise", opinion: "opinião", unconfirmed: "não confirmado" };

export default function News({ route }: { route: Route }) {
  const tab = route.args?.tab || "top";
  const [d, setD] = useState<any>(null);
  const [fresh, setFresh] = useState<any[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const q = `/api/news?tab=${tab}${route.args?.ticker ? `&ticker=${route.args.ticker}` : ""}`;
  useEffect(() => {
    let alive = true; const ctl = new AbortController();
    setD(null); setFresh([]);
    api(q).then((r) => { if (alive) setD(r); });
    // poll: novidades viram contador quando o leitor não está no topo (não desloca a lista)
    const t = setInterval(() => api(q).then((r) => {
      if (!alive) return;
      setD((cur: any) => {
        if (!cur) return r;
        const known = new Set(cur.items.map((i: any) => i.id));
        const nw = r.items.filter((i: any) => !known.has(i.id));
        const base = { ...cur, updated_at: r.updated_at };
        if (!nw.length) return base;
        if ((box.current?.scrollTop || 0) < 4) return { ...base, items: [...nw, ...cur.items] };
        setFresh((f) => [...nw.filter((x: any) => !f.some((y) => y.id === x.id)), ...f]);
        return base;
      });
    }), 30000);
    return () => { alive = false; ctl.abort(); clearInterval(t); };
  }, [q]);
  const go = (t: string) => run(t === "ticker" ? `NEWS ${route.ticker}:${route.exchange}` : `NEWS ${({ top: "WORLD", live: "LIVE", br: "BR", us: "US", asia: "ASIA", eu: "EU", bridge: "BRIDGE", watchlist: "WATCH", portfolio: "PORTFOLIO" } as any)[t]}`);
  const flush = () => { setD((c: any) => ({ ...c, items: [...fresh, ...c.items] })); setFresh([]); if (box.current) box.current.scrollTop = 0; };
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="tabs">{TABS.map(([k, l]) => <button key={k} className={tab === k ? "on" : ""} onClick={() => go(k)}>{l}</button>)}
        {route.args?.ticker && <button className="on">{route.args.ticker}</button>}</div>
      {fresh.length > 0 && <div className="newbar" role="button" tabIndex={0} onClick={flush}>{fresh.length} novas manchetes — ir para o topo</div>}
      <div ref={box} className="pb" tabIndex={0}>
        {!d ? <div className="note">carregando…</div> : (
          <>
            {d.note && <div className="callout">{d.note}</div>}
            {d.items.length === 0 && !d.note && <div className="callout">Nenhum item nesta aba com as fontes integradas. {tab === "asia" || tab === "eu" ? "Veículos asiáticos/europeus dependem de contrato (ver catálogo abaixo)." : ""}</div>}
            <div className="note"><span className="up">● ao vivo</span> — fontes consultadas a cada 2 min{d.updated_at ? `, última às ${new Date(d.updated_at).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" })} BRT` : ""}. Ordem: {d.ordering}. Fontes integradas são primárias e de uso autorizado; veículos jornalísticos aparecem no catálogo como "depende de contrato".</div>
            <table className="tbl"><tbody>
              {d.items.map((n: any) => (
                <tr key={n.id} className={open === n.id ? "sel" : ""} style={{ cursor: "pointer", verticalAlign: "top" }} tabIndex={0}
                    onClick={() => { setOpen(n.id); set({ selectedNews: n.id } as any); }} onKeyDown={(e) => e.key === "Enter" && (setOpen(n.id), set({ selectedNews: n.id } as any))}>
                  <td className="mono dim" style={{ width: 112, fontSize: 10.5 }}>{n.time_precision === "day" ? dt(n.published_at, "America/Sao_Paulo").slice(0, 8) + " (dia)" : dt(n.published_at)}</td>
                  <td style={{ whiteSpace: "normal" }}>
                    <div>{n.material && <span className="badge warn" style={{ marginRight: 4 }}>material</span>}<b style={{ fontWeight: 500 }}>{n.headline}</b></div>
                    <div className="dim" style={{ fontSize: 10.5 }}>{n.outlet} · via {n.distributor} · <span className="badge">{KIND[n.kind]}</span> · {n.lang.toUpperCase()}
                      {n.story && <> · <span className="badge calc">história: {n.story.size} itens ({n.story.sources.join(" + ")})</span></>}
                      {n.links.map((l: any, i: number) => <span key={i} className="mono" style={{ marginLeft: 6 }} title={l.rationale}>{l.ticker}<span className="dim2">·{l.relation === "direct" ? "direto" : l.relation === "macro" ? "macro" : "setor"}</span></span>)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody></table>
            <h3 style={{ padding: "0 10px" }}>Catálogo de fontes</h3>
            <table className="tbl"><tbody>{d.catalog.map((c: any) => <tr key={c.source}><td>{c.source}</td><td className={c.status.startsWith("integrado") ? "up" : "dim"}>{c.status}</td><td className="dim">{c.rights}</td><td className="dim">{c.precision}</td></tr>)}</tbody></table>
          </>
        )}
      </div>
    </div>
  );
}

// Faixa persistente no rodapé: uma manchete por vez (8 s), pausa, anterior, próxima e modo contínuo; respeita movimento reduzido.
export function NewsTicker() {
  const [items, setItems] = useState<any[]>([]);
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const reduce = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const pausedRef = useRef(paused); pausedRef.current = paused;
  const arrive = (nw: any[]) => { if (nw.length && !pausedRef.current) setI(0); };   // manchete nova vai para a faixa (exceto pausada)
  const load = () => api("/api/news?tab=live&limit=30").then((r) => setItems((cur) => {
    const ids = new Set(cur.map((x) => x.id)); const nw = r.items.filter((x: any) => !ids.has(x.id));
    if (cur.length) arrive(nw);
    return nw.length ? [...nw, ...cur].slice(0, 40) : cur.length ? cur : r.items;
  })).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 30000); (window as any).__meridianoTickerPush = (it: any) => { setItems((c) => [it, ...c]); arrive([it]); }; return () => clearInterval(t); }, []);
  useEffect(() => { if (paused || !items.length) return; const t = setInterval(() => setI((x) => (x + 1) % items.length), 8000); return () => clearInterval(t); }, [paused, items.length]);
  const it = items[i % Math.max(1, items.length)];
  if (!it) return null;
  return (
    <div className="ticker" role="region" aria-label="faixa de notícias" aria-live={paused ? "off" : "polite"}>
      <button className="ibtn" onClick={() => setI((x) => (x - 1 + items.length) % items.length)} aria-label="anterior">‹</button>
      <button className="ibtn" onClick={() => setPaused(!paused)} aria-label={paused ? "retomar" : "pausar"}>{paused ? "▶" : "❚❚"}</button>
      <button className="ibtn" onClick={() => setI((x) => (x + 1) % items.length)} aria-label="próxima">›</button>
      {continuous && !reduce ? (
        <div className="tk-cont"><div className="tk-run">{items.map((x) => <span key={x.id}><b>{x.time_precision === "day" ? dt(x.published_at, "America/Sao_Paulo").slice(0, 8) : dt(x.published_at).slice(9)}</b> {x.outlet}: {x.headline} · </span>)}</div></div>
      ) : (
        <span className="tk-one" key={it.id} style={{ cursor: "pointer" }} onClick={() => set({ selectedNews: it.id } as any)}>
          <b className="mono">{it.time_precision === "day" ? dt(it.published_at, "America/Sao_Paulo").slice(0, 8) : dt(it.published_at).slice(9)}</b> <span className="dim">{it.outlet}</span> {it.headline}
        </span>
      )}
      <span className="dim" style={{ marginLeft: "auto", whiteSpace: "nowrap" }}>{(i % items.length) + 1}/{items.length}</span>
      <button className={"btn" + (continuous ? " pri" : "")} style={{ padding: "0 6px", fontSize: 10.5 }} onClick={() => setContinuous(!continuous)} title={reduce ? "movimento reduzido ativo: rolagem contínua desativada" : ""}>contínuo</button>
    </div>
  );
}

export function NewsEvidence({ id, onClose }: { id: string; onClose: () => void }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { setD(null); api(`/api/news/${id}`).then(setD); }, [id]);
  if (!d) return <div className="note">carregando…</div>;
  const n = d.item;
  return (
    <div>
      <div className="kvs">
        <span className="k">Manchete</span><span className="v"><b>{n.headline}</b></span>
        <span className="k">Tipo</span><span className="v">{KIND[n.kind]}{n.meta?.derived ? " (derivado de série oficial)" : ""}</span>
        <span className="k">Veículo / distrib.</span><span className="v">{n.outlet} · {n.distributor}</span>
        <span className="k">Publicado</span><span className="v">{n.time_precision === "day" ? `${dt(n.published_at, "America/Sao_Paulo").slice(0, 8)} — fonte informa só o dia` : `${dt(n.published_at, "America/New_York")} ET · ${dt(n.published_at, "America/Sao_Paulo")} BRT`}</span>
        <span className="k">Ingestão</span><span className="v">{dt(n.ingested_at)}</span>
        <span className="k">Idioma</span><span className="v">{n.lang.toUpperCase()} — tradução indisponível (sem serviço autorizado)</span>
        <span className="k">Status / versão</span><span className="v">{n.status} · v{n.version}</span>
        <span className="k">Licença</span><span className="v dim">{n.license}</span>
        <span className="k">Original</span><span className="v"><a href={n.url} target="_blank" rel="noopener noreferrer">abrir na fonte ↗</a></span>
      </div>
      {d.story.length > 1 && (<div className="kvs"><span className="k">História</span><span className="v">{d.story.map((s: any) => <div key={s.id} style={{ fontSize: 11 }}>{dt(s.published_at)} · {s.source} ({s.lang}) — {s.headline.slice(0, 80)}</div>)}
        <div className="dim" style={{ fontSize: 10.5 }}>Agrupado por emissor e data (heurística declarada); canais independentes do mesmo emissor.</div></span></div>)}
      {d.macro && <div className="callout">{d.macro.realized && <div>Realizado: {d.macro.realized}</div>}Consenso prévio: — · Anterior: —. {d.macro.note}</div>}
      <div style={{ padding: "0 10px 8px" }}>
        {d.reactions.map((r: any) => (
          <div key={r.ticker} style={{ marginBottom: 6 }}>
            <div className="mono">{r.ticker} <span className="dim">({r.relation === "direct" ? "vínculo direto" : r.relation === "macro" ? "relação macroeconômica" : "relação setorial"})</span></div>
            <div className="dim" style={{ fontSize: 11 }}>{r.rationale}</div>
            {r.tradable_session && <div style={{ fontSize: 11 }}>1ª sessão negociável: <b>{dt(r.tradable_session.session_date)}</b> ({r.tradable_session.status})</div>}
            {r.has_prices ? <button className="btn pri" style={{ marginTop: 3 }} onClick={() => { history.replaceState(null, "", "#"); run(`${r.ticker} ${r.exchange || ""} CHART 1D 3M`).then(() => history.replaceState(null, "", `${location.hash}&cell=${encodeURIComponent("candle:" + r.tradable_session.session_date)}`)); onClose(); }}>Ver reação no gráfico (vs {r.benchmark || "—"})</button>
              : <div className="dim" style={{ fontSize: 10.5 }}>sem série de preços autorizada para {r.ticker}</div>}
            <div className="dim" style={{ fontSize: 10.5 }}>{r.intraday_note}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
