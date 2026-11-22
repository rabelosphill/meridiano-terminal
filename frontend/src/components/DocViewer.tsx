// Documento original com o valor destacado. Esc fecha e devolve o foco à mesma célula.
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { dt } from "../format";
import { IClose, IDown, IUp } from "./Icons";

export default function DocViewer({ factId, onClose }: { factId: number; onClose: () => void }) {
  const [html, setHtml] = useState<string | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [pos, setPos] = useState({ i: 0, n: 0 });
  const [err, setErr] = useState<string | null>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setHtml(null); setErr(null);
    api(`/api/facts/${factId}`).then(setMeta).catch((e) => setErr(e.message));
    api<string>(`/api/facts/${factId}/source`).then(setHtml).catch((e) => setErr(e.message));
    closeBtn.current?.focus();
    const onMsg = (m: MessageEvent) => {
      if (m.data?.ft === "doc-esc") onClose();
      if (m.data?.ft === "doc-pos") setPos({ i: m.data.i, n: m.data.n });
    };
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [factId]);

  const send = (ft: string) => frame.current?.contentWindow?.postMessage({ ft }, "*");
  return (
    <div className="docv" role="dialog" aria-label="Documento-fonte"
         onKeyDown={(e) => {
           if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onClose(); }
           if (e.key === "n") send("next");
           if (e.key === "N") send("prev");
           if (e.key === "PageDown" || e.key === "PageUp") { e.preventDefault(); frame.current?.contentWindow?.scrollBy(0, (e.key === "PageDown" ? 1 : -1) * (frame.current.clientHeight * 0.9)); }
         }}>
      <div className="dh">
        <button ref={closeBtn} className="btn pri" onClick={onClose} title="Esc">← Voltar à célula <span className="kbd">Esc</span></button>
        {meta && (
          <>
            <span className="mono">{meta.document?.form} {meta.document?.external_id}</span>
            <span className="dim">publicado {meta.source?.code === "CVM_DADOS" ? `${dt(meta.document?.published_at, "America/Sao_Paulo").slice(0, 8)} (CVM: precisão de dia, BRT)` : `${dt(meta.document?.published_at, "America/New_York")} ET`}</span>
            <span className="badge">{meta.source?.code}</span>
            <span className="dim mono" style={{ overflow: "hidden", textOverflow: "ellipsis", maxWidth: 420 }}>{meta.location?.text}</span>
          </>
        )}
        <span style={{ flex: 1 }} />
        {pos.n > 1 && (<>
          <span className="dim">ocorrência {pos.i + 1}/{pos.n}</span>
          <button className="ibtn" onClick={() => send("prev")} title="anterior (Shift+N)"><IUp /></button>
          <button className="ibtn" onClick={() => send("next")} title="próxima (N)"><IDown /></button>
        </>)}
        {meta?.document?.url && <a href={meta.document.url} target="_blank" rel="noopener noreferrer" className="btn">Abrir no regulador ↗</a>}
        <button className="ibtn" onClick={onClose} aria-label="Fechar"><IClose /></button>
      </div>
      {err && <div className="callout err">{err}</div>}
      {html ? <iframe ref={frame} title="documento original" sandbox="allow-scripts" srcDoc={html} />
            : !err && <div className="note">carregando documento original…</div>}
    </div>
  );
}
