// Gráfico próprio em canvas: painéis múltiplos, cursor cruzado, zoom no cursor, arraste, seleção de intervalo,
// escala log, eventos clicáveis e desenhos editáveis (tendência, horizontal, canal, retângulo, Fibonacci, medição, nota).
import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from "react";

export type Bar = { t: string; o: number; h: number; l: number; c: number; v: number | null; vwap?: number | null };
export type StudyOut = { series?: Record<string, (number | null)[]>; levels?: number[]; error?: string; bins?: { from: number; to: number; volume: number }[] };
export type StudyDef = { key: string; id: string; params: any; pane: "price" | "volume" | "own"; color: string; label: string };
export type Evt = { id: string; type: string; headline: string; published_at: string; precision: string; tradable_session: { session_date: string; status: string }; source: string; url?: string };
export type Pt = { t: string; p: number };
export type Drawing = { id?: string; kind: string; points: Pt[]; text?: string; locked?: boolean; hidden?: boolean; style?: any };
export type View = { from: number; to: number };
export type ChartHandle = { back: () => void; reset: () => void; zoom: (f: number) => void; focus: () => void };

const AXIS_W = 66, TIME_H = 22, GAP = 6;
const C = { up: "#3ecf8e", down: "#ff6b6b", grid: "rgba(255,255,255,.05)", text: "#8fa3b8", cross: "rgba(232,176,74,.7)", sel: "rgba(232,176,74,.12)" };
const EVT: Record<string, [string, string]> = { earnings: ["R", "#e8b04a"], filing: ["D", "#8ab4ff"], dividend: ["$", "#3ecf8e"], dividends: ["$", "#3ecf8e"],
  split: ["S", "#c08bff"], news: ["N", "#d5dee8"], macro: ["M", "#46d3c3"], cash_dividend: ["$", "#3ecf8e"] };
export const evtGlyph = (t: string) => EVT[t] || ["•", "#d5dee8"];
const FIB = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

type Props = {
  bars: Bar[]; studies: Record<string, StudyOut>; defs: StudyDef[]; events: Evt[]; drawings: Drawing[];
  type: "candle" | "ohlc" | "line" | "area"; log: boolean; view: View; cursor: number | null; tool: string | null; selected: number | null;
  showEvents: boolean; contrast?: boolean;
  onView: (v: View, push?: boolean) => void; onCursor: (i: number | null) => void; onEvent: (e: Evt) => void;
  onDrawings: (d: Drawing[]) => void; onSelect: (i: number | null) => void; onToolDone: () => void; onLogInvalid: (msg: string) => void;
};

