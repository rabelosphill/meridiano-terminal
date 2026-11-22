// Watchlist: linhas estáveis (cotações mudam in-place, sem reordenar), navegação por setas, Enter abre no grupo A.
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { dir, num, signed, timeOnly } from "../format";
import { useQuotes } from "../quotes";
import { run } from "../nav";
import { get, useStore } from "../store";

const EQ = ["equity_common", "equity_pref", "adr"];

export function openInGroup(t: { ticker: string; exchange?: string; kind: string }) {
  const r = get().route;
  const base = `${t.ticker}${t.exchange ? " " + t.exchange : ""}`;
  // o grupo A segue o ativo mantendo a função corrente quando compatível
  if (r && EQ.includes(t.kind) && ["FIN", "FILINGS", "DCF", "OVERVIEW"].includes(r.fn))
    return run(r.fn === "FIN" ? `${base} FIN ${r.args?.freq || "A"} ${r.args?.statement || "IS"}` : `${base} ${r.fn}`);
  return run(`${base} OVERVIEW`);
}

export default function Watchlist({ name = "MINHA-MESA" }: { name?: string }) {
  const [items, setItems] = useState<any[]>([]);
  const [sel, setSel] = useState(0);
  const { quotes } = useQuotes();
  const active = useStore((s) => s.route?.ticker);
  const refs = useRef<(HTMLTableRowElement | null)[]>([]);
  const reload = () => api(`/api/watchlists/${name}`).then((w) => setItems(w.items));
  useEffect(() => { reload(); const h = () => reload(); window.addEventListener("meridiano:watch", h); return () => window.removeEventListener("meridiano:watch", h); }, [name]);

  return (
    <table className="tbl" role="grid" aria-label={`Watchlist ${name}`}>
      <thead><tr><th>Ativo</th><th>Último</th><th>Var.</th><th title="classe do feed">Feed</th></tr></thead>
      <tbody>
        {items.map((it, i) => {
          const q = quotes[it.ticker] || it;
          const st = q.feed_state === "interrupted" ? "interrupted" : q.feed_class === "simulated" ? "sim" : q.feed_class === "eod" ? "eod" : q.feed_state;
          return (
            <tr key={it.ticker} ref={(el) => (refs.current[i] = el)} tabIndex={i === sel ? 0 : -1} className={active === it.ticker ? "sel" : ""}
                onFocus={() => setSel(i)} onClick={() => openInGroup(it)}
                onKeyDown={(e) => {
                  if (e.key === "ArrowDown") { e.preventDefault(); refs.current[Math.min(i + 1, items.length - 1)]?.focus(); }
                  if (e.key === "ArrowUp") { e.preventDefault(); refs.current[Math.max(i - 1, 0)]?.focus(); }
                  if (e.key === "Enter") openInGroup(it);
                }}>
              <td title={`${it.name} · ${it.exchange || "OTC"}`}><span className="mono">{it.ticker}</span> <span className="dim2" style={{ fontSize: 10 }}>{it.exchange || ""}</span></td>
              <td className="num mono">{q.price ? num(q.price, Number(q.price) > 1000 ? 0 : 2) : <span className="dim2">—</span>}</td>
              <td className={"num mono " + dir(q.change_pct)} style={{ fontSize: 11 }}>{q.change_pct ? signed(q.change_pct, 2, "%") : ""}</td>
              <td title={`${q.feed_label || ""}${q.observed_at ? " · obs. " + q.observed_at : ""}`}>
                <span className={"badge " + st}>{st === "sim" ? "SIM" : st === "eod" ? "EOD" : st === "interrupted" ? "INT" : st === "no_permission" ? "🔒" : st === "stale" ? "ATR" : (st || "").slice(0, 3).toUpperCase()}</span>
                {q.feed_class === "simulated" && q.observed_at && <span className="dim2 mono" style={{ fontSize: 9.5, marginLeft: 4 }}>{timeOnly(q.observed_at)}</span>}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
