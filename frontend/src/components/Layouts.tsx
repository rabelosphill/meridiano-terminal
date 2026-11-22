// Layouts: prontos (Visão Geral, Gráfico, Balanço, Notícias, Mesa Brasil–EUA) e salvos pelo usuário.
// Um layout salvo guarda painéis, comando, e o estado do gráfico (ativo, intervalo, janela, estudos, desenhos, benchmark, candle).
import { useEffect, useState } from "react";
import { api, put } from "../api";
import { run } from "../nav";
import { fnKey, get, loadState, saveState, set } from "../store";

export default function Layouts() {
  const [d, setD] = useState<any>(null);
  const load = () => api("/api/layouts").then(setD);
  useEffect(() => { load(); }, []);
  const apply = async (name: string) => {
    if (d.builtin[name]) {
      const b = d.builtin[name]; const r = get().route;
      set({ layout: { sizes: b.sizes, collapsed: b.collapsed, maximized: null } });
      const t = r?.ticker ? `${r.ticker} ${r.exchange || ""}` : "PETR4 B3";
      return run(b.cmd.replace("{T}", t));
    }
    const s = d.saved.find((x: any) => x.name === name)?.state;
    if (!s) return;
    set({ layout: s.layout });
    if (s.fnKey && s.fnState) saveState(s.fnKey, s.fnState, 0);
    await new Promise((r) => setTimeout(r, 450));
    await run(s.cmd);
    if (s.cell) history.replaceState(null, "", `${location.hash.split("&cell=")[0]}&cell=${encodeURIComponent(s.cell)}`);
  };
  const saveCurrent = async () => {
    const name = prompt("Nome do layout:"); if (!name) return;
    const r = get().route; const k = fnKey(r);
    const fnState = await loadState<any>(k);
    const cell = new URLSearchParams(location.hash.slice(1)).get("cell") || undefined;
    await put(`/api/layouts/${encodeURIComponent(name)}`, { layout: get().layout, cmd: r?.text, fnKey: k, fnState, cell });
    load();
  };
  if (!d) return null;
  return (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
      <select className="field" style={{ fontSize: 11 }} value="" onChange={(e) => apply(e.target.value)} aria-label="layouts">
        <option value="" disabled>Layouts…</option>
        <optgroup label="Prontos">{Object.keys(d.builtin).map((n) => <option key={n}>{n}</option>)}</optgroup>
        {d.saved.length > 0 && <optgroup label="Meus">{d.saved.map((s: any) => <option key={s.name}>{s.name}</option>)}</optgroup>}
      </select>
      <button className="btn" style={{ padding: "0 8px" }} onClick={saveCurrent}>salvar layout…</button>
    </span>
  );
}
