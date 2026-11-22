// Execução de comandos, histórico e URL compartilhável (sem dados privados: só comando e posição).
import { api, post } from "./api";
import { get, Route, saveState, set } from "./store";

export function canonical(r: any): string {
  const inst = r.ticker ? `${r.ticker}${r.exchange ? " " + r.exchange : ""}` : "";
  switch (r.fn) {
    case "FIN": return `${inst} FIN ${r.args?.freq || "A"} ${r.args?.statement || "IS"}`;
    case "OVERVIEW": case "FILINGS": case "DCF": case "VALUE": case "PEERS": case "EVENTS": return `${inst} ${r.fn}`;
    case "CHART": return `${inst} CHART ${r.args?.interval === "5m" ? "5MIN" : r.args?.interval === "1m" ? "1MIN" : r.args?.interval || "1D"} ${r.args?.window || "2Y"}`;
    case "NEWS": return r.args?.tab === "ticker" ? `NEWS ${r.ticker}:${r.exchange}` : `NEWS ${({ top: "WORLD", live: "LIVE", br: "BR", us: "US", asia: "ASIA", eu: "EU", bridge: "BRIDGE", watchlist: "WATCH", portfolio: "PORTFOLIO" } as any)[r.args?.tab] || "WORLD"}`;
    case "SCAN": return `SCAN ${r.args?.market || "BR"}${r.args?.name ? " " + r.args.name : ""}`;
    case "THESIS": return `THESIS ${r.ticker}:${r.exchange}`;
    case "MARKETS": return `MARKETS ${(r.args?.regions || ["BR", "US"]).join(" ")}`;
    case "FIND": return `FIND ${r.args?.q || ""}`;
    case "HELP": return `HELP ${r.args?.q || ""}`.trim();
    case "MACRO": return `MACRO ${String(r.args?.code || "").replace(".", " ")}`;
    case "WATCH": return `WATCH ${r.args?.name}`;
    case "COMPARE": return `COMPARE ${(r.args?.instruments || []).map((i: any) => `${i.ticker}:${i.exchange}`).join(" ")}${r.args?.ccy && r.args.ccy !== "NATIVE" ? " CCY=" + r.args.ccy : ""}`;
    default: return r.text || "";
  }
}

export function writeUrl(route: Route, extra: Record<string, string | undefined> = {}) {
  const p = new URLSearchParams({ cmd: route.text });
  for (const [k, v] of Object.entries(extra)) if (v) p.set(k, v);
  const h = "#" + p.toString();
  if (location.hash !== h) history.replaceState(null, "", h);
}
export function readUrl(): { cmd?: string; cell?: string; doc?: string } {
  const p = new URLSearchParams(location.hash.slice(1));
  return { cmd: p.get("cmd") || undefined, cell: p.get("cell") || undefined, doc: p.get("doc") || undefined };
}

export async function run(text: string, opts: { push?: boolean } = {}): Promise<boolean> {
  const res = await post("/api/command/parse", { text });
  if (!res.ok) { set({ error: { ...res, input: text } }); return false; }
  const route: Route = { ...res, text: "" };
  route.text = canonical(route);
  const prev = get().route;
  set((s) => ({
    route, error: null, doc: null,
    history: opts.push === false || !prev ? s.history : [...s.history.slice(-49), prev],
    linkA: route.instrument_id ? { instrument_id: route.instrument_id, ticker: route.ticker, exchange: route.exchange } : s.linkA,
    mobileTab: "main",
  }));
  writeUrl(route);
  saveState("session", { cmd: route.text });
  return true;
}

export function back() {
  const h = get().history;
  if (!h.length) return;
  const prev = h[h.length - 1];
  set({ route: prev, history: h.slice(0, -1), doc: null, error: null });
  writeUrl(prev);
}

export async function preloadIndex() {
  return api("/api/search/index", { cacheMs: 600000 });
}

// ganchos de medição (critério H) — sem efeito na interface
(window as any).__meridianoRun = run;
