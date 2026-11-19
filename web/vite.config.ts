import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// The shell links stylesheets and scripts that live in client/static and are not
// renamed on change. Stamping each link with a fingerprint of the file means a
// changed file is fetched again even if a browser or service worker kept the old one.
const fingerprintStatic = () => ({
  name: "fingerprint-static",
  transformIndexHtml: (html: string) =>
    html.replace(/(["'])\/static\/([\w.-]+\.(?:css|js))\1/g, (_m, q: string, name: string) => {
      const hash = createHash("md5").update(readFileSync(resolve(__dirname, "../client/static", name))).digest("hex").slice(0, 10);
      return `${q}/static/${name}?v=${hash}${q}`;
    }),
});

// In development the FastAPI server (port 8000) owns the API, media, static
// files and the server-rendered public pages; Vite serves the React app.
const api = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), fingerprintStatic()],
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
