import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Во время разработки (npm run dev) запросы к API проксируются на backend.
// В production статику и проксирование берёт на себя Caddy (см. Caddyfile).
export default defineConfig({
  plugins: [react()],
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
