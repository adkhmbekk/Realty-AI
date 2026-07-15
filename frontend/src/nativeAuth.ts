// Нативный вход через Google/Apple: получение токена ОТ ПРОВАЙДЕРА.
//
// Здесь только шаг «получить id_token у Google/Apple» через Capacitor-плагин.
// Дальше App шлёт токен на наш backend (/auth/google | /auth/apple), тот проверяет
// подпись/aud и выдаёт наш пропуск (см. App.tsx → nativeSignIn).
//
// Client_id'ы вшиваются при сборке из env (VITE_GOOGLE_WEB_CLIENT_ID и т.п.).
// aud возвращаемого Google id_token = webClientId — backend проверяет по нему.
import { Capacitor } from "@capacitor/core";
import { SocialLogin } from "@capgo/capacitor-social-login";

export type Provider = "google" | "apple";

export interface ProviderToken {
  // Google id_token / Apple identity_token (подписанный провайдером JWT).
  idToken: string;
  // Apple отдаёт имя ТОЛЬКО при первом входе; Google — в profile.
  firstName?: string;
  lastName?: string;
}

// Доступен ли нативный провайдер-вход (только в нативном приложении Capacitor;
// в обычном браузере/Telegram — нет). Экран входа по этому флагу решает, звать ли
// провайдера или показать подсказку.
export function providerAuthAvailable(): boolean {
  return Capacitor.isNativePlatform();
}

let initialized = false;
async function ensureInit(): Promise<void> {
  if (initialized) return;
  // Инициализируем ТОЛЬКО настроенных провайдеров. Apple на Android требует
  // redirectUrl — если его нет, initialize падает целиком (роняя и Google).
  // Поэтому Apple подключаем лишь когда задан VITE_APPLE_CLIENT_ID.
  const opts: Record<string, unknown> = {};
  const gWeb = import.meta.env.VITE_GOOGLE_WEB_CLIENT_ID;
  const gIos = import.meta.env.VITE_GOOGLE_IOS_CLIENT_ID;
  if (gWeb || gIos) {
    opts.google = { webClientId: gWeb, iOSClientId: gIos };
  }
  const appleId = import.meta.env.VITE_APPLE_CLIENT_ID;
  if (appleId) {
    opts.apple = { clientId: appleId, redirectUrl: import.meta.env.VITE_APPLE_REDIRECT_URL || "" };
  }
  await SocialLogin.initialize(opts as never);
  initialized = true;
}

// Получить токен провайдера или null (не нативная платформа / отказ пользователя).
export async function getProviderToken(provider: Provider): Promise<ProviderToken | null> {
  if (!Capacitor.isNativePlatform()) return null;
  await ensureInit();

  if (provider === "google") {
    // БЕЗ scopes: плагин требует правки MainActivity при использовании scopes.
    // Для аутентификации хватает id_token (email/имя — в его claims, бэк их
    // достаёт из проверенного токена).
    const { result } = await SocialLogin.login({
      provider: "google",
      options: {},
    });
    // online-режим (по умолчанию) отдаёт idToken + profile; offline — только код.
    if (result.responseType !== "online" || !result.idToken) return null;
    return {
      idToken: result.idToken,
      firstName: result.profile.givenName ?? undefined,
      lastName: result.profile.familyName ?? undefined,
    };
  }

  const { result } = await SocialLogin.login({
    provider: "apple",
    options: { scopes: ["email", "name"] },
  });
  if (!result.idToken) return null;
  return {
    idToken: result.idToken,
    firstName: result.profile.givenName ?? undefined,
    lastName: result.profile.familyName ?? undefined,
  };
}
