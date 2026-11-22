import { useEffect, useState } from "react";
import { api, put } from "../api";
import { dt, num, pct, timeOnly } from "../format";
import { run } from "../nav";
import { loadState, Route, saveState } from "../store";

export default function Overview({ route }: { route: Route }) {
  const [o, setO] = useState<any>(null);
  const [tab, setTab] = useState("summary");
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    setO(null);
    api(`/api/instruments/${route.instrument_id}/overview`).then(setO).catch((e) => setErr(e.message));
    loadState<{ tab: string }>(`fn:${route.instrument_id}:OVERVIEW`).then((s) => s?.tab && setTab(s.tab));
  }, [route.instrument_id]);
  const pick = (t: any) => {
    if (!t.enabled) return;
    const base = `${route.ticker} ${route.exchange || ""}`;
    if (t.code === "financials") return run(`${base} FIN A IS`);
    if (t.code === "cash") return run(`${base} FIN A CF`);
    if (t.code === "documents") return run(`${base} FILINGS`);
    if (t.code === "thesis") return run(`THESIS ${route.ticker}:${route.exchange}`);
    if (t.code === "valuation") return run(`${base} DCF`);
    setTab(t.code); saveState(`fn:${route.instrument_id}:OVERVIEW`, { tab: t.code });
  };
  if (err) return <div className="callout err">{err}</div>;
  if (!o) return <div className="note">carregando…</div>;
  const cur = o.tabs.find((t: any) => t.code === tab);
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div className="tabs" role="tablist">
        {o.tabs.map((t: any) => <button key={t.code} role="tab" aria-selected={tab === t.code} className={tab === t.code ? "on" : ""} disabled={!t.enabled} title={t.requires || ""} onClick={() => pick(t)}>{t.label}</button>)}
      </div>
      <div className="pb">
        <div className="view">
          {tab === "summary" && <Summary o={o} />}
          {tab === "business" && <Business o={o} />}
          {tab === "debt" && <Debt o={o} />}
          {tab === "peers" && <Peers route={route} />}
          {tab === "events" && <Events o={o} />}
          {cur && !cur.enabled && <div className="callout">{cur.requires}</div>}
          <h3>Cobertura das abas</h3>
          <table className="tbl"><tbody>{o.tabs.filter((t: any) => !t.enabled).map((t: any) => <tr key={t.code}><td>{t.label}</td><td className="dim" style={{ whiteSpace: "normal" }}>{t.requires}</td></tr>)}</tbody></table>
        </div>
      </div>
    </div>
  );
}

function Summary({ o }: { o: any }) {
  const ins = o.instrument, iss = o.issuer;
  return (
    <>
      <div className="cards">
        <div className="box"><div className="dim">Emissor / entidade legal</div><b>{iss?.entity_name || ins.name}</b><div className="dim mono">{iss?.tax_id} · {iss?.country}</div>
          <div className="dim">padrão {iss?.reporting_std || "—"} · exercício termina {iss?.fiscal_year_end ? `${iss.fiscal_year_end.slice(2)}/${iss.fiscal_year_end.slice(0, 2)}` : "—"}</div></div>
        <div className="box"><div className="dim">Instrumento</div><b>{ins.name}</b><div className="dim">{ins.kind} {ins.class_name ? `· ${ins.class_name}` : ""} · {ins.currency}</div>
          <div className="dim mono" style={{ fontSize: 10.5 }}>chave persistente {ins.id}</div>
          {Object.keys(ins.attrs || {}).length > 0 && <div className="mono" style={{ fontSize: 10.5 }}>{Object.entries(ins.attrs).map(([k, v]) => `${k}=${v}`).join(" · ")}</div>}</div>
        <div className="box"><div className="dim">Identificadores</div>{o.identifiers.map((i: any) => <div key={i.scheme + i.value} className="mono" style={{ fontSize: 11 }}>{i.scheme} {i.value}</div>)}</div>
      </div>
      <h3>Listagens (ticker é chave de busca; vigências preservadas)</h3>
      <table className="tbl"><thead><tr><th>Ticker</th><th>Bolsa</th><th>Tipo</th><th>Moeda</th><th>Vigência</th><th>Status</th></tr></thead><tbody>
        {o.listings.map((l: any) => <tr key={l.id}><td className="mono">{l.ticker}</td><td>{l.exchange || "OTC"}</td><td className="dim">{l.kind} {l.class_name}</td><td>{l.currency}</td>
          <td className="mono dim">{l.valid_from} → {l.valid_to || "vigente"}</td><td>{l.status}</td></tr>)}</tbody></table>
      {o.adr_parity.length > 0 && (<>
        <h3>Paridade ADR</h3>
        <table className="tbl"><thead><tr><th>ADR</th><th>Razão (vigência)</th><th>Local</th><th>USD/BRL</th><th>Implícito</th><th>ADR</th><th>Prêmio</th><th>Horários</th></tr></thead><tbody>
          {o.adr_parity.map((a: any) => <tr key={a.adr}><td className="mono">{a.adr}</td><td className="dim">{a.ratio} <span className="dim2">desde {a.valid_from}</span></td>
            <td className="num mono">{num(a.local_price, 2)}</td><td className="num mono" title={a.fx_source}>{num(a.fx, 4)}</td><td className="num mono">{num(a.implied, 2)}</td>
            <td className="num mono">{num(a.adr_price, 2)}</td><td className="num mono">{a.premium_pct ? num(a.premium_pct, 2) + "%" : "—"}</td>
            <td className="dim" style={{ fontSize: 10.5 }}>B3 {timeOnly(a.local_time, "America/Sao_Paulo")} BRT · NY {timeOnly(a.adr_time, "America/New_York")} ET · FX ref. {dt(a.fx_ref)}</td></tr>)}
        </tbody></table>
        <div className="note">{o.adr_parity[0]?.convention}. {o.adr_parity[0]?.warning}</div>
      </>)}
      {o.coverage?.length > 0 && (<>
        <h3>Cobertura de fundamentos</h3>
        <table className="tbl"><thead><tr><th>Fonte</th><th>Demonstração</th><th>Fatos</th><th>De</th><th>Até</th><th>Última divulgação</th></tr></thead><tbody>
          {o.coverage.map((c: any) => <tr key={c.source + c.statement}><td>{c.source}</td><td>{c.statement}</td><td className="num">{num(c.n)}</td><td className="mono">{dt(c.first)}</td><td className="mono">{dt(c.last)}</td><td className="mono">{dt(c.last_published, c.source === "CVM_DADOS" ? "America/Sao_Paulo" : "America/New_York").slice(0, 8)}</td></tr>)}</tbody></table>
      </>)}
    </>
  );
}

