import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local-first desktop frontend. Built output is loaded by the Tauri shell, but
// it also runs in a plain browser against the localhost API for development.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    target: "es2021",
    sourcemap: false,
  },
});
