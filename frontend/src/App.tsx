import { ReactNode, useEffect, useRef, useState } from "react";
import { api, clearCache, currentUser, USER_KEY } from "./api";
import AssetHeader from "./components/AssetHeader";
import CommandBar from "./components/CommandBar";
import ContextPanel from "./components/ContextPanel";
import { IBack, ICollapseL, ICollapseR, IMax, IMin, ISave, Logo } from "./components/Icons";
import Watchlist from "./components/Watchlist";
import { back, readUrl, run } from "./nav";
import { startQuotes } from "./quotes";
import { get, Layout, loadState, saveState, set, useStore } from "./store";
import Compare from "./views/Compare";
import Fin from "./views/Fin";
import { Filings, Find, Help, Macro, Markets, Watch } from "./views/Misc";
import Overview from "./views/Overview";
import { Dcf, Thesis } from "./views/Thesis";
import Chart from "./views/Chart";
import News, { NewsTicker } from "./views/News";
import Scan, { Events } from "./views/Scan";
import Value from "./views/Value";
import { Peers } from "./views/Overview";
import Layouts from "./components/Layouts";

function Main() {
  const route = useStore((s) => s.route);
  if (!route) return <div className="note">Digite um comando (Ctrl/⌘ K). Ex.: <span className="mono">PETR4 B3 FIN Q</span></div>;
  switch (route.fn) {
    case "FIN": return <Fin route={route} />;
    case "OVERVIEW": return <Overview route={route} />;
    case "HELP": return <Help route={route} />;
    case "MARKETS": return <Markets />;
    case "FIND": return <Find route={route} />;
    case "FILINGS": return <Filings route={route} />;
    case "COMPARE": return <Compare route={route} />;
    case "MACRO": return <Macro route={route} />;
    case "WATCH": return <Watch route={route} />;
    case "THESIS": return <Thesis route={route} />;
    case "DCF": return <Dcf route={route} />;
    case "CHART": return <Chart route={route} />;
    case "NEWS": return <News route={route} />;
    case "SCAN": return <Scan route={route} />;
    case "EVENTS": return <Events route={route} />;
    case "VALUE": return <Value route={route} />;
    case "PEERS": return <div className="view"><Peers route={route} /></div>;
    default: return <div className="note">Função {route.fn} sem tela.</div>;
  }
}

const TITLES = ["Watchlist · mercados", "Análise", "Notícias · eventos · fonte"];

function Panel({ i, size, children, title, layout, setLayout }: { i: number; size: number; children: ReactNode; title: ReactNode; layout: Layout; setLayout: (l: Layout) => void }) {
  const focus = useStore((s) => s.focusPanel);
  const mob = useStore((s) => s.mobileTab);
  const mobOn = (i === 0 && mob === "list") || (i === 1 && mob === "main") || (i === 2 && mob === "ctx");
  const isMobile = typeof window !== "undefined" && window.matchMedia("(max-width: 760px)").matches;
  if (layout.collapsed[i] && !isMobile) {
    return <div className="collapsed-rail"><button className="ibtn" title="expandir" onClick={() => setLayout({ ...layout, collapsed: layout.collapsed.map((c, j) => (j === i ? false : c)) as any })}>{i === 0 ? <ICollapseR /> : <ICollapseL />}</button><span className="lbl">{TITLES[i]}</span></div>;
  }
  const hidden = !isMobile && layout.maximized !== null && layout.maximized !== i;
  if (hidden) return null;
  return (
    <section className={"panel" + (focus === i ? " focused" : "") + (mobOn ? " mob-on" : "")} style={{ flex: layout.maximized === i ? "1 1 100%" : `${size} 1 0` }}
             onFocusCapture={() => get().focusPanel !== i && set({ focusPanel: i })} aria-label={TITLES[i]} data-panel={i}>
      <div className="ph">
        <span className="t">{title}</span>
        {i !== 1 && <button className="ibtn" title="recolher" onClick={() => setLayout({ ...layout, collapsed: layout.collapsed.map((c, j) => (j === i ? true : c)) as any })}>{i === 0 ? <ICollapseL /> : <ICollapseR />}</button>}
        <button className="ibtn" title={layout.maximized === i ? "restaurar" : "maximizar"} onClick={() => setLayout({ ...layout, maximized: layout.maximized === i ? null : i })}>{layout.maximized === i ? <IMin /> : <IMax />}</button>
      </div>
      <div className="pb" tabIndex={-1}>{children}</div>
    </section>
  );
}

