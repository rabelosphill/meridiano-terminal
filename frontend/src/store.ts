// Estado global mínimo (useSyncExternalStore) + persistência por usuário/workspace/painel/instrumento/função.
import { useSyncExternalStore } from "react";
import { api, put } from "./api";

export type Route = {
  fn: string;                    // HELP, MARKETS, FIND, OVERVIEW, FIN, FILINGS, COMPARE, MACRO, WATCH, THESIS, DCF
  text: string;                  // comando canônico
  instrument_id?: string; listing_id?: string; issuer_id?: string; ticker?: string; exchange?: string; kind?: string;
  args?: any; notice?: string;
};
export type CellRef = { row: number; col: number; concept?: string; period?: string };
export type Layout = { sizes: [number, number, number]; collapsed: [boolean, boolean, boolean]; maximized: number | null };

export type State = {
  route: Route | null;
  history: Route[];
  selectedFact: number | null;     // célula inspecionada (painel de contexto)
  selectedEvent: any | null;       // evento clicado no gráfico
  selectedNews: string | null;     // notícia aberta (evidência)
  contrast: boolean;
  selectedCell: any | null;
  doc: { factId: number; returnTo: CellRef; title: string } | null;
  layout: Layout;
  linkA: { instrument_id?: string; ticker?: string; exchange?: string } | null;
  error: any | null;
  focusPanel: number;
  mobileTab: "list" | "main" | "ctx";
};

const DEFAULT_LAYOUT: Layout = { sizes: [20, 56, 24], collapsed: [false, false, false], maximized: null };

let state: State = {
  route: null, history: [], selectedFact: null, selectedEvent: null, selectedNews: null, contrast: false, selectedCell: null, doc: null, layout: DEFAULT_LAYOUT,
  linkA: null, error: null, focusPanel: 1, mobileTab: "main",
};
const subs = new Set<() => void>();
export function get() { return state; }
export function set(patch: Partial<State> | ((s: State) => Partial<State>)) {
  const p = typeof patch === "function" ? patch(state) : patch;
  state = { ...state, ...p };
  subs.forEach((f) => f());
}
export function useStore<T>(sel: (s: State) => T): T {
  return useSyncExternalStore((cb) => { subs.add(cb); return () => subs.delete(cb); }, () => sel(state));
}

export const WORKSPACE = "default";
const timers: Record<string, any> = {};
export function saveState(key: string, value: any, delay = 400) {
  try { localStorage.setItem(`meridiano.${WORKSPACE}.${key}`, JSON.stringify(value)); } catch { /* armazenamento indisponível */ }
  clearTimeout(timers[key]);
  timers[key] = setTimeout(() => { put(`/api/state/${WORKSPACE}/${encodeURIComponent(key)}`, value).catch(() => {}); }, delay);
}
export async function loadState<T>(key: string): Promise<T | null> {
  try {
    const r = await api<{ state: T | null }>(`/api/state/${WORKSPACE}/${encodeURIComponent(key)}`);
    if (r.state) return r.state;
  } catch { /* offline: cai para cópia local */ }
  try { const s = localStorage.getItem(`meridiano.${WORKSPACE}.${key}`); return s ? JSON.parse(s) : null; } catch { return null; }
}
export function fnKey(r: Route | null) {
  return r ? `fn:${r.instrument_id || "-"}:${r.fn}` : "fn:-";
}