export default forwardRef<ChartHandle, Props>(function ChartCanvas(p, ref) {
  const wrap = useRef<HTMLDivElement>(null);
  const cv = useRef<HTMLCanvasElement>(null);
  const [size, setSize] = useState({ w: 800, h: 500 });
  const hist = useRef<View[]>([]);
  const drag = useRef<any>(null);
  const pending = useRef<Pt[]>([]);
  const [hover, setHover] = useState<{ x: number; y: number } | null>(null);
  const markers = useRef<{ x: number; y: number; e: Evt }[]>([]);

  useImperativeHandle(ref, () => ({
    back: () => { const v = hist.current.pop(); if (v) p.onView(v, false); },
    reset: () => { hist.current.push(p.view); p.onView({ from: Math.max(0, p.bars.length - 504), to: p.bars.length }, false); },
    zoom: (f: number) => zoomAt(f, (p.cursor ?? (p.view.from + p.view.to) / 2)),
    focus: () => wrap.current?.focus(),
  }));

  useLayoutEffect(() => {
    const ro = new ResizeObserver(() => { const r = wrap.current!.getBoundingClientRect(); setSize({ w: Math.max(200, r.width), h: Math.max(200, r.height) }); });
    ro.observe(wrap.current!);
    return () => ro.disconnect();
  }, []);

  // painéis
  const ownDefs = p.defs.filter((d) => d.pane === "own");
  const panes = useMemo(() => {
    const H = size.h - TIME_H;
    const units = 3 + 0.8 + ownDefs.length * 0.9;
    const u = (H - GAP * (1 + ownDefs.length)) / units;
    const out: { key: string; y: number; h: number }[] = [];
    let y = 0;
    out.push({ key: "price", y, h: 3 * u }); y += 3 * u + GAP;
    out.push({ key: "volume", y, h: 0.8 * u }); y += 0.8 * u + GAP;
    for (const d of ownDefs) { out.push({ key: d.key, y, h: 0.9 * u }); y += 0.9 * u + GAP; }
    return out;
  }, [size.h, ownDefs.map((d) => d.key).join()]);

  const plotW = size.w - AXIS_W;
  const n = p.bars.length;
  const span = Math.max(5, p.view.to - p.view.from);
  const bw = plotW / span;
  const xOf = (i: number) => (i - p.view.from + 0.5) * bw;
  const iOf = (x: number) => Math.floor(x / bw + p.view.from);
  const idx = useMemo(() => { const m = new Map<string, number>(); p.bars.forEach((b, i) => m.set(b.t, i)); return m; }, [p.bars]);
  const tIndex = (t: string) => { if (idx.has(t)) return idx.get(t)!; let lo = 0; for (let i = 0; i < n; i++) if (p.bars[i].t <= t) lo = i; return t > p.bars[n - 1]?.t ? n - 1 + daysAfter(p.bars[n - 1].t, t) : lo; };

  // escala de preço (visível + sobreposições)
  const vis = useMemo(() => {
    const a = Math.max(0, Math.floor(p.view.from)), b = Math.min(n, Math.ceil(p.view.to));
    let lo = Infinity, hi = -Infinity, vmax = 0;
    for (let i = a; i < b; i++) { const x = p.bars[i]; lo = Math.min(lo, x.l); hi = Math.max(hi, x.h); vmax = Math.max(vmax, x.v || 0); }
    for (const d of p.defs.filter((d) => d.pane === "price")) for (const s of Object.values(p.studies[d.key]?.series || {})) for (let i = a; i < b; i++) { const v = s[i]; if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
    if (!isFinite(lo)) { lo = 0; hi = 1; }
    const pad = (hi - lo) * 0.06 || 1;
    return { a, b, lo: lo - pad, hi: hi + pad, vmax };
  }, [p.bars, p.view, p.studies, p.defs]);
  const logOk = vis.lo > 0;
  useEffect(() => { if (p.log && !logOk) p.onLogInvalid("Escala logarítmica exige preços positivos na janela — mantida linear."); }, [p.log, logOk]);
  const useLog = p.log && logOk;
  const pp = panes[0];
  const yOf = (price: number) => {
    const f = useLog ? (Math.log(price) - Math.log(vis.lo)) / (Math.log(vis.hi) - Math.log(vis.lo)) : (price - vis.lo) / (vis.hi - vis.lo);
    return pp.y + pp.h - f * pp.h;
  };
  const pOf = (y: number) => {
    const f = (pp.y + pp.h - y) / pp.h;
    return useLog ? Math.exp(Math.log(vis.lo) + f * (Math.log(vis.hi) - Math.log(vis.lo))) : vis.lo + f * (vis.hi - vis.lo);
  };

  // ---------- desenho ----------
  useEffect(() => {
    const c = cv.current!; const dpr = window.devicePixelRatio || 1;
    c.width = size.w * dpr; c.height = size.h * dpr; c.style.width = size.w + "px"; c.style.height = size.h + "px";
    const g = c.getContext("2d")!; g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, size.w, size.h);
    g.font = "10.5px ui-monospace, Menlo, monospace"; g.textBaseline = "middle";
    const up = p.contrast ? "#00ff9c" : C.up, dn = p.contrast ? "#ff4040" : C.down;
    // grade + eixo de preço
    const ticks = niceTicks(vis.lo, vis.hi, Math.max(3, Math.floor(pp.h / 48)));
    g.strokeStyle = C.grid; g.fillStyle = C.text; g.lineWidth = 1;
    for (const t of ticks) { const y = Math.round(yOf(t)) + .5; if (y < pp.y || y > pp.y + pp.h) continue; g.beginPath(); g.moveTo(0, y); g.lineTo(plotW, y); g.stroke(); g.fillText(fmtP(t), plotW + 6, y); }
    // eixo de tempo
    const step = Math.max(1, Math.ceil(70 / bw));
    g.fillStyle = C.text;
    for (let i = Math.ceil(vis.a / step) * step; i < vis.b; i += step) {
      const x = xOf(i); g.strokeStyle = C.grid; g.beginPath(); g.moveTo(Math.round(x) + .5, 0); g.lineTo(Math.round(x) + .5, size.h - TIME_H); g.stroke();
      g.fillText(fmtT(p.bars[i].t), x - 26, size.h - TIME_H / 2);
    }
    g.save(); g.beginPath(); g.rect(0, pp.y, plotW, pp.h); g.clip();
    // preço
    if (p.type === "line" || p.type === "area") {
      g.beginPath(); let first = true;
      for (let i = vis.a; i < vis.b; i++) { const x = xOf(i), y = yOf(p.bars[i].c); first ? g.moveTo(x, y) : g.lineTo(x, y); first = false; }
      g.strokeStyle = "#e8b04a"; g.lineWidth = 1.6; g.stroke();
      if (p.type === "area") { g.lineTo(xOf(vis.b - 1), pp.y + pp.h); g.lineTo(xOf(vis.a), pp.y + pp.h); g.closePath(); g.fillStyle = "rgba(232,176,74,.12)"; g.fill(); }
    } else {
      for (let i = vis.a; i < vis.b; i++) {
        const b = p.bars[i], x = xOf(i), isUp = b.c >= b.o, col = isUp ? up : dn;
        g.strokeStyle = col; g.fillStyle = col; g.lineWidth = 1;
        const w = Math.max(1, bw * 0.7);
        if (p.type === "candle") {
          g.beginPath(); g.moveTo(Math.round(x) + .5, yOf(b.h)); g.lineTo(Math.round(x) + .5, yOf(b.l)); g.stroke();
          const y1 = yOf(Math.max(b.o, b.c)), y2 = yOf(Math.min(b.o, b.c));
          if (isUp && bw > 3) g.strokeRect(x - w / 2, y1, w, Math.max(1, y2 - y1)); else g.fillRect(x - w / 2, y1, w, Math.max(1, y2 - y1));
        } else {
          g.beginPath(); g.moveTo(x, yOf(b.h)); g.lineTo(x, yOf(b.l)); g.moveTo(x - w / 2, yOf(b.o)); g.lineTo(x, yOf(b.o)); g.moveTo(x, yOf(b.c)); g.lineTo(x + w / 2, yOf(b.c)); g.stroke();
        }
      }
    }
    // sobreposições no preço
    for (const d of p.defs.filter((d) => d.pane === "price")) {
      const out = p.studies[d.key];
      if (out?.bins) { // perfil de volume aproximado
        const vm = Math.max(...out.bins.map((b) => b.volume)) || 1;
        g.fillStyle = "rgba(138,180,255,.18)";
        for (const b of out.bins) { const y1 = yOf(b.to), y2 = yOf(b.from); g.fillRect(plotW - (b.volume / vm) * plotW * 0.22, y1, (b.volume / vm) * plotW * 0.22, Math.max(1, y2 - y1 - 1)); }
        continue;
      }
      Object.entries(out?.series || {}).forEach(([k, s], j) => line(g, s, vis.a, vis.b, xOf, yOf, d.id === "bb" && k !== "mid" ? fade(d.color) : d.color, d.id === "avwap" ? [4, 3] : []));
    }
    // eventos
    markers.current = [];
    if (p.showEvents) {
      const stack: Record<number, number> = {};
      for (const e of p.events) {
        const i = idx.get(e.tradable_session?.session_date);
        if (i === undefined || i < vis.a || i >= vis.b) continue;
        const k = stack[i] = (stack[i] || 0) + 1;
        const x = xOf(i), y = Math.min(pp.y + pp.h - 9, yOf(p.bars[i].l) + 10 + (k - 1) * 14);
        const [ch, col] = evtGlyph(e.type);
        g.fillStyle = "rgba(10,14,19,.9)"; g.strokeStyle = col; g.lineWidth = 1.2;
        g.beginPath(); g.arc(x, y, 6, 0, Math.PI * 2); g.fill(); g.stroke();
        g.fillStyle = col; g.font = "bold 8.5px system-ui"; g.fillText(ch, x - 2.8, y + .5); g.font = "10.5px ui-monospace, Menlo, monospace";
        markers.current.push({ x, y, e });
      }
      // gancho de teste/acessibilidade: posições dos marcadores em coordenadas da janela
      const r = c.getBoundingClientRect();
      (window as any).__meridianoMarkers = markers.current.map((m) => ({ x: r.left + m.x, y: r.top + m.y, id: m.e.id, type: m.e.type, headline: m.e.headline, session: m.e.tradable_session?.session_date }));
    }
    // desenhos
    const all = [...p.drawings.map((d, i) => ({ d, i })), ...(pending.current.length && p.tool ? [{ d: { kind: p.tool, points: [...pending.current, ...(hover ? [{ t: tOfIndex(iOf(hover.x)), p: pOf(hover.y) }] : [])] }, i: -1 }] : [])];
    for (const { d, i } of all) { if (!d.hidden) drawShape(g, d as Drawing, i === p.selected, tIndex, xOf, yOf, plotW); }
    g.restore();
    // volume
    const vp = panes[1];
    g.fillStyle = C.text; g.fillText("Vol", 4, vp.y + 8);
    for (let i = vis.a; i < vis.b; i++) {
      const b = p.bars[i]; if (!b.v) continue;
      const hh = (b.v / (vis.vmax || 1)) * (vp.h - 4);
      g.fillStyle = b.c >= b.o ? "rgba(62,207,142,.35)" : "rgba(255,107,107,.35)";
      g.fillRect(xOf(i) - Math.max(1, bw * 0.35), vp.y + vp.h - hh, Math.max(1, bw * 0.7), hh);
    }
    for (const d of p.defs.filter((d) => d.pane === "volume")) for (const s of Object.values(p.studies[d.key]?.series || {})) line(g, s, vis.a, vis.b, xOf, (v) => vp.y + vp.h - (v / (vis.vmax || 1)) * (vp.h - 4), d.color, []);
    // painéis de estudo
    for (const d of ownDefs) {
      const pa = panes.find((x) => x.key === d.key)!; const out = p.studies[d.key];
      g.strokeStyle = "rgba(255,255,255,.08)"; g.strokeRect(0.5, pa.y + .5, plotW - 1, pa.h - 1);
      g.fillStyle = C.text; g.fillText(d.label + (out?.error ? " — " + out.error : ""), 4, pa.y + 8);
      const ss = Object.entries(out?.series || {});
      let lo = Infinity, hi = -Infinity;
      for (const [, s] of ss) for (let i = vis.a; i < vis.b; i++) { const v = s[i]; if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
      for (const L of out?.levels || []) { lo = Math.min(lo, L); hi = Math.max(hi, L); }
      if (!isFinite(lo)) continue;
      const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
      const yy = (v: number) => pa.y + pa.h - ((v - lo) / (hi - lo)) * pa.h;
      g.setLineDash([3, 3]); g.strokeStyle = "rgba(255,255,255,.18)";
      for (const L of out?.levels || []) { g.beginPath(); g.moveTo(0, yy(L)); g.lineTo(plotW, yy(L)); g.stroke(); g.fillStyle = C.text; g.fillText(String(L), plotW + 6, yy(L)); }
      g.setLineDash([]);
      g.fillStyle = C.text; g.fillText(fmtP(hi - pad), plotW + 6, pa.y + 8); g.fillText(fmtP(lo + pad), plotW + 6, pa.y + pa.h - 8);
      const palette = [d.color, "#8ab4ff", "#ff9b9b", "#c08bff"];
      ss.forEach(([k, s], j) => {
        if (k === "hist") { for (let i = vis.a; i < vis.b; i++) { const v = s[i]; if (v == null) continue; g.fillStyle = v >= 0 ? "rgba(62,207,142,.5)" : "rgba(255,107,107,.5)"; g.fillRect(xOf(i) - bw * .35, Math.min(yy(0), yy(v)), Math.max(1, bw * .7), Math.abs(yy(v) - yy(0))); } }
        else line(g, s, vis.a, vis.b, xOf, yy, palette[j % palette.length], []);
      });
    }
    // cursor cruzado
    const ci = p.cursor;
    if (ci != null && ci >= vis.a && ci < vis.b) {
      const x = Math.round(xOf(ci)) + .5;
      g.strokeStyle = C.cross; g.setLineDash([4, 3]); g.beginPath(); g.moveTo(x, 0); g.lineTo(x, size.h - TIME_H); g.stroke();
      if (hover && hover.y < pp.y + pp.h) { g.beginPath(); g.moveTo(0, hover.y); g.lineTo(plotW, hover.y); g.stroke(); g.setLineDash([]); g.fillStyle = "#e8b04a"; g.fillRect(plotW, hover.y - 8, AXIS_W, 16); g.fillStyle = "#0a0e13"; g.fillText(fmtP(pOf(hover.y)), plotW + 4, hover.y); }
      g.setLineDash([]); g.fillStyle = "#e8b04a"; g.fillRect(x - 34, size.h - TIME_H + 2, 68, TIME_H - 4); g.fillStyle = "#0a0e13"; g.fillText(fmtT(p.bars[ci].t, true), x - 31, size.h - TIME_H / 2);
    }
    // seleção de intervalo
    if (drag.current?.mode === "select") { const a = drag.current.x0, b = drag.current.x1; g.fillStyle = C.sel; g.fillRect(Math.min(a, b), 0, Math.abs(b - a), size.h - TIME_H); }
  });

  function tOfIndex(i: number) { return p.bars[Math.max(0, Math.min(n - 1, i))]?.t; }

  const zoomAt = (f: number, center: number) => {
    const s0 = p.view.to - p.view.from, s1 = Math.max(10, Math.min(n + 20, s0 * f));
    const r = (center - p.view.from) / s0;
    let from = center - r * s1; let to = from + s1;
    if (to > n + 10) { to = n + 10; from = to - s1; } if (from < -10) { from = -10; to = from + s1; }
    p.onView({ from, to });
  };

  const hitDrawing = (x: number, y: number): number | null => {
    for (let i = p.drawings.length - 1; i >= 0; i--) {
      const d = p.drawings[i]; if (d.hidden) continue;
      const pts = d.points.map((q) => ({ x: xOf(tIndex(q.t)), y: yOf(q.p) }));
      if (d.kind === "hline" && Math.abs(y - pts[0].y) < 5) return i;
      if (pts.some((q) => Math.hypot(q.x - x, q.y - y) < 8)) return i;
      if (pts.length >= 2 && distSeg(x, y, pts[0], pts[1]) < 5) return i;
    }
    return null;
  };

  return (
    <div ref={wrap} tabIndex={0} style={{ position: "relative", width: "100%", height: "100%", outline: "none", cursor: p.tool ? "crosshair" : drag.current ? "grabbing" : "default" }}
         aria-label="Gráfico de preços: setas movem o cursor, + e − zoom, Backspace volta à visão anterior"
         onWheel={(e) => { e.preventDefault(); const r = cv.current!.getBoundingClientRect(); zoomAt(e.deltaY > 0 ? 1.12 : 0.89, e.clientX - r.left < plotW ? (e.clientX - r.left) / bw + p.view.from : p.view.to); }}
         onMouseDown={(e) => {
           const r = cv.current!.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
           if (p.tool) {
             pending.current.push({ t: tOfIndex(iOf(x)), p: pOf(y) });
             const need = ({ hline: 1, note: 1, channel: 3 } as any)[p.tool] || 2;
             if (pending.current.length >= need) {
               const d: Drawing = { kind: p.tool, points: pending.current.slice(0, need), text: p.tool === "note" ? (prompt("Texto da anotação:") || "nota") : undefined };
               pending.current = []; p.onDrawings([...p.drawings, d]); p.onSelect(p.drawings.length); p.onToolDone();
             }
             return;
           }
           const mk = markers.current.find((m) => Math.hypot(m.x - x, m.y - y) < 8);
           if (mk) { p.onEvent(mk.e); return; }
           const hd = hitDrawing(x, y);
           if (hd !== null) {
             p.onSelect(hd);
             const d = p.drawings[hd];
             if (!d.locked) { const pi = d.points.findIndex((q) => Math.hypot(xOf(tIndex(q.t)) - x, yOf(q.p) - y) < 8); drag.current = { mode: "edit", d: hd, pi, x0: x, y0: y, orig: d.points }; }
             return;
           }
           p.onSelect(null);
           drag.current = e.shiftKey ? { mode: "select", x0: x, x1: x } : { mode: "pan", x0: x, v0: p.view };
         }}
         onMouseMove={(e) => {
           const r = cv.current!.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top;
           setHover({ x, y });
           const i = iOf(x); if (i >= 0 && i < n && x < plotW) p.onCursor(i);
           const dr = drag.current; if (!dr) return;
           if (dr.mode === "pan") { const dx = (x - dr.x0) / bw; p.onView({ from: dr.v0.from - dx, to: dr.v0.to - dx }); }
           if (dr.mode === "select") { dr.x1 = x; setHover({ x, y }); }
           if (dr.mode === "edit") {
             const d = p.drawings[dr.d];
             const pts = dr.pi >= 0 ? dr.orig.map((q: Pt, k: number) => (k === dr.pi ? { t: tOfIndex(i), p: pOf(y) } : q))
               : dr.orig.map((q: Pt) => ({ t: tOfIndex(tIndex(q.t) + Math.round((x - dr.x0) / bw)), p: pOf(yOf(q.p) + (y - dr.y0)) }));
             p.onDrawings(p.drawings.map((x2, k) => (k === dr.d ? { ...d, points: pts } : x2)));
           }
         }}
         onMouseUp={() => {
           const dr = drag.current; drag.current = null;
           if (dr?.mode === "select" && Math.abs(dr.x1 - dr.x0) > 8) { hist.current.push(p.view); const a = iOf(Math.min(dr.x0, dr.x1)), b = iOf(Math.max(dr.x0, dr.x1)) + 1; p.onView({ from: a, to: b }); }
           else if (dr?.mode === "pan" && dr.v0.from !== p.view.from) hist.current.push(dr.v0);
         }}
         onMouseLeave={() => { setHover(null); drag.current = null; }}
         onDoubleClick={() => { hist.current.push(p.view); p.onView({ from: Math.max(0, n - Math.round(p.view.to - p.view.from)), to: n }); }}
         onKeyDown={(e) => {
           const c = p.cursor ?? n - 1;
           if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
             e.preventDefault(); const ni = Math.max(0, Math.min(n - 1, c + (e.key === "ArrowLeft" ? -1 : 1))); p.onCursor(ni);
             if (ni < p.view.from) p.onView({ from: ni, to: ni + span }); if (ni >= p.view.to) p.onView({ from: ni - span + 1, to: ni + 1 });
           }
           if (e.key === "+" || e.key === "=") zoomAt(0.85, c);
           if (e.key === "-") zoomAt(1.18, c);
           if (e.key === "Backspace") { e.preventDefault(); const v = hist.current.pop(); if (v) p.onView(v, false); }
           if ((e.key === "Delete") && p.selected != null && !p.drawings[p.selected]?.locked) { p.onDrawings(p.drawings.filter((_, k) => k !== p.selected)); p.onSelect(null); }
           if (e.key === "Escape" && p.tool) { pending.current = []; p.onToolDone(); }
         }}>
      <canvas ref={cv} />
    </div>
  );
});

