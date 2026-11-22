// Barra de comando: sugestões locais (índice em memória), Enter executa, Esc devolve o foco anterior.
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { run } from "../nav";
import { set, useStore } from "../store";

type Idx = { ticker: string; exchange?: string; name: string; issuer?: string; entity?: string; kind: string; active: boolean; terms: string; valid_to?: string | null; status?: string };
type Cmd = { code: string; title: string; syntax: string; synonyms: string[]; examples: string[]; kinds: string[] | null };
type Sug = { text: string; label: string; hint: string; group: string };

const norm = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toUpperCase();
export const perf: { suggest: number[] } = { suggest: [] };
(window as any).__meridianoPerf = perf;
(window as any).__meridianoSuggestPure = (q: string, idx: any[], cmds: any[]) => suggest(q, idx, cmds);

export function suggest(input: string, idx: Idx[], cmds: Cmd[]): Sug[] {
  const t0 = performance.now();
  const q = norm(input.trim());
  const out: Sug[] = [];
  if (!q) {
    for (const c of cmds) out.push({ text: c.examples[0], label: c.examples[0], hint: c.title, group: "Comandos" });
  } else {
    const toks = q.split(/\s+/);
    const head = toks[0];
    // 1) comandos
    for (const c of cmds) {
      const names = [c.code, ...c.synonyms];
      if (names.some((n) => n.startsWith(head)) && toks.length === 1)
        for (const ex of c.examples.slice(0, 2)) out.push({ text: ex, label: ex, hint: `${c.title} — ${c.syntax}`, group: "Comandos" });
    }
    // 2) instrumentos (ticker, nome, emissor, identificadores) e funções aplicáveis
    const instrQ = toks.length > 1 && /^[A-Z0-9.:]+$/.test(head) ? head.split(":")[0] : q;
    const hits = idx.filter((r) => (toks.length > 1 && /^[A-Z0-9.:]+$/.test(head) ? r.ticker.toUpperCase().startsWith(instrQ) : toks.every((t) => r.terms.includes(t))));
    const EQK = ["equity_common", "equity_pref", "equity_unit", "adr"];
    const rank = (r: Idx) => (r.ticker.toUpperCase() === instrQ ? 100 : 0) + (r.ticker.toUpperCase().startsWith(instrQ) ? 30 : 0) + (r.active ? 10 : 0)
      + (EQK.includes(r.kind) ? 25 : 0) + (norm(r.issuer || "").startsWith(q) ? 15 : 0);
    hits.sort((a, b) => rank(b) - rank(a) || a.ticker.length - b.ticker.length || a.ticker.localeCompare(b.ticker));
    for (const h of hits.slice(0, 8)) {
      const base = `${h.ticker}${h.exchange ? " " + h.exchange : ""}`;
      const eq = ["equity_common", "equity_pref", "adr"].includes(h.kind);
      const fns = eq ? ["OVERVIEW", "FIN A", "FIN Q", "FILINGS", "DCF"] : ["OVERVIEW"];
      const typed = toks.slice(1).join(" ");
      for (const f of fns) {
        if (typed && !f.startsWith(typed.replace(/^(B3|NASDAQ|NYSE)\s*/, ""))) continue;
        out.push({ text: `${base} ${f}`, label: `${base} ${f}`, hint: `${h.name}${h.active ? "" : ` · ticker histórico (até ${h.valid_to})`}`, group: "Instrumentos" });
        if (!typed) break;
      }
    }
    if (toks.length === 1 && hits.length === 0) out.push({ text: `FIND ${input.trim()}`, label: `FIND ${input.trim()}`, hint: "buscar empresas, instrumentos e listagens", group: "Busca" });
  }
  perf.suggest.push(performance.now() - t0);
  if (perf.suggest.length > 2000) perf.suggest.shift();
  return out.slice(0, 14);
}

