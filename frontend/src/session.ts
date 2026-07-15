// Хранение сессии для НАТИВНОГО приложения (вне Telegram).
//
// В Telegram Mini App токены живут только в памяти: при перезапуске приложение
// заново входит по initData. В нативном приложении initData НЕТ, поэтому сессию
// нужно пережить перезапуск — сохраняем refresh-пропуск и при старте меняем его на
// свежую сессию через /auth/refresh.
//
// На нативной платформе используем @capacitor/preferences (SharedPreferences на
// Android / UserDefaults на iOS); в вебе/Telegram — localStorage. Интерфейс
// асинхронный, потому что Preferences асинхронный.
import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";

export interface StoredSession {
  access: string | null;
  refresh: string | null;
}

const K_ACCESS = "pa_access";
const K_REFRESH = "pa_refresh";

const isNative = () => Capacitor.isNativePlatform();

export async function saveSession(access: string | null, refresh: string | null): Promise<void> {
  try {
    if (isNative()) {
      if (access) await Preferences.set({ key: K_ACCESS, value: access });
      if (refresh) await Preferences.set({ key: K_REFRESH, value: refresh });
      return;
    }
    if (access) localStorage.setItem(K_ACCESS, access);
    if (refresh) localStorage.setItem(K_REFRESH, refresh);
  } catch {
    /* приватный режим / переполнение — не критично, просто не переживём перезапуск */
  }
}

export async function loadSession(): Promise<StoredSession | null> {
  try {
    if (isNative()) {
      const access = (await Preferences.get({ key: K_ACCESS })).value;
      const refresh = (await Preferences.get({ key: K_REFRESH })).value;
      if (!access && !refresh) return null;
      return { access, refresh };
    }
    const access = localStorage.getItem(K_ACCESS);
    const refresh = localStorage.getItem(K_REFRESH);
    if (!access && !refresh) return null;
    return { access, refresh };
  } catch {
    return null;
  }
}

export async function clearSession(): Promise<void> {
  try {
    if (isNative()) {
      await Preferences.remove({ key: K_ACCESS });
      await Preferences.remove({ key: K_REFRESH });
      return;
    }
    localStorage.removeItem(K_ACCESS);
    localStorage.removeItem(K_REFRESH);
  } catch {
    /* noop */
  }
}