function line(g: CanvasRenderingContext2D, s: (number | null)[], a: number, b: number, xOf: (i: number) => number, yOf: (v: number) => number, color: string, dash: number[]) {
  g.strokeStyle = color; g.lineWidth = 1.3; g.setLineDash(dash); g.beginPath();
  let pen = false;
  for (let i = a; i < b; i++) { const v = s[i]; if (v == null) { pen = false; continue; } const x = xOf(i), y = yOf(v); pen ? g.lineTo(x, y) : g.moveTo(x, y); pen = true; }
  g.stroke(); g.setLineDash([]);
}
const fade = (c: string) => c + "99";

function drawShape(g: CanvasRenderingContext2D, d: Drawing, sel: boolean, tIndex: (t: string) => number, xOf: (i: number) => number, yOf: (p: number) => number, W: number) {
  const pts = d.points.map((q) => ({ x: xOf(tIndex(q.t)), y: yOf(q.p), p: q.p }));
  g.strokeStyle = sel ? "#ffd27a" : d.style?.color || "#e8b04a"; g.fillStyle = g.strokeStyle; g.lineWidth = sel ? 2 : 1.3;
  const seg = (a: any, b: any) => { g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke(); };
  if (d.kind === "hline") { g.setLineDash([6, 3]); g.beginPath(); g.moveTo(0, pts[0].y); g.lineTo(W, pts[0].y); g.stroke(); g.setLineDash([]); g.fillText(fmtP(pts[0].p), 4, pts[0].y - 7); }
  if (d.kind === "trend" && pts.length > 1) seg(pts[0], pts[1]);
  if (d.kind === "channel" && pts.length > 1) { seg(pts[0], pts[1]); if (pts[2]) { const dy = pts[2].y - (pts[0].y + (pts[1].y - pts[0].y) * ((pts[2].x - pts[0].x) / ((pts[1].x - pts[0].x) || 1))); seg({ x: pts[0].x, y: pts[0].y + dy }, { x: pts[1].x, y: pts[1].y + dy }); } }
  if (d.kind === "rect" && pts.length > 1) { g.globalAlpha = .12; g.fillRect(pts[0].x, pts[0].y, pts[1].x - pts[0].x, pts[1].y - pts[0].y); g.globalAlpha = 1; g.strokeRect(pts[0].x, pts[0].y, pts[1].x - pts[0].x, pts[1].y - pts[0].y); }
  if (d.kind === "fib" && pts.length > 1) {
    for (const f of FIB) { const pr = pts[1].p + (pts[0].p - pts[1].p) * f, y = yOf(pr); g.globalAlpha = .7; g.beginPath(); g.moveTo(Math.min(pts[0].x, pts[1].x), y); g.lineTo(W, y); g.stroke(); g.globalAlpha = 1; g.fillText(`${(f * 100).toFixed(1)}%  ${fmtP(pr)}`, Math.min(pts[0].x, pts[1].x) + 2, y - 6); }
  }
  if (d.kind === "measure" && pts.length > 1) { seg(pts[0], pts[1]); const ch = (pts[1].p / pts[0].p - 1) * 100; const bars = Math.round(Math.abs(pts[1].x - pts[0].x) / ((xOf(1) - xOf(0)) || 1)); g.fillText(`${ch >= 0 ? "+" : "−"}${Math.abs(ch).toFixed(2)}% · ${bars} barras`, pts[1].x + 6, pts[1].y); }
  if (d.kind === "note") { g.fillText("✎ " + (d.text || ""), pts[0].x + 4, pts[0].y); }
  if (sel) for (const q of pts) { g.fillRect(q.x - 3, q.y - 3, 6, 6); }
  if (d.locked) g.fillText("🔒", pts[0].x - 14, pts[0].y);
}

