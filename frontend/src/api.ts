// Клиент к backend. Токен подставляется из переданного getter'а.

export interface ApiResult<T = any> {
  ok: boolean;
  status: number;
  data: T | null;
}

let tokenGetter: () => string | null = () => null;

export function setTokenGetter(fn: () => string | null) {
  tokenGetter = fn;
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: unknown } = {}
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = tokenGetter();
  if (token) headers["Authorization"] = "Bearer " + token;
  let res: Response;
  try {
    res = await fetch(path, {
      method: opts.method || "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    return { ok: false, status: 0, data: null };
  }
  let data: any = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  return { ok: res.ok, status: res.status, data };
}

export function errText(data: any, status: number, fallback = "—"): string {
  if (!data) return `${fallback} ${status}`;
  const d = data.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) return d.map((e: any) => e.msg || JSON.stringify(e)).join("; ");
  return "" + status;
}

// Построение query-строки из объекта параметров (массивы повторяются).
export function buildQuery(params: Record<string, unknown>): string {
  const p = new URLSearchParams();
  Object.keys(params).forEach((k) => {
    const v = params[k];
    if (v == null || v === "") return;
    if (Array.isArray(v)) v.forEach((x) => x != null && x !== "" && p.append(k, String(x)));
    else p.set(k, String(v));
  });
  return p.toString();
}
