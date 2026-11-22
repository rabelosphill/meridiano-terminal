// Grade virtualizada: cabeçalho e 1ª coluna congelados, setas percorrem células,
// Enter inspeciona, S / Shift+Enter abre a fonte, PageUp/PageDown rolam o painel.
import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { num } from "../format";

export type Cell = { state: string; v?: string; basis?: string; fact_id?: number; restated?: boolean; formula?: string; inputs?: number[]; reason?: string; sign_flipped?: boolean; n_versions?: number; label?: string };
export type Row = { key?: string; concept: string; label: string; indent: number; bold?: boolean; unit?: string; cells: Cell[]; note?: boolean; fixa?: boolean };
export type Col = { id: string; label: string; calendar: string; end: string; start?: string };
export type GridHandle = { focus: () => void; scrollTop: () => number };

const RH = 22, HH = 40, CW = 108, OVERSCAN = 8;
const C0 = typeof window !== "undefined" && window.innerWidth < 760 ? 170 : 300;

function fmt(c: Cell, unit?: string): string {
  if (c.state === "absent") return "—";
  if (c.state === "not_comparable") return "n/c";
  if (c.v === undefined || c.v === null) return "—";
  const x = Number(c.v);
  if (unit === "shares") return num(x / 1e6, 1);
  if (unit && unit.includes("/sh")) return num(x, 2);
  return num(x / 1e6, Math.abs(x) < 1e7 && x !== 0 ? 1 : 0);
}

type Props = {
  rows: Row[]; cols: Col[]; cur: { r: number; c: number }; inspected?: { r: number; c: number } | null;
  onMove: (p: { r: number; c: number }) => void; onInspect: (p: { r: number; c: number }) => void; onSource: (p: { r: number; c: number }) => void;
  initialScroll?: number; onScroll?: (top: number) => void;
};

