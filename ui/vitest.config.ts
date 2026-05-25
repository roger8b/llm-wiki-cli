import path from "node:path"
import { defineConfig } from "vitest/config"

// Fast in-process unit tests (stores, pure utils). The WebKit end-to-end smoke
// lives under e2e/ and runs via Playwright (npm run test:e2e), not here.
export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    globals: true,
  },
})
