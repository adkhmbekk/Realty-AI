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

// Текущий язык интерфейса — шлём его серверу заголовком X-Lang, чтобы ошибки
// приходили на выбранном языке (ru/uz/en).
let langGetter: () => string = () => "ru";

export function setLangGetter(fn: () => string) {
  langGetter = fn;
}

// Обработчик «тихого перелогина». Когда пропуск истёк (сервер отвечает 401),
// мы один раз пытаемся получить свежий пропуск через Telegram и повторить
// запрос — пользователь даже не замечает, что срок действия закончился.
let reauthHandler: () => Promise<string | null> = async () => null;

export function setReauthHandler(fn: () => Promise<string | null>) {
  reauthHandler = fn;
}

// Чтобы при пачке одновременных 401 не дёргать вход много раз — объединяем
// параллельные попытки перелогина в одну.
let reauthInFlight: Promise<string | null> | null = null;

function tryReauth(): Promise<string | null> {
  if (!reauthInFlight) {
    reauthInFlight = reauthHandler().finally(() => {
      reauthInFlight = null;
    });
  }
  return reauthInFlight;
}

// Таймаут запроса: на медленном/зависшем туннеле fetch может висеть вечно,
// подвешивая UI без снятия спиннера (находка M12). Ограничиваем время и
// даём отмену через AbortController.
const DEFAULT_TIMEOUT_MS = 20000;

function fetchWithTimeout(input: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  return fetch(input, { ...init, signal: ctrl.signal }).finally(() => clearTimeout(timer));
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: unknown; timeoutMs?: number } = {}
): Promise<ApiResult<T>> {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const doFetch = (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = { "Content-Type": "application/json", "X-Lang": langGetter() };
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetchWithTimeout(path, {
      method: opts.method || "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    }, timeoutMs);
  };

  let res: Response;
  try {
    res = await doFetch(tokenGetter());
  } catch {
    return { ok: false, status: 0, data: null };
  }
  // Пропуск истёк — один раз пробуем тихо перелогиниться и повторить запрос.
  if (res.status === 401) {
    const fresh = await tryReauth();
    if (fresh) {
      try {
        res = await doFetch(fresh);
      } catch {
        return { ok: false, status: 0, data: null };
      }
    }
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

// Примечание: multipart-загрузка (apiUpload) удалена как мёртвый код —
// фото отправляются как data-URL в JSON через api() (см. downscaleToDataUrl).

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
