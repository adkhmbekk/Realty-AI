import type { CapacitorConfig } from "@capacitor/cli";

// Конфигурация нативной обёртки (Android/iOS) вокруг того же веб-приложения, что
// и Telegram Mini App. На Telegram-сборку не влияет (там просто `vite build`).
//
// webDir=dist — Capacitor кладёт собранные ассеты в нативный проект и грузит их
// локально из webview (capacitor://localhost на iOS, https://localhost на Android).
// Backend вызывается по абсолютному адресу VITE_API_BASE (см. api.ts) — кросс-
// ориджин, CORS на бэке уже разрешает эти origin (Фаза 1).
const config: CapacitorConfig = {
  appId: "com.realtyai.app",
  appName: "Realty AI",
  webDir: "dist",
};

export default config;
