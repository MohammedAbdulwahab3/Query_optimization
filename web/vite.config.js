import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api -> the Go API so the frontend can use same-origin paths.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET || "http://localhost:8080",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
