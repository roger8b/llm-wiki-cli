import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { defineConfig, devices } from "@playwright/test"

const here = path.dirname(fileURLToPath(import.meta.url))

// WebKit smoke tests. Playwright's WebKit is the same engine as Tauri's
// macOS/Linux WebView (WKWebView/WebKitGTK), so this catches the WKWebView-only
// regressions Chromium tolerates (e.g. `crossorigin` module-script loading, the
// first-launch lazy-import failure). The SPA is served by the real backend.
const PORT = 8765
const BRAIN = path.join(os.tmpdir(), "llm-wiki-e2e-brain")

// Allow overriding the python entrypoint locally (e.g. WIKI_SERVE=".venv/bin/python -m llmwiki.interfaces.cli.main").
const serve = process.env.WIKI_SERVE ?? "python -m llmwiki.interfaces.cli.main"

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
  },
  projects: [{ name: "webkit", use: { ...devices["Desktop Safari"] } }],
  webServer: {
    command: `${serve} serve --host 127.0.0.1 --port ${PORT} --brain ${BRAIN}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    cwd: path.resolve(here, ".."),
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
})