function Business({ o }: { o: any }) {
  const sp = o.sector_pack;
  return (<>
    <p>{o.issuer?.description}</p>
    {sp && (<><h3>Pacote setorial: {sp.label}</h3>
      <table className="tbl"><thead><tr><th>Métrica priorizada</th><th>Status</th></tr></thead><tbody>
        {sp.priority.map((p: any) => <tr key={p.key}><td>{p.label}</td><td className={p.available ? "up" : "dim"} style={{ whiteSpace: "normal" }}>{p.available ? "✓ disponível (biblioteca de métricas)" : `requer: ${p.requires}`}</td></tr>)}</tbody></table></>)}
  </>);
}

function Debt({ o }: { o: any }) {
  const [m, setM] = useState<any>(null);
  useEffect(() => { if (o.issuer) api(`/api/issuers/${o.issuer.id}/metrics?freq=A`).then(setM); }, [o.issuer?.id]);
  if (!m) return <div className="note">carregando…</div>;
  const rows: [string, string, boolean][] = [["debt_current", "Dívida CP", false], ["debt_noncurrent", "Dívida LP", false], ["cash", "Caixa e equivalentes", false], ["total_debt", "Dívida bruta", true], ["net_debt", "Dívida líquida", true]];
  return (<>
    <div className="note">Saldos no fim de cada exercício — {m.currency} milhões. Saldos nunca são somados entre trimestres.</div>
    <table className="tbl"><thead><tr><th>Item</th>{m.periods.map((p: any) => <th key={p.period_end}>{dt(p.period_end)}</th>)}</tr></thead><tbody>
      {rows.map(([k, l, met]) => <tr key={k}><td>{l}{met && <span className="badge calc" style={{ marginLeft: 6 }}>ƒ</span>}</td>
        {m.periods.map((p: any) => { const v = met ? p.metrics[k].value : p.values[k]; return <td key={p.period_end} className="num mono" title={met ? p.metrics[k].formula : ""}>{v === null || v === undefined ? "—" : num(Number(v) / 1e6)}</td>; })}</tr>)}
    </tbody></table>
    <div className="note">{m.periods[0]?.metrics.net_debt.convention}</div>
  </>);
}

export function Peers({ route }: { route: Route }) {
  const [p, setP] = useState<any>(null);
  const [txt, setTxt] = useState("");
  useEffect(() => { api(`/api/peers/${route.instrument_id}`).then((r) => { setP(r); setTxt(r.members.map((m: any) => `${m.ticker}:${m.exchange || ""}`).join(" ")); }); }, [route.instrument_id]);
  if (!p) return <div className="note">carregando…</div>;
  const save = async () => { const r = await put(`/api/peers/${route.instrument_id}`, { tickers: txt.split(/\s+/).filter(Boolean) }); setP(r); };
  return (<>
    <div className="note">Grupo de pares ({p.origin}). Edite e salve; o grupo é por usuário.</div>
    <div style={{ display: "flex", gap: 6 }}><input className="field" style={{ flex: 1 }} value={txt} onChange={(e) => setTxt(e.target.value.toUpperCase())} /><button className="btn pri" onClick={save}>Salvar pares</button></div>
    <table className="tbl" style={{ marginTop: 6 }}><tbody>{p.members.map((m: any) => <tr key={m.id}><td className="mono">{m.ticker}</td><td>{m.name}</td><td className="dim">{m.sector_pack}</td></tr>)}</tbody></table>
    {p.members.length > 0 && <button className="btn" style={{ marginTop: 6 }} onClick={() => run(`COMPARE ${route.ticker}:${route.exchange} ${p.members.map((m: any) => `${m.ticker}:${m.exchange}`).join(" ")}`)}>Comparar com pares</button>}
  </>);
}

function Events({ o }: { o: any }) {
  return (<>
    <h3>Eventos corporativos</h3>
    {o.corporate_actions.length === 0 ? <div className="note">Nenhum evento cadastrado. Conector de eventos (proventos B3 / 8-K) é próximo ciclo.</div> :
      <table className="tbl"><thead><tr><th>Data ex</th><th>Tipo</th><th>Razão / valor</th><th>Detalhe</th></tr></thead><tbody>
        {o.corporate_actions.map((a: any) => <tr key={a.kind + a.ex_date}><td className="mono">{dt(a.ex_date)}</td><td>{a.kind}</td><td className="num mono">{a.ratio ?? a.amount ?? ""}</td><td className="dim">{JSON.stringify(a.detail)}</td></tr>)}</tbody></table>}
  </>);
}