export default forwardRef<GridHandle, Props>(function StatementGrid(p, ref) {
  const box = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(0);
  const [h, setH] = useState(400);
  useImperativeHandle(ref, () => ({ focus: () => box.current?.focus({ preventScroll: true }), scrollTop: () => box.current?.scrollTop || 0 }));

  useLayoutEffect(() => {
    const el = box.current!;
    const ro = new ResizeObserver(() => setH(el.clientHeight));
    ro.observe(el); setH(el.clientHeight);
    if (p.initialScroll) { el.scrollTop = p.initialScroll; setTop(p.initialScroll); }
    return () => ro.disconnect();
  }, []);

  // mantém a célula corrente visível
  useEffect(() => {
    const el = box.current; if (!el) return;
    const y = p.cur.r * RH;
    if (y < el.scrollTop) el.scrollTop = y;
    else if (y + RH > el.scrollTop + el.clientHeight - HH) el.scrollTop = y + RH - el.clientHeight + HH;
    const x = C0 + p.cur.c * CW;
    if (x + CW > el.scrollLeft + el.clientWidth) el.scrollLeft = x + CW - el.clientWidth;
    else if (x - C0 < el.scrollLeft) el.scrollLeft = Math.max(0, x - C0);
  }, [p.cur.r, p.cur.c]);

  const visible = Math.ceil(h / RH);
  const start = Math.max(0, Math.floor(top / RH) - OVERSCAN);
  const end = Math.min(p.rows.length, start + visible + OVERSCAN * 2);
  const width = C0 + p.cols.length * CW;

  const onKey = (e: React.KeyboardEvent) => {
    const { r, c } = p.cur;
    const page = Math.max(1, visible - 3);
    const mv = (nr: number, nc: number) => { e.preventDefault(); p.onMove({ r: Math.max(0, Math.min(p.rows.length - 1, nr)), c: Math.max(0, Math.min(p.cols.length - 1, nc)) }); };
    switch (e.key) {
      case "ArrowDown": return mv(r + 1, c);
      case "ArrowUp": return mv(r - 1, c);
      case "ArrowRight": return mv(r, c + 1);
      case "ArrowLeft": return mv(r, c - 1);
      case "PageDown": return mv(r + page, c);
      case "PageUp": return mv(r - page, c);
      case "Home": return mv(e.ctrlKey || e.metaKey ? 0 : r, 0);
      case "End": return mv(e.ctrlKey || e.metaKey ? p.rows.length - 1 : r, p.cols.length - 1);
      case "Enter": e.preventDefault(); return e.shiftKey ? p.onSource(p.cur) : p.onInspect(p.cur);
      case "s": case "S": if (!e.metaKey && !e.ctrlKey) { e.preventDefault(); p.onSource(p.cur); } return;
    }
  };

  return (
    <div className="grid" ref={box} tabIndex={0} role="grid" aria-rowcount={p.rows.length} aria-colcount={p.cols.length + 1}
         aria-label="Demonstração financeira: setas navegam, Enter inspeciona, S abre a fonte"
         onKeyDown={onKey} onScroll={(e) => { const t = (e.target as HTMLDivElement).scrollTop; setTop(t); p.onScroll?.(t); }}>
      <div style={{ width, minWidth: "100%" }}>
        <div className="gh" role="row">
          <div className="c0" style={{ width: C0 }}>Conta</div>
          {p.cols.map((c) => (
            <div key={c.id} className="c" style={{ width: CW }} role="columnheader" title={`Período corrido: ${c.calendar}`}>
              <span>{c.label}</span><small>{c.end.split("-").reverse().join("/")}</small>
            </div>
          ))}
        </div>
        <div style={{ height: start * RH }} />
        {p.rows.slice(start, end).map((row, i) => {
          const ri = start + i;
          return (
            <div key={row.concept + ri} className={"gr" + (row.bold ? " bold" : "")} role="row" aria-rowindex={ri + 1}>
              <div className="c0" style={{ width: C0, paddingLeft: 8 + row.indent * 12 }} title={`${row.label} · ${row.concept}`}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{row.label}</span>
                {row.unit && row.unit !== "USD" && row.unit !== "BRL" && <span className="dim2 mono" style={{ fontSize: 9.5 }}>{row.unit === "shares" ? "mi ações" : row.unit}</span>}
                {row.fixa === false && <span className="dim2" title="Conta livre da companhia (ST_CONTA_FIXA=N): código pode mudar entre documentos" style={{ fontSize: 9 }}>livre</span>}
              </div>
              {row.cells.map((cell, ci) => {
                const isCur = p.cur.r === ri && p.cur.c === ci;
                const insp = p.inspected && p.inspected.r === ri && p.inspected.c === ci;
                const neg = cell.v && Number(cell.v) < 0;
                const cls = ["c", isCur ? "cur" : "", insp ? "insp" : "", cell.state === "absent" ? "absent" : "", cell.state === "not_comparable" ? "nc" : "",
                  cell.basis === "calculated" ? "calc" : "", neg && cell.basis !== "calculated" ? "neg" : ""].join(" ");
                const title = cell.state === "absent" ? `Ausente${cell.reason ? ": " + cell.reason : " — não divulgado neste período"} (diferente de zero)`
                  : cell.state === "not_comparable" ? `Não comparável: ${cell.reason}`
                  : `${cell.v}${cell.basis === "calculated" ? ` · calculado: ${cell.formula}` : " · reportado"}${cell.restated ? " · reapresentado (há versões diferentes)" : ""}`;
                return (
                  <div key={ci} className={cls} style={{ width: CW }} role="gridcell" aria-selected={isCur} title={title}
                       onMouseDown={() => p.onMove({ r: ri, c: ci })} onClick={() => p.onInspect({ r: ri, c: ci })} onDoubleClick={() => p.onSource({ r: ri, c: ci })}>
                    {fmt(cell, row.unit)}
                    {cell.restated && <span className="mk r" aria-label="reapresentado">↺</span>}
                    {cell.basis === "calculated" && !cell.restated && <span className="mk" style={{ color: "var(--calc)" }} aria-label="calculado">ƒ</span>}
                  </div>
                );
              })}
            </div>
          );
        })}
        <div style={{ height: Math.max(0, (p.rows.length - end) * RH) }} />
      </div>
    </div>
  );
});