export default function CommandBar() {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [sel, setSel] = useState(-1);
  const [idx, setIdx] = useState<Idx[]>([]);
  const [cmds, setCmds] = useState<Cmd[]>([]);
  const prevFocus = useRef<HTMLElement | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const error = useStore((s) => s.error);

  useEffect(() => {
    api("/api/search/index", { cacheMs: 600000 }).then(setIdx);
    api("/api/commands", { cacheMs: 600000 }).then((r) => setCmds(r.commands));
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (document.activeElement !== input.current) prevFocus.current = document.activeElement as HTMLElement;
        input.current?.focus(); input.current?.select(); setOpen(true);
      }
    };
    window.addEventListener("keydown", onKey);
    (window as any).__meridianoSuggest = (s: string) => suggest(s, idxRef.current, cmdsRef.current);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const idxRef = useRef(idx); idxRef.current = idx;
  const cmdsRef = useRef(cmds); cmdsRef.current = cmds;

  const sugs = useMemo(() => (open ? suggest(text, idx, cmds) : []), [text, idx, cmds, open]);
  useEffect(() => setSel(-1), [text]);

  const restoreFocus = () => {
    setOpen(false);
    const p = prevFocus.current;
    if (p && document.contains(p)) p.focus(); else input.current?.blur();
  };
  const exec = async (t: string) => {
    if (!t.trim()) return;
    setOpen(false);
    const ok = await run(t);
    if (ok) { setText(""); restoreFocus(); }
  };

  return (
    <div className="cmd">
      <span className="prompt">›</span>
      <input
        ref={input} value={text} spellCheck={false} aria-label="Barra de comando" placeholder="PETR4 B3 FIN Q · AAPL NASDAQ FIN A · FIND PETROBRAS · HELP"
        onFocus={(e) => { if (!prevFocus.current || prevFocus.current === e.target) prevFocus.current = (e.relatedTarget as HTMLElement) || null; setOpen(true); }}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={(e) => { setText(e.target.value); setOpen(true); if (error) set({ error: null }); }}
        onKeyDown={(e) => {
          if (e.key === "Escape") { e.preventDefault(); set({ error: null }); restoreFocus(); return; }
          if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, sugs.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, -1)); }
          if (e.key === "Tab" && sugs.length && !e.shiftKey) { e.preventDefault(); setText(sugs[Math.max(sel, 0)].text); }
          if (e.key === "Enter") {
            e.preventDefault();
            const typed = text.trim();
            // Enter executa o texto digitado; com uma sugestão escolhida por ↑/↓, executa a sugestão
            exec(sel >= 0 && sugs[sel] ? sugs[sel].text : typed);
          }
        }}
      />
      {open && sugs.length > 0 && !error && (
        <div className="sugg" role="listbox">
          {sugs.map((s, i) => (
            <div key={s.text + i}>
              {(i === 0 || sugs[i - 1].group !== s.group) && <div className="grp">{s.group}</div>}
              <div className={"it" + (i === sel ? " sel" : "")} role="option" aria-selected={i === sel}
                   onMouseDown={(e) => { e.preventDefault(); exec(s.text); }}>
                <span className="mono">{s.label}</span><span className="dim">{s.hint}</span>
              </div>
            </div>
          ))}
          <div className="foot"><span><span className="kbd">↑↓</span> navegar</span><span><span className="kbd">Tab</span> completar</span><span><span className="kbd">Enter</span> executar</span><span><span className="kbd">Esc</span> voltar</span></div>
        </div>
      )}
      {error && (
        <div className="cmderr" role="alert">
          <b>{error.error === "incompatible" ? "Comando incompatível" : "Comando inválido"}:</b> {error.message}
          {error.suggestions?.length > 0 && (
            <div className="chips">{error.suggestions.map((s: string) => <button key={s} className="chip" onClick={() => exec(s)}>{s}</button>)}</div>
          )}
        </div>
      )}
    </div>
  );
}
