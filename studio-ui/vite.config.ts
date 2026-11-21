/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The built UI is served by the Python package, so it is written straight into
// src/phi_guard_studio/static (generated; do not hand-edit).
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../src/phi_guard_studio/static",
    emptyOutDir: true,
    sourcemap: false,
    // No inline <script> or modulepreload polyfill: the CSP forbids inline scripts.
    modulePreload: { polyfill: false },
    assetsInlineLimit: 0,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
