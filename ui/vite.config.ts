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
    // Split vendor chunks to keep the main bundle small and avoid the 500KB
    // warning. Each import group below gets its own file in dist/assets/.
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return
          if (id.includes("react") || id.includes("scheduler")) return "vendor-react"
          if (id.includes("zustand")) return "vendor-zustand"
          if (id.includes("react-router") || id.includes("@remix-run")) return "vendor-router"
          if (id.includes("cmdk")) return "vendor-cmdk"
          if (id.includes("radix-ui") || id.includes("@radix-ui")) return "vendor-radix"
          if (id.includes("lucide-react")) return "vendor-icons"
          if (id.includes("sonner")) return "vendor-sonner"
          if (id.includes("react-markdown") || id.includes("remark-") || id.includes("rehype-")) return "vendor-markdown"
          if (id.includes("react-diff-viewer") || id.includes("diff")) return "vendor-diff"
          if (id.includes("tailwindcss") || id.includes("@tailwindcss")) return "vendor-tailwind"
          if (id.includes("class-variance") || id.includes("clsx") || id.includes("tailwind-merge")) return "vendor-utils"
          return "vendor-misc"
        },
      },
    },
  },
})
