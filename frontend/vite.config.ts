/// <reference types="vitest/config" />
import { defineConfig } from "vite";

// Im Dev-Modus (npm run dev) laufen API und WebSocket auf dem Backend
// unter localhost:8000 - Vite proxied beides transparent weiter.
export default defineConfig({
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        target: process.env.VITE_BACKEND ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: (process.env.VITE_BACKEND ?? "http://localhost:8000").replace("http", "ws"),
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    target: "es2022",
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts"],
  },
});