function Splitter({ idx, layout, setLayout, desk }: { idx: number; layout: Layout; setLayout: (l: Layout) => void; desk: React.RefObject<HTMLDivElement> }) {
  const [drag, setDrag] = useState(false);
  const onDown = (e: React.PointerEvent) => {
    e.preventDefault(); setDrag(true);
    const W = desk.current!.clientWidth, x0 = e.clientX, s0 = [...layout.sizes] as [number, number, number];
    const move = (ev: PointerEvent) => {
      const d = ((ev.clientX - x0) / W) * 100;
      const s = [...s0] as [number, number, number];
      s[idx] = Math.max(10, s0[idx] + d); s[idx + 1] = Math.max(15, s0[idx + 1] - d);
      setLayout({ ...layout, sizes: s });
    };
    const up = () => { setDrag(false); window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };
  return <div className={"splitter" + (drag ? " drag" : "")} role="separator" aria-orientation="vertical" tabIndex={0} onPointerDown={onDown}
              onKeyDown={(e) => { const d = e.key === "ArrowLeft" ? -2 : e.key === "ArrowRight" ? 2 : 0; if (!d) return; const s = [...layout.sizes] as any; s[idx] += d; s[idx + 1] -= d; setLayout({ ...layout, sizes: s }); }} />;
}

export default function App() {
  const layout = useStore((s) => s.layout);
  const route = useStore((s) => s.route);
  const mob = useStore((s) => s.mobileTab);
  const contrast = useStore((s) => s.contrast);
  useEffect(() => { document.documentElement.dataset.contrast = contrast ? "high" : ""; }, [contrast]);
  const [me, setMe] = useState<any>(null);
  const [savedMsg, setSavedMsg] = useState("");
  const desk = useRef<HTMLDivElement>(null);
  const setLayout = (l: Layout) => set({ layout: l });

  useEffect(() => {
    startQuotes();
    api("/api/me").then(setMe);
    loadState<{ on: boolean }>("contrast").then((c) => c?.on && set({ contrast: true }));
    loadState<Layout>("layout").then((l) => {
      if (l) set({ layout: l });
      else if (window.innerWidth < 1280) set({ layout: { ...get().layout, collapsed: [false, false, true] } }); // notebook: lateral direita recolhida
    });
    // contexto: URL compartilhável > última sessão do usuário > monitor
    const u = readUrl();
    if (u.cmd) run(u.cmd, { push: false }).then(() => { if (u.cell) history.replaceState(null, "", location.hash.includes("cell=") ? location.hash : `${location.hash}&cell=${encodeURIComponent(u.cell)}`); });
    else loadState<{ cmd: string }>("session").then((s) => run(s?.cmd || "MARKETS BR US", { push: false }));
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && ["1", "2", "3"].includes(e.key)) {
        e.preventDefault();
        const i = Number(e.key) - 1;
        const p = document.querySelector<HTMLElement>(`[data-panel="${i}"] .grid, [data-panel="${i}"] [tabindex="0"], [data-panel="${i}"] .pb`);
        p?.focus(); set({ focusPanel: i });
      }
      if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); back(); }
      if ((e.key === "PageDown" || e.key === "PageUp") && !(e.target as HTMLElement).closest(".grid, input, textarea, .docv")) {
        const pb = document.querySelector<HTMLElement>(`[data-panel="${get().focusPanel}"] .pb`);
        if (pb) { e.preventDefault(); pb.scrollBy({ top: (e.key === "PageDown" ? 1 : -1) * pb.clientHeight * 0.9 }); }
      }
    };
    window.addEventListener("keydown", onKey);
    // link compartilhado colado/aberto com a aplicação já carregada
    const onHash = () => { const h = readUrl(); if (h.cmd && h.cmd !== get().route?.text) run(h.cmd).then(() => { if (h.cell) history.replaceState(null, "", `${location.hash}&cell=${encodeURIComponent(h.cell)}`); }); };
    window.addEventListener("hashchange", onHash);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("hashchange", onHash); };
  }, []);

  const sizes = layout.sizes;
  const vis = [0, 1, 2].filter((i) => !layout.collapsed[i] && (layout.maximized === null || layout.maximized === i));
  return (
    <div className="app" data-contrast={contrast ? "high" : undefined}>
      <header className="topbar">
        <div className="brand"><Logo /><span>MERIDIANO</span></div>
        <button className="ibtn" title="comando anterior (Alt ←)" onClick={back}><IBack /></button>
        <CommandBar />
        <span className="kbd">Ctrl/⌘ K</span>
        <span className="env" title="Ambiente de desenvolvimento: cotações de ações são simuladas">DEV · cotações SIMULADAS</span>
      </header>
      <AssetHeader />
      <div className="desk" ref={desk}>
        <Panel i={0} size={sizes[0]} layout={layout} setLayout={setLayout} title={TITLES[0]}><Watchlist /></Panel>
        {vis.includes(0) && vis.includes(1) && <Splitter idx={0} layout={layout} setLayout={setLayout} desk={desk} />}
        <Panel i={1} size={sizes[1]} layout={layout} setLayout={setLayout} title={<><b>{route?.fn || "—"}</b> {route?.text}</>}><Main /></Panel>
        {vis.includes(1) && vis.includes(2) && <Splitter idx={1} layout={layout} setLayout={setLayout} desk={desk} />}
        <Panel i={2} size={sizes[2]} layout={layout} setLayout={setLayout} title={TITLES[2]}><ContextPanel /></Panel>
      </div>
      <nav className="mobtabs" aria-label="Navegação móvel">
        {([["list", "Lista"], ["main", "Análise"], ["ctx", "Fonte/Contexto"]] as const).map(([k, l]) => <button key={k} className={mob === k ? "on" : ""} onClick={() => set({ mobileTab: k })}>{l}</button>)}
      </nav>
      <NewsTicker />
      <footer className="foot">
        <span>Usuário:</span>
        <select value={currentUser()} onChange={(e) => { try { localStorage.setItem(USER_KEY, e.target.value); } catch {} clearCache(); location.reload(); }} aria-label="usuário de desenvolvimento">
          {(me?.users || []).map((u: any) => <option key={u.id} value={u.id}>{u.name} ({u.role})</option>)}
        </select>
        <Layouts />
        <button className={"btn" + (contrast ? " pri" : "")} style={{ padding: "0 8px" }} onClick={() => { const c = !contrast; set({ contrast: c }); saveState("contrast", { on: c }); }} aria-pressed={contrast}>alto contraste</button>
        <button className="btn" style={{ padding: "0 8px" }} onClick={() => setLayout({ sizes: [20, 56, 24], collapsed: [false, false, false], maximized: null })}>20/56/24</button>
        <span className="up">{savedMsg}</span>
        <span style={{ flex: 1 }} />
        <span>Dados: SEC EDGAR · CVM · BCB · FRED (snapshot/ao vivo conforme ingestão) · ações SIM</span>
        <span><span className="kbd">Alt 1/2/3</span> painéis · <span className="kbd">Alt ←</span> voltar · <span className="kbd">HELP</span></span>
      </footer>
    </div>
  );
}
