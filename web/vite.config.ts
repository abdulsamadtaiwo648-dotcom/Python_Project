import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the FastAPI server (port 8000) owns the API, media, static
// files and the server-rendered public pages; Vite serves the React app.
const api = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": api,
      "/static": api,
      "/media": api,
      "/sw.js": api,
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
