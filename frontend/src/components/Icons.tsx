// Ícones próprios (traço 1.6, grade 16).
const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
export const Logo = () => (
  <svg viewBox="0 0 32 32" aria-hidden><circle cx="16" cy="16" r="13" fill="none" stroke="#46d3c3" strokeWidth="2.6" /><path d="M16 3C9 10 9 22 16 29" fill="none" stroke="#e8b04a" strokeWidth="2.6" /><path d="M5 16h22" stroke="#46d3c3" strokeWidth="1.4" opacity=".55" /></svg>
);
export const IMax = () => <svg viewBox="0 0 16 16"><path {...P} d="M3 6V3h3M10 3h3v3M13 10v3h-3M6 13H3v-3" /></svg>;
export const IMin = () => <svg viewBox="0 0 16 16"><path {...P} d="M6 3v3H3M13 6h-3V3M10 13v-3h3M3 10h3v3" /></svg>;
export const ICollapseL = () => <svg viewBox="0 0 16 16"><path {...P} d="M10 3 5 8l5 5" /></svg>;
export const ICollapseR = () => <svg viewBox="0 0 16 16"><path {...P} d="m6 3 5 5-5 5" /></svg>;
export const ISave = () => <svg viewBox="0 0 16 16"><path {...P} d="M3 3h8l2 2v8H3zM5 3v3h5V3M5 13V9h6v4" /></svg>;
export const ILink = () => <svg viewBox="0 0 16 16"><path {...P} d="M7 9a3 3 0 0 0 4 0l2-2a3 3 0 0 0-4-4l-1 1M9 7a3 3 0 0 0-4 0L3 9a3 3 0 0 0 4 4l1-1" /></svg>;
export const IPin = () => <svg viewBox="0 0 16 16"><path {...P} d="M6 2h4l-.5 4 2.5 2v1H4V8l2.5-2zM8 9v5" /></svg>;
export const IDoc = () => <svg viewBox="0 0 16 16"><path {...P} d="M4 2h5l3 3v9H4zM9 2v3h3M6 8h4M6 11h4" /></svg>;
export const IPause = () => <svg viewBox="0 0 16 16"><path {...P} d="M5 3v10M11 3v10" /></svg>;
export const IPlay = () => <svg viewBox="0 0 16 16"><path {...P} d="M5 3l8 5-8 5z" /></svg>;
export const IBack = () => <svg viewBox="0 0 16 16"><path {...P} d="M7 4 3 8l4 4M3 8h10" /></svg>;
export const IClose = () => <svg viewBox="0 0 16 16"><path {...P} d="m4 4 8 8M12 4l-8 8" /></svg>;
export const IUp = () => <svg viewBox="0 0 16 16"><path {...P} d="m4 10 4-4 4 4" /></svg>;
export const IDown = () => <svg viewBox="0 0 16 16"><path {...P} d="m4 6 4 4 4-4" /></svg>;
