/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the Vite server proxies API calls to the FastAPI backend on 127.0.0.1:8765.
// `--mode demo` builds the public demo (sample data in the browser) into dist-demo/ for /demo/.
export default defineConfig(({ mode }) => ({
  base: mode === "demo" ? "/demo/" : "/",
  plugins: [react(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/healthz": "http://127.0.0.1:8765",
      "/readyz": "http://127.0.0.1:8765",
    },
  },
  build: { outDir: mode === "demo" ? "dist-demo" : "dist", sourcemap: false },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.tsx", "src/**/*.test.ts"],
    setupFiles: ["src/test-setup.ts"],
  },
}));
