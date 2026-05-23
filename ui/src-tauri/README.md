# llm-wiki desktop (Tauri v2)

Wraps the wiki into a native macOS app. The Python backend (`wiki serve`) runs
as a **sidecar** on a dynamic port; the WebView points at it. The backend
serves both the SPA and the `/api` routes on the same origin, so the React
app works unchanged.

```
┌─ Tauri (Rust) ─────────────────────────────┐
│  • finds a free port                        │
│  • spawns  wiki-backend serve --port <p>    │  ← PyInstaller binary
│            --brain ~/.wiki/brains/desktop   │
│  • waits until the port is reachable        │
│  • opens WebView → http://127.0.0.1:<p>     │
│  • kills the sidecar on exit                │
└─────────────────────────────────────────────┘
```

## Prerequisites

```bash
rustup default stable          # Rust toolchain
cargo install tauri-cli --version "^2"   # Tauri CLI (or: npm i -g @tauri-apps/cli)
```

## Build

```bash
# 1. Build the SPA (into ../../src/llmwiki/interfaces/api/dist)
cd ui && npm run build

# 2. Compile the Python backend into a sidecar binary
./scripts/build_sidecar.sh     # → ui/src-tauri/binaries/wiki-backend-<triple>

# 3. Generate app icons (once)
cd ui && cargo tauri icon path/to/icon.png

# 4. Build the macOS app + dmg
cd ui && cargo tauri build      # → ui/src-tauri/target/release/bundle/
```

## Dev

```bash
cd ui && cargo tauri dev        # hot-reloads the Rust shell
```

(For pure UI iteration prefer `npm run dev` + `wiki serve` — much faster.)

## Notes

- **Dynamic port** — never hardcoded; the Rust shell passes `--port` to the
  sidecar and points the WebView at it.
- **Default brain** — `~/.wiki/brains/desktop`, auto-created on first launch by
  `wiki serve --brain` (which inits the brain if missing).
- **Graceful exit** — the sidecar child is killed on app exit; the backend also
  exposes `POST /api/shutdown`.
- **Sidecar packaging** — `build_sidecar.sh` uses PyInstaller `--onedir`
  (faster startup than `--onefile`); the deps live next to the binary.
