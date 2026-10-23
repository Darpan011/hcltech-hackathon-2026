import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker, VITE_PROXY_TARGET=http://backend:8000; on a laptop it defaults to localhost.
const target = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": { target, changeOrigin: true } },
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
  },
});