function distSeg(px: number, py: number, a: { x: number; y: number }, b: { x: number; y: number }) {
  const dx = b.x - a.x, dy = b.y - a.y; const t = Math.max(0, Math.min(1, ((px - a.x) * dx + (py - a.y) * dy) / ((dx * dx + dy * dy) || 1)));
  return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
}
function daysAfter(a: string, b: string) { return Math.round((new Date(b).getTime() - new Date(a).getTime()) / 86400000 * 5 / 7); }
function niceTicks(lo: number, hi: number, n: number) {
  const raw = (hi - lo) / n; const mag = Math.pow(10, Math.floor(Math.log10(raw))); const st = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
  const out = []; for (let v = Math.ceil(lo / st) * st; v <= hi; v += st) out.push(v); return out;
}
export function fmtP(v: number) { const a = Math.abs(v); return v.toLocaleString("pt-BR", { maximumFractionDigits: a >= 1000 ? 0 : a >= 10 ? 2 : 3, minimumFractionDigits: a >= 1000 ? 0 : 2 }); }
function fmtT(t: string, full = false) { if (t.length > 10) { const d = new Date(t); return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); } const [y, m, d] = t.split("-"); return full ? `${d}/${m}/${y.slice(2)}` : `${d}/${m}/${y.slice(2)}`; }
