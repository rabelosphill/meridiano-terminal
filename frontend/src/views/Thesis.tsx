// THESIS e DCF: premissas versionadas com autor e instante; contexto salvo permite voltar ao ponto exato.
import { useEffect, useState } from "react";
import { api, ApiError, currentUser, post } from "../api";
import { dt, num, pct } from "../format";
import { run } from "../nav";
import { get, loadState, Route, saveState } from "../store";

const LIST_KEYS = ["growth", "ebit_margin"];
const FIELDS: [string, string, "pct" | "abs" | "list" | "txt"][] = [
  ["base_revenue", "Receita base (último FY)", "abs"], ["growth", "Crescimento a/a por ano", "list"], ["ebit_margin", "Margem EBIT por ano", "list"],
  ["tax_rate", "Alíquota efetiva", "pct"], ["capex_pct_rev", "Capex / receita", "pct"], ["da_pct_rev", "D&A / receita", "pct"], ["nwc_pct_rev", "Capital de giro / Δreceita", "pct"],
  ["wacc", "WACC", "pct"], ["g", "g perpetuidade", "pct"], ["net_debt", "Dívida líquida", "abs"], ["minorities", "Não controladores", "abs"], ["diluted_shares", "Ações plenamente diluídas", "abs"],
];

export function Dcf({ route, embedded, onSave }: { route: Route; embedded?: boolean; onSave?: (inputs: any, res: any) => void }) {
  const [def, setDef] = useState<any>(null);
  const [inp, setInp] = useState<any>(null);
  const [target, setTarget] = useState("");
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api(`/api/dcf/defaults/${route.issuer_id}`).then(async (d) => {
      setDef(d);
      const s = await loadState<any>(`fn:${route.instrument_id}:DCF`);
      setInp(s?.inputs || d.inputs); setTarget(s?.target || "");
    }).catch((e) => setErr(e.message));
  }, [route.issuer_id]);
  const calc = async (i = inp) => {
    setErr(null);
    try {
      const r = await post("/api/dcf/run", { inputs: i, target_price: target || undefined });
      setRes(r); saveState(`fn:${route.instrument_id}:DCF`, { inputs: i, target });
    } catch (e: any) { setErr((e as ApiError).message); setRes(null); }
  };
  useEffect(() => { if (inp) calc(inp); }, [inp === null]);
  if (err && !inp) return <div className="callout err">{err}</div>;
  if (!inp) return <div className="note">carregando premissas…</div>;
  const setF = (k: string, v: string) => setInp({ ...inp, [k]: LIST_KEYS.includes(k) ? v.split(/[;\s]+/).filter(Boolean) : v });
  const mi = (v: any) => num(Number(v) / 1e6);
  return (
    <div className={embedded ? "" : "view"}>
      <div className="note">DCF de FCFF em {inp.currency} {inp.basis}, desconto fim de período. FCFF = EBIT×(1−t) + D&A − Capex − ΔNWC. Campos marcados "premissa do usuário" não são estimativas de mercado. Ano-base: {def?.base_period}.</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill,minmax(250px,1fr))", gap: "4px 14px" }}>
        {FIELDS.map(([k, l, t]) => (
          <label key={k} style={{ display: "grid", gridTemplateColumns: "1fr 120px", alignItems: "center", gap: 6 }} title={typeof def?.provenance?.[k] === "string" ? def.provenance[k] : def?.provenance?.[k] ? JSON.stringify(def.provenance[k]).slice(0, 200) : ""}>
            <span className="dim" style={{ fontSize: 11.5 }}>{l}{typeof def?.provenance?.[k] === "string" && def.provenance[k].startsWith("PREMISSA") && <span style={{ color: "var(--accent-2)" }}> *</span>}</span>
            <input className="field num" value={LIST_KEYS.includes(k) ? inp[k].join(" ") : inp[k]} onChange={(e) => setF(k, e.target.value)} onKeyDown={(e) => e.key === "Enter" && calc()} />
          </label>
        ))}
        <label style={{ display: "grid", gridTemplateColumns: "1fr 120px", alignItems: "center", gap: 6 }}><span className="dim">Preço p/ DCF reverso ({inp.currency})</span>
          <input className="field num" value={target} placeholder="informar" onChange={(e) => setTarget(e.target.value)} onKeyDown={(e) => e.key === "Enter" && calc()} /></label>
      </div>
      <div style={{ display: "flex", gap: 6, margin: "8px 0" }}>
        <button className="btn pri" onClick={() => calc()}>Calcular <span className="kbd">Enter</span></button>
        <button className="btn" onClick={() => { setInp(def.inputs); }}>Restaurar padrões</button>
        {onSave && res && <button className="btn" onClick={() => onSave(inp, res)}>Anexar à tese</button>}
        <span className="dim" style={{ fontSize: 11 }}><span style={{ color: "var(--accent-2)" }}>*</span> premissa do usuário · ações: {inp.share_convention}</span>
      </div>
      {err && <div className="callout err">{err}</div>}
      {res && (
        <>
          <div className="cards">
            <div className="box"><div className="dim">Valor por ação</div><div className="mono" style={{ fontSize: 20 }}>{num(res.result.per_share, 2)} <span className="dim" style={{ fontSize: 12 }}>{inp.currency}</span></div></div>
            <div className="box"><div className="dim">Enterprise value</div><div className="mono" style={{ fontSize: 16 }}>{mi(res.result.enterprise_value)} mi</div><div className="dim">TV = {pct(res.result.tv_share_of_ev)} do EV</div></div>
            {res.reverse && <div className="box"><div className="dim">DCF reverso: crescimento implícito</div><div className="mono" style={{ fontSize: 16 }}>{res.reverse.implied_growth ? pct(res.reverse.implied_growth, 2) : "sem solução"}</div><div className="dim" style={{ fontSize: 11 }}>{res.reverse.note}</div></div>}
          </div>
          <h3>Ponte EV → equity</h3>
          <table className="tbl"><tbody>{res.result.bridge.map((b: any) => <tr key={b.item}><td>{b.item}</td><td className="num mono">{mi(b.value)}</td></tr>)}
            <tr><td>÷ Ações plenamente diluídas</td><td className="num mono">{num(Number(res.result.diluted_shares) / 1e6, 1)} mi</td></tr></tbody></table>
          <h3>Projeção ({inp.currency} mi)</h3>
          <table className="tbl"><thead><tr><th>Ano</th><th>Receita</th><th>EBIT</th><th>NOPAT</th><th>D&A</th><th>Capex</th><th>ΔNWC</th><th>FCFF</th><th>VP</th></tr></thead><tbody>
            {res.result.years.map((y: any) => <tr key={y.t}><td>t+{y.t}</td>{["revenue", "ebit", "nopat", "da", "capex", "dnwc", "fcff", "pv"].map((k) => <td key={k} className="num mono">{mi(y[k])}</td>)}</tr>)}</tbody></table>
          <h3>Matriz WACC × g (valor por ação)</h3>
          <table className="tbl"><thead><tr><th>WACC \ g</th>{res.sensitivity.g.map((g: string) => <th key={g}>{pct(g, 1)}</th>)}</tr></thead><tbody>
            {res.sensitivity.rows.map((r: any) => <tr key={r.wacc}><td className="mono">{pct(r.wacc, 1)}</td>{r.values.map((v: any, i: number) => <td key={i} className="num mono" style={r.wacc === inp.wacc && res.sensitivity.g[i] === inp.g ? { outline: "1px solid var(--accent)" } : {}}>{v === null ? <span className="dim2" title="WACC ≤ g">inválido</span> : num(v, 2)}</td>)}</tr>)}</tbody></table>
          <h3>Cenários</h3>
          <table className="tbl"><thead><tr><th>Cenário</th><th>Choques</th><th>Por ação</th><th>EV (mi)</th></tr></thead><tbody>
            {Object.entries(res.scenarios).map(([k, v]: any) => <tr key={k}><td>{k}</td><td className="dim mono" style={{ fontSize: 10.5 }}>{Object.entries(v.shock).map(([a, b]) => `${a} ${Number(b) > 0 ? "+" : ""}${pct(b as string, 1)}`).join(" · ") || "—"}</td><td className="num mono">{num(v.per_share, 2)}</td><td className="num mono">{mi(v.enterprise_value)}</td></tr>)}</tbody></table>
          <div className="note">Biblioteca {res.result.library_version}. Validações: WACC &gt; g; moeda e base (nominal/real) do FCFF iguais às do WACC.</div>
        </>
      )}
    </div>
  );
}

