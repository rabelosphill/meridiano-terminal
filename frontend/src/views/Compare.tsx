import { useEffect, useState } from "react";
import { post } from "../api";
import { CCY_SYM, num, pct } from "../format";
import { run } from "../nav";
import { Route } from "../store";

const ROWS: [string, string, "abs" | "pct"][] = [
  ["revenue", "Receita", "abs"], ["revenue_growth", "Crescimento a/a", "pct"], ["gross_margin", "Margem bruta", "pct"], ["ebit", "EBIT", "abs"],
  ["ebit_margin", "Margem operacional", "pct"], ["net_income", "Lucro líquido", "abs"], ["net_margin", "Margem líquida", "pct"], ["cfo", "Caixa das operações", "abs"],
  ["capex", "Capex", "abs"], ["fcf", "FCF (CFO − capex)", "abs"], ["fcf_margin", "Margem FCF", "pct"], ["net_debt", "Dívida líquida (saldo)", "abs"], ["roe", "ROE", "pct"],
];

export default function Compare({ route }: { route: Route }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const ccy = route.args.ccy || "NATIVE";
  useEffect(() => { setD(null); post("/api/compare", { instruments: route.args.instruments, ccy, freq: route.args.freq || "A" }).then(setD).catch((e) => setErr(e.message)); }, [route.text]);
  const base = route.args.instruments.map((i: any) => `${i.ticker}:${i.exchange}`).join(" ");
  if (err) return <div className="callout err">{err}</div>;
  if (!d) return <div className="note">carregando…</div>;
  return (
    <div>
      <div className="toolbar">
        <span>Moeda:</span>
        <div className="seg">{["NATIVE", "BRL", "USD"].map((c) => <button key={c} className={ccy === c ? "on" : ""} onClick={() => run(`COMPARE ${base}${c !== "NATIVE" ? " CCY=" + c : ""}`)}>{c === "NATIVE" ? "Nativa" : c}</button>)}</div>
        <span className="dim">Período: exercícios fiscais completos (datas explícitas por emissor)</span>
      </div>
      <div style={{ overflow: "auto" }}>
        <table className="tbl">
          <thead>
            <tr><th>Métrica</th>{d.columns.map((c: any) => <th key={c.ticker} colSpan={c.periods.length} style={{ textAlign: "center", borderLeft: "1px solid var(--line-2)" }}>
              {c.ticker} · {c.issuer} <span className="dim">({CCY_SYM[c.currency]} mi{c.currency !== c.native_currency ? `, convertido de ${c.native_currency}` : ""} · {c.standard})</span></th>)}</tr>
            <tr><th></th>{d.columns.flatMap((c: any) => c.periods.map((p: any, i: number) => <th key={c.ticker + p.period_end} style={i === 0 ? { borderLeft: "1px solid var(--line-2)" } : {}} title={p.calendar}>{p.fiscal_label}<div className="dim2 mono" style={{ fontSize: 9.5 }}>{p.period_end}</div></th>))}</tr>
          </thead>
          <tbody>
            {ROWS.map(([k, l, t]) => <tr key={k}><td>{l}</td>{d.columns.flatMap((c: any) => c.periods.map((p: any, i: number) => {
              const v = t === "pct" ? p.ratios[k] : p.values[k];
              return <td key={c.ticker + p.period_end + k} className="num mono" style={i === 0 ? { borderLeft: "1px solid var(--line-2)" } : {}}>{v === null || v === undefined ? "—" : t === "pct" ? pct(v) : num(Number(v) / 1e6)}</td>;
            }))}</tr>)}
            {d.currency_mode !== "NATIVE" && <tr><td className="dim">PTAX usada (fluxo / saldo)</td>{d.columns.flatMap((c: any) => c.periods.map((p: any) => <td key={c.ticker + p.period_end + "fx"} className="num mono dim" style={{ fontSize: 10.5 }}>{p.fx ? `${num(p.fx.flows?.rate, 4)} / ${num(p.fx.balances?.rate, 4)}` : "nativa"}</td>))}</tr>}
          </tbody>
        </table>
      </div>
      {d.columns.some((c: any) => c.periods.some((p: any) => p.flags.length)) && <div className="callout">{[...new Set(d.columns.flatMap((c: any) => c.periods.flatMap((p: any) => p.flags)))].join(" · ")}</div>}
      <div className="note">{d.notes.map((n: string) => <div key={n}>• {n}</div>)}</div>
    </div>
  );
}
