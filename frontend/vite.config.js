import { defineConfig } from "vite";

// Preserve the browser's Host and Origin as a pair. The API checks them and
// rejects cross-site writes; rewriting Origin here would defeat that check.
const proxy = {
  "/api": {
    target: process.env.COLOR_MIXING_API_TARGET || "http://127.0.0.1:8501",
    changeOrigin: false,
  },
};

export default defineConfig({
  server: { host: "127.0.0.1", port: 5173, strictPort: true, proxy },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy },
  build: { sourcemap: false },
});