export function Thesis({ route }: { route: Route }) {
  const [t, setT] = useState<any>(null);
  const [title, setTitle] = useState(""); const [stance, setStance] = useState("neutral"); const [body, setBody] = useState("");
  const [assm, setAssm] = useState<any[]>([]);
  const [dcf, setDcf] = useState<any>(null);
  const [showDcf, setShowDcf] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const load = () => api(`/api/thesis/${route.instrument_id}`).then((r) => {
    setT(r);
    const v = r.versions[0];
    if (r.thesis) { setTitle(r.thesis.title); setStance(r.thesis.stance); }
    if (v) { setBody(v.body); setAssm(v.assumptions || []); }
  });
  useEffect(() => { load(); }, [route.instrument_id]);
  const save = async () => {
    // contexto: último ponto de análise deste instrumento (função + célula + rolagem)
    const hist = [...get().history].reverse().find((h) => h.instrument_id === route.instrument_id && h.fn === "FIN");
    const fnState = hist ? await loadState<any>(`fn:${route.instrument_id}:FIN`) : null;
    const key = hist ? `${hist.args?.statement}:${hist.args?.freq}:${fnState?.scope || "consolidated"}` : null;
    const context = hist ? { cmd: hist.text, cell: fnState?.cells?.[key!] } : {};
    await post(`/api/thesis/${route.instrument_id}`, { title, stance, body, assumptions: assm, dcf_inputs: dcf, context });
    setMsg("Versão salva."); setTimeout(() => setMsg(null), 2500); load();
  };
  const restore = (ctx: any) => {
    if (!ctx?.cmd) return;
    // a URL com ?cell tem precedência sobre o estado salvo: o FIN abre exatamente na célula registrada na versão
    run(ctx.cmd).then((ok) => {
      if (!ok) return;
      if (ctx.candle) history.replaceState(null, "", `#cmd=${encodeURIComponent(ctx.cmd)}&cell=${encodeURIComponent("candle:" + ctx.candle)}`);
      else if (ctx.cell) history.replaceState(null, "", `#cmd=${encodeURIComponent(ctx.cmd)}&cell=${encodeURIComponent(ctx.cell.concept + "@" + ctx.cell.period)}`);
    });
  };
  if (!t) return <div className="note">carregando…</div>;
  return (
    <div className="view">
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <input className="field" style={{ flex: 1, minWidth: 200, fontFamily: "var(--font)", fontSize: 13 }} placeholder="Título da tese" value={title} onChange={(e) => setTitle(e.target.value)} />
        <div className="seg">{[["long", "Comprado"], ["neutral", "Neutro"], ["short", "Vendido"]].map(([k, l]) => <button key={k} className={stance === k ? "on" : ""} onClick={() => setStance(k)}>{l}</button>)}</div>
        <button className="btn pri" onClick={save}>Salvar nova versão</button>
        {msg && <span className="up">{msg}</span>}
      </div>
      <textarea className="field" style={{ marginTop: 6 }} placeholder="Tese, gatilhos, riscos, o que invalidaria a tese…" value={body} onChange={(e) => setBody(e.target.value)} />
      <h3>Premissas</h3>
      <table className="tbl"><thead><tr><th>Premissa</th><th>Valor</th><th>Unidade</th><th>Fonte / justificativa</th><th></th></tr></thead><tbody>
        {assm.map((a, i) => <tr key={i}>{["label", "value", "unit", "source"].map((k) => <td key={k}><input className="field" style={{ width: "100%" }} value={a[k] || ""} onChange={(e) => setAssm(assm.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} /></td>)}
          <td><button className="btn" onClick={() => setAssm(assm.filter((_, j) => j !== i))}>×</button></td></tr>)}
      </tbody></table>
      <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
        <button className="btn" onClick={() => setAssm([...assm, { label: "", value: "", unit: "", source: "estimativa do usuário" }])}>+ premissa</button>
        <button className="btn" onClick={() => setShowDcf(!showDcf)}>{showDcf ? "ocultar DCF" : "DCF da tese"}</button>
        {dcf && <span className="badge calc">DCF anexado (WACC {pct(dcf.wacc, 1)}, g {pct(dcf.g, 1)})</span>}
      </div>
      {showDcf && route.issuer_id && <div className="box" style={{ marginTop: 6 }}><Dcf route={route} embedded onSave={(i) => { setDcf(i); setShowDcf(false); }} /></div>}
      <h3>Histórico ({t.versions.length} versões)</h3>
      <table className="tbl"><thead><tr><th>v</th><th>Autor</th><th>Instante</th><th>Resumo</th><th>DCF</th><th>Contexto</th></tr></thead><tbody>
        {t.versions.map((v: any) => <tr key={v.id}><td className="num">{v.version}</td><td>{v.author}</td><td className="mono">{dt(v.created_at)}</td>
          <td className="dim" style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis" }}>{v.body.slice(0, 80)}</td>
          <td className="mono">{v.dcf ? `${num(v.dcf.result.per_share, 2)} (lib ${v.dcf.library_version})` : "—"}</td>
          <td>{v.context?.cmd ? <button className="btn" onClick={() => restore(v.context)} title={JSON.stringify(v.context)}>voltar ao ponto: {v.context.cmd}{v.context.candle ? ` @ candle ${v.context.candle}` : v.context.cell ? ` @ ${v.context.cell.concept} ${v.context.cell.period}` : ""}</button> : <span className="dim2">—</span>}</td></tr>)}
      </tbody></table>
      <div className="note">Usuário atual: {currentUser()}. Cada salvamento cria versão imutável com autor e instante; o DCF anexado guarda premissas, resultado e versão da biblioteca.</div>
    </div>
  );
}
