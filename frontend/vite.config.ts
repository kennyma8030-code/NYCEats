import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In dev, Vite serves the app and forwards API calls to uvicorn on :8000.
// In production FastAPI serves frontend/dist itself, so no proxy is involved.
// API_PROXY names another uvicorn, for when :8000 is taken:
//   API_PROXY=http://localhost:8010 npm run dev -- --port 5180
export default defineConfig(({ mode }) => {
  // An empty prefix reads every variable, the shell's included, not only VITE_ ones.
  const API = loadEnv(mode, ".", "").API_PROXY || "http://localhost:8000";
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": API,
        "/healthz": API,
      },
    },
    build: {
      outDir: "dist",
      emptyOutDir: true,
    },
  };
});
