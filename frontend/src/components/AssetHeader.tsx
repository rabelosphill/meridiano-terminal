// Cabeçalho do ativo (fixo): preço com sinal, estado do mercado separado do estado do feed, horário da bolsa x local.
import { useEffect, useState } from "react";
import { dir, dt, num, signed, timeOnly } from "../format";
import { useQuotes } from "../quotes";
import { useStore } from "../store";
import { run } from "../nav";

const KIND: Record<string, string> = { equity_common: "Ação ON", equity_pref: "Ação PN", adr: "ADR", index: "Índice", fx: "Câmbio", gov_bond: "Título soberano",
  future: "Futuro", option: "Opção", commodity: "Commodity", etf: "ETF" };
const MKT_LBL: Record<string, string> = { open: "mercado aberto", closed: "mercado fechado", holiday: "feriado", "n/a": "sem pregão" };

export default function AssetHeader() {
  const route = useStore((s) => s.route);
  const { quotes } = useQuotes();
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(t); }, []);
  const q = route?.ticker ? quotes[route.ticker] : undefined;
  if (!route?.ticker) {
    return (
      <div className="assethdr">
        <span className="tk">{route?.fn || "MERIDIANO"}</span><span className="nm">{route?.text}</span><span style={{ flex: 1 }} />
        <Clocks />
      </div>
    );
  }
  const mk = q?.market;
  return (
    <div className="assethdr" aria-live="off">
      <span className="tk">{route.ticker}</span>
      <span className="dim mono">{route.exchange || "OTC"}</span>
      <span className="nm">{q?.name}</span>
      <span className="badge">{KIND[route.kind || ""] || route.kind}</span>
      {q?.price ? (
        <>
          <span className="px">{num(q.price, 2)} <span className="dim" style={{ fontSize: 11 }}>{q.currency}</span></span>
          <span className={"mono " + dir(q.change_pct)}>{signed(q.change, 2)} ({signed(q.change_pct, 2, "%")})</span>
        </>
      ) : <span className="dim">{q?.feed_label || "sem cotação"}</span>}
      {q && <span className={"badge " + (q.feed_state === "interrupted" ? "interrupted" : q.feed_class === "simulated" ? "sim" : q.feed_state === "stale" ? "stale" : "eod")} title={q.feed_label}>
        {q.feed_state === "interrupted" ? "FEED INTERROMPIDO" : q.feed_class === "simulated" ? "SIMULADO" : q.feed_class?.toUpperCase()}</span>}
      {mk && <span className={"badge " + mk.state} title={mk.session}>{MKT_LBL[mk.state] || mk.label}{mk.state === "holiday" ? `: ${mk.label.split(": ")[1]}` : ""}</span>}
      <span className="kv opt"><span className="k">obs. (hora da bolsa)</span><span className="mono">{q?.observed_at ? (q.observed_at.length > 10 ? timeOnly(q.observed_at, mk?.timezone) : dt(q.observed_at)) : "—"}</span></span>
      <span className="kv opt"><span className="k">obs. (hora local)</span><span className="mono">{q?.observed_at && q.observed_at.length > 10 ? timeOnly(q.observed_at) : "—"}</span></span>
      {route.notice && <span className="badge warn">{route.notice}</span>}
      <span className="hdrnav">
        {(["OVERVIEW", "CHART", "FIN Q", "NEWS"] as const).filter((f) => !(route.fn === f || (f === "FIN Q" && route.fn === "FIN"))).map((f) => (
          <button key={f} className="btn sm" title={`${route.ticker} ${route.exchange || ""} ${f}`}
            onClick={() => run(f === "NEWS" ? `NEWS ${route.ticker}:${route.exchange || ""}` : `${route.ticker} ${route.exchange || ""} ${f}`)}>
            {f === "CHART" ? "Gráfico" : f === "OVERVIEW" ? "Resumo" : f === "FIN Q" ? "Demonstrações" : "Notícias"}</button>))}
      </span>
      <span style={{ flex: 1 }} />
      <Clocks />
    </div>
  );
}

function Clocks() {
  const now = new Date().toISOString();
  return (
    <>
      <span className="kv opt"><span className="k">São Paulo</span><span className="mono">{timeOnly(now, "America/Sao_Paulo")}</span></span>
      <span className="kv opt"><span className="k">Nova York</span><span className="mono">{timeOnly(now, "America/New_York")}</span></span>
      <span className="kv opt"><span className="k">Local</span><span className="mono">{timeOnly(now)}</span></span>
    </>
  );
}
