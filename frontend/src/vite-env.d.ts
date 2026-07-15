/// <reference types="vite/client" />

// Метка сборки, подставляется Vite (см. vite.config.ts → define).
declare const __BUILD_ID__: string;

interface ImportMetaEnv {
  // Базовый адрес backend для нативной сборки (Capacitor). Пусто/не задано —
  // относительные /api/... (Telegram Mini App на одном origin с бэком).
  readonly VITE_API_BASE?: string;
  // OAuth client_id'ы для нативного входа (вшиваются при сборке приложения).
  // Google: web client id — для Android и возвращаемого aud в id_token; iOS —
  // отдельный. Apple: bundle/service id. Backend проверяет aud по этим же id.
  readonly VITE_GOOGLE_WEB_CLIENT_ID?: string;
  readonly VITE_GOOGLE_IOS_CLIENT_ID?: string;
  readonly VITE_APPLE_CLIENT_ID?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
