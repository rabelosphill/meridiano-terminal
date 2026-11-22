// Cliente HTTP. Usuário de desenvolvimento enviado em X-User (troca pelo seletor no rodapé).
export const USER_KEY = "meridiano.user";
export function currentUser(): string {
  try { return localStorage.getItem(USER_KEY) || "ana"; } catch { return "ana"; }
}

export class ApiError extends Error {
  status: number; detail: any;
  constructor(status: number, detail: any) {
    super(detail?.message || `HTTP ${status}`); this.status = status; this.detail = detail;
  }
}

const memo = new Map<string, { t: number; v: any }>();

export async function api<T = any>(path: string, opts: RequestInit & { cacheMs?: number } = {}): Promise<T> {
  const key = (opts.method || "GET") + path + currentUser();
  if (opts.cacheMs && memo.has(key) && performance.now() - memo.get(key)!.t < opts.cacheMs) return memo.get(key)!.v;
  const r = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", "X-User": currentUser(), ...(opts.headers || {}) } });
  const ct = r.headers.get("content-type") || "";
  const body = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new ApiError(r.status, body?.detail ?? body);
  if (opts.cacheMs) memo.set(key, { t: performance.now(), v: body });
  return body as T;
}
export const post = <T = any>(path: string, body: any) => api<T>(path, { method: "POST", body: JSON.stringify(body) });
export const put = <T = any>(path: string, body: any) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export function clearCache() { memo.clear(); }
