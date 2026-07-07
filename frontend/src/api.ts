// Клиент к backend. Токен подставляется из переданного getter'а.
import { bumpData } from "./refresh";

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

function fetchWithTimeout(
  input: string, init: RequestInit, timeoutMs: number, extSignal?: AbortSignal
): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  // Внешняя отмена (например, кнопка «Стоп» массового импорта) прерывает запрос
  // сразу, не дожидаясь таймаута.
  if (extSignal) {
    if (extSignal.aborted) ctrl.abort();
    else extSignal.addEventListener("abort", () => ctrl.abort(), { once: true });
  }
  return fetch(input, { ...init, signal: ctrl.signal }).finally(() => clearTimeout(timer));
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: unknown; timeoutMs?: number; signal?: AbortSignal } = {}
): Promise<ApiResult<T>> {
  const timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const doFetch = (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = { "Content-Type": "application/json", "X-Lang": langGetter() };
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetchWithTimeout(path, {
      method: opts.method || "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    }, timeoutMs, opts.signal);
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
  // Успешная НЕ-GET операция изменила данные → сигналим для умного обновления
  // (страницы под нами подтянут свежее при возврате, см. refresh.ts / useRevisit).
  if (res.ok && (opts.method || "GET").toUpperCase() !== "GET") bumpData();
  return { ok: res.ok, status: res.status, data };
}

// Понятные запасные сообщения, когда сервер НЕ прислал переведённый текст ошибки
// (обрыв связи / таймаут / 5xx без тела). Локализуем по текущему языку интерфейса,
// чтобы пользователь видел причину, а не «—» или голый код статуса.
const FALLBACK_MSG: Record<string, { net: string; srv: string }> = {
  ru: {
    net: "Нет связи с сервером. Проверьте интернет и попробуйте снова.",
    srv: "Сервер временно недоступен. Попробуйте позже.",
  },
  uz: {
    net: "Server bilan aloqa yoʻq. Internetni tekshirib, qayta urinib koʻring.",
    srv: "Server vaqtincha mavjud emas. Keyinroq urinib koʻring.",
  },
  en: {
    net: "No connection to the server. Check your internet and try again.",
    srv: "The server is temporarily unavailable. Please try again later.",
  },
};

export function errText(data: any, status: number, fallback?: string): string {
  // 1) Сервер прислал переведённый текст ошибки (AppError.detail) — показываем его.
  const d = data?.detail;
  if (typeof d === "string" && d.trim()) return d;
  // 2) Ошибки валидации (422): detail — массив, склеиваем сообщения полей.
  if (Array.isArray(d) && d.length) return d.map((e: any) => e.msg || JSON.stringify(e)).join("; ");
  // 3) Текста ошибки нет: если вызывающий передал свой fallback — берём его,
  //    иначе локализованное «нет связи» (status 0) либо «сервер недоступен».
  if (fallback) return fallback;
  const fb = FALLBACK_MSG[langGetter()] || FALLBACK_MSG.ru;
  return status === 0 ? fb.net : fb.srv;
}

// Загрузка файла (multipart/form-data) — для импорта готовой базы клиента
// (.xlsx/.csv). Content-Type НЕ ставим: браузер сам проставит boundary.
export async function apiUpload<T = any>(
  path: string,
  form: FormData,
  opts: { timeoutMs?: number } = {}
): Promise<ApiResult<T>> {
  const timeoutMs = opts.timeoutMs ?? 60000;
  const doFetch = (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = { "X-Lang": langGetter() };
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetchWithTimeout(path, { method: "POST", headers, body: form }, timeoutMs);
  };
  let res: Response;
  try {
    res = await doFetch(tokenGetter());
  } catch {
    return { ok: false, status: 0, data: null };
  }
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
  if (res.ok) bumpData(); // загрузка файла (импорт базы) меняет данные
  return { ok: res.ok, status: res.status, data };
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
