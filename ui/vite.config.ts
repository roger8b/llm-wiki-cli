import path from "node:path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // FastAPI backend (wiki serve) during development. The backend serves
      // every endpoint under /api, so we forward the prefix as-is.
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // Built SPA is embedded in the Python package and served by `wiki serve`.
    outDir: path.resolve(__dirname, "../src/llmwiki/interfaces/api/dist"),
    emptyOutDir: true,
  },
})
