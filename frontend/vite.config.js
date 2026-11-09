import { defineConfig } from "vite";
export default defineConfig({
  base: "/studio/",
  build: { outDir: "../src/tts_host/web", emptyOutDir: true },
  server: {
    proxy: {
      "/v1": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
    },
  },
});
