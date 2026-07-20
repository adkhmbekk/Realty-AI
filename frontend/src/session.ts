// Хранение сессии для НАТИВНОГО приложения (вне Telegram).
//
// В Telegram Mini App токены живут только в памяти: при перезапуске приложение
// заново входит по initData. В нативном приложении initData НЕТ, поэтому сессию
// нужно пережить перезапуск — сохраняем refresh-пропуск и при старте меняем его на
// свежую сессию через /auth/refresh.
//
// Где храним токены на нативной платформе: @aparajita/capacitor-secure-storage —
// на Android это EncryptedSharedPreferences с мастер-ключом в AndroidKeyStore
// (аппаратно-защищённое хранилище), на iOS — Keychain. Токены (access/refresh)
// больше НЕ лежат в плейнтексте. Раньше использовался @capacitor/preferences
// (обычный SharedPreferences, плейнтекст) — оставляем его ТОЛЬКО для одноразовой
// миграции старых сессий, чтобы уже вошедшие юзеры не разлогинились после
// обновления приложения. В вебе/Telegram — localStorage (нативного Keystore там
// нет, а вход всё равно идёт по initData).
import { SecureStorage } from "@aparajita/capacitor-secure-storage";
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
      if (access) await SecureStorage.setItem(K_ACCESS, access);
      if (refresh) await SecureStorage.setItem(K_REFRESH, refresh);
      return;
    }
    if (access) localStorage.setItem(K_ACCESS, access);
    if (refresh) localStorage.setItem(K_REFRESH, refresh);
  } catch {
    /* приватный режим / переполнение / OS-ошибка Keystore — не критично, просто
       не переживём перезапуск (юзер войдёт заново) */
  }
}

// Одноразовая миграция: старые сессии лежали в @capacitor/preferences (плейнтекст).
// Если в защищённом хранилище пусто, но в Preferences есть токены — переносим их в
// Keystore и вычищаем Preferences. Так обновление приложения не разлогинивает уже
// вошедших, а токены уезжают из плейнтекста навсегда.
async function migrateFromPreferences(): Promise<StoredSession | null> {
  try {
    const access = (await Preferences.get({ key: K_ACCESS })).value;
    const refresh = (await Preferences.get({ key: K_REFRESH })).value;
    if (!access && !refresh) return null;
    if (access) await SecureStorage.setItem(K_ACCESS, access);
    if (refresh) await SecureStorage.setItem(K_REFRESH, refresh);
    await Preferences.remove({ key: K_ACCESS });
    await Preferences.remove({ key: K_REFRESH });
    return { access, refresh };
  } catch {
    return null;
  }
}

export async function loadSession(): Promise<StoredSession | null> {
  try {
    if (isNative()) {
      const access = await SecureStorage.getItem(K_ACCESS);
      const refresh = await SecureStorage.getItem(K_REFRESH);
      if (!access && !refresh) {
        // Возможно, это первый запуск после обновления — токены ещё в старом
        // (плейнтекст) хранилище. Переносим их в Keystore.
        return await migrateFromPreferences();
      }
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
      // Чистим и защищённое хранилище, и старое (вдруг остались недомигрированные).
      await SecureStorage.removeItem(K_ACCESS).catch(() => {});
      await SecureStorage.removeItem(K_REFRESH).catch(() => {});
      await Preferences.remove({ key: K_ACCESS }).catch(() => {});
      await Preferences.remove({ key: K_REFRESH }).catch(() => {});
      return;
    }
    localStorage.removeItem(K_ACCESS);
    localStorage.removeItem(K_REFRESH);
  } catch {
    /* noop */
  }
}
