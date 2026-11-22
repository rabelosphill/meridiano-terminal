// Formatação numérica tabular (pt-BR). Sinal sempre explícito em variações; cor nunca é a única pista.
const nf = (d: number) => new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
const cache: Record<number, Intl.NumberFormat> = {};
export function num(v: number | string | null | undefined, d = 0): string {
  if (v === null || v === undefined || v === "") return "—";
  const x = typeof v === "string" ? Number(v) : v;
  if (!isFinite(x)) return "—";
  cache[d] ||= nf(d);
  const s = cache[d].format(Math.abs(x));
  return x < 0 ? `−${s}` : s;
}
export function scaled(v: string | null | undefined, scale = 6, d = 0): string {
  if (v === null || v === undefined) return "—";
  return num(Number(v) / 10 ** scale, d);
}
export function signed(v: number | string | null | undefined, d = 2, suffix = ""): string {
  if (v === null || v === undefined || v === "") return "—";
  const x = Number(v);
  if (!isFinite(x)) return "—";
  const s = num(Math.abs(x), d) + suffix;
  return x > 0 ? `▲ +${s}` : x < 0 ? `▼ −${s}` : `■ ${s}`;
}
export function dir(v: number | string | null | undefined): "up" | "down" | "flat" {
  const x = Number(v);
  return !isFinite(x) || x === 0 ? "flat" : x > 0 ? "up" : "down";
}
export function pct(v: string | number | null | undefined, d = 1): string {
  if (v === null || v === undefined) return "—";
  return num(Number(v) * 100, d) + "%";
}
export function dt(iso?: string | null, tz?: string): string {
  if (!iso) return "—";
  if (iso.length === 10) return iso.split("-").reverse().join("/");
  const d = new Date(iso);
  return d.toLocaleString("pt-BR", { timeZone: tz, day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
export function timeOnly(iso?: string | null, tz?: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("pt-BR", { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
export const CCY_SYM: Record<string, string> = { BRL: "R$", USD: "US$", EUR: "€" };
