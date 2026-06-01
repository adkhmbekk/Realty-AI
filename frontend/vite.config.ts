import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Метка сборки (дата и время). Подставляется в код при каждой сборке и
// показывается в Профиле — так сразу видно, что приложение реально обновилось.
const BUILD_ID = new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";

// Во время разработки (npm run dev) запросы к API проксируются на backend.
// В production статику и проксирование берёт на себя Caddy (см. Caddyfile).
export default defineConfig({
  plugins: [react()],
  define: {
    __BUILD_ID__: JSON.stringify(BUILD_ID),
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
