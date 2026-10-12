import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, Vite serves the app and forwards API calls to uvicorn on :8000.
// In production FastAPI serves frontend/dist itself, so no proxy is involved.
const API = "http://localhost:8000";

export default defineConfig({
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
});
