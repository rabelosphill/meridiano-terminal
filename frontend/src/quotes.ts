// Cotações ao vivo: snapshot periódico + SSE. Atualiza valores in-place (sem reordenar linhas).
import { useSyncExternalStore } from "react";
import { api } from "./api";

export type Quote = {
  ticker: string; listing_id: string; instrument_id: string; exchange?: string; kind: string; name: string; currency: string;
  price?: string; prev_close?: string; change?: string; change_pct?: string; observed_at?: string; source?: string;
  feed_class?: string; feed_state?: string; feed_label?: string; market?: any;
};
type TapeItem = { seq: number; type: string; ticker?: string; price?: string; at: string; source?: string; state?: string };

let quotes: Record<string, Quote> = {};
let feeds: any[] = [];
let version = 0;
let tape: TapeItem[] = [];
const subs = new Set<() => void>();
const emit = () => { version++; subs.forEach((f) => f()); };

export function useQuotes() {
  useSyncExternalStore((cb) => { subs.add(cb); return () => subs.delete(cb); }, () => version);
  return { quotes, feeds, tape };
}
export function getQuote(t?: string) { return t ? quotes[t] : undefined; }

async function refresh() {
  try {
    const r = await api<{ quotes: Quote[]; feeds: any[] }>("/api/quotes");
    const next: Record<string, Quote> = {};
    for (const q of r.quotes) next[q.ticker] = q;
    quotes = next; feeds = r.feeds; emit();
  } catch { /* mantém último valor válido */ }
}

let started = false;
export function startQuotes() {
  if (started) return; started = true;
  refresh();
  setInterval(refresh, 5000);
  const es = new EventSource("/api/stream");
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data) as TapeItem;
    tape = [ev, ...tape].slice(0, 300);
    if (ev.type === "quote" && ev.ticker && quotes[ev.ticker] && quotes[ev.ticker].feed_state !== "no_permission") {
      const q = quotes[ev.ticker];
      const pc = q.prev_close ? Number(q.prev_close) : NaN;
      const p = Number(ev.price);
      quotes = { ...quotes, [ev.ticker]: { ...q, price: ev.price, observed_at: ev.at, feed_state: "ok",
        change: isFinite(pc) ? String(p - pc) : q.change, change_pct: isFinite(pc) ? String((p / pc - 1) * 100) : q.change_pct } };
    }
    if (ev.type === "feed") refresh();
    emit();
  };
}
