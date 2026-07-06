import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy (spec §11.4): the SPA uses relative /api and /storage URLs; the
// dev server forwards both to the backend so relative image_url values work.
// BACKEND_ORIGIN is http://backend:8000 inside compose, http://localhost:8000 otherwise.
const backend = process.env.BACKEND_ORIGIN ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/storage": { target: backend, changeOrigin: true },
    },
  },
});
