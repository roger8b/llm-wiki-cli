# llm-wiki

> A local-first, LLM-maintained personal knowledge base — built for engineers
> who think in plain text and want their notes to stay sharp over time.

```
wiki brain create my-brain
wiki source add docs/architecture.md
wiki ingest raw/articles/architecture.md
wiki ask "What are the trade-offs of our current auth approach?"
```

---

## What it is

**llm-wiki** is a CLI + API that turns a folder of Markdown files into a
living knowledge base. You feed it raw sources (articles, PDFs, notes, meeting
transcripts). An LLM agent reads them, writes structured wiki pages, and
proposes every change as a **change request** you must review before it touches
your files. Nothing is ever written to disk without your approval.

Key properties:
- **Local-first.** Your data lives in a plain directory. No cloud lock-in.
- **Git-native.** The brain is a git repo. Every applied change is
  diffable and revertable.
- **Human in the loop.** The LLM proposes; you approve (`apply`) or reject.
- **Provider-agnostic.** Works with Ollama (local or cloud), Anthropic, OpenAI,
  and Google — you pick the model.
- **MCP-ready.** Expose the wiki to other agents via the built-in MCP server.

---

## Requirements

| Dependency | Version |
|------------|---------|
| Python     | ≥ 3.12  |
| Git        | any     |
| Ollama (optional) | [ollama.ai](https://ollama.ai) |

---

## Installation

### One-line installer (recommended)

```bash
git clone https://github.com/roger8b/llm-wiki-cli.git
cd llm-wiki-cli
./install.sh
```

The installer:
1. Creates a dedicated venv at `~/.wiki/venv`
2. Installs `llm-wiki[api,mcp,agent,ollama]` and all extras
3. Symlinks `wiki` → `~/.local/bin/wiki`

Add `~/.local/bin` to your `PATH` if not already there:

```bash
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc
```

### Custom paths / extras

```bash
LLMWIKI_HOME=~/.config/wiki \
LLMWIKI_BIN=~/.local/bin \
LLMWIKI_EXTRAS=api,mcp,agent,anthropic \
./install.sh
```

Available extras:

| Extra | Adds |
|-------|------|
| `agent` | DeepAgents + LangGraph (required for LLM features) |
| `ollama` | Ollama model support |
| `anthropic` | Claude (Anthropic) model support |
| `openai` | OpenAI model support |
| `google` | Gemini (Google) model support |
| `api` | FastAPI web UI + REST API |
| `mcp` | MCP server for agent integrations |
| `pdf` | PDF source ingestion |
| `html` | HTML source ingestion (boilerplate removal) |
| `audio` | Audio ingestion — offline transcription (faster-whisper) |

### Desktop app (macOS)

Prefer a clickable app over the CLI? (Apple Silicon only.)

**One-line install** — downloads the latest release, installs it into
`/Applications`, clears the Gatekeeper quarantine flag and launches it:

```bash
curl -fsSL https://raw.githubusercontent.com/roger8b/llm-wiki-cli/main/install-desktop.sh | bash
```

Install a specific version with `VERSION=v2.1.0`, or skip auto-launch with
`NO_LAUNCH=1`.

**Manual install** — download the latest `.dmg` instead:

**[Download latest macOS app →](https://github.com/roger8b/llm-wiki-cli/releases/latest)**

1. Open the `.dmg` and drag **llm-wiki** into Applications.
2. **First launch only:** the app is *not* code-signed (no Apple Developer
   account), so macOS Gatekeeper blocks it. Right-click the app →
   **Open** → **Open**. After that it launches normally.

   If macOS still refuses ("app is damaged"), clear the quarantine flag:

   ```bash
   xattr -cr /Applications/llm-wiki.app
   ```

### Dev install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[agent,ollama,api,mcp,dev]"
```

---

## Quick start

```bash
# 1. Create a brain (scaffolds, registers + activates it — no need to cd in)
wiki brain create my-brain

# 2. Configure the model (edit ~/.wiki/config.yaml — global, shared by all brains)
#    Default: ollama:llama3.1
#    Examples: ollama:gemma4:31b-cloud  |  anthropic:claude-sonnet-4-6

# 3. Add a raw source
wiki source add ~/articles/rag-overview.md

# 4. Ingest it — the LLM reads the source and proposes wiki pages
wiki ingest raw/articles/rag-overview.md

# 5. Review the proposed changes
wiki review                  # list pending change requests
wiki review CR-2026-0001     # see the diffs

# 6. Apply or reject
wiki apply CR-2026-0001
# wiki reject CR-2026-0001

# 7. Search and query
wiki search "retrieval augmented generation"
wiki ask "What are the trade-offs of RAG vs fine-tuning?"
```

---

## Directory layout

### Brain directory (git-tracked)

```
my-brain/
├── .llmwiki/                # brain identity marker (tracked, stays empty)
├── raw/                     # immutable raw sources (never edited by LLM)
│   ├── articles/
│   ├── pdfs/
│   ├── meetings/
│   └── …
├── wiki/                    # LLM-written knowledge pages
│   ├── concepts/
│   ├── entities/
│   ├── synthesis/
│   ├── decisions/
│   ├── projects/
│   └── research/
├── schemas/                 # YAML schemas + page templates
├── WIKI_PROTOCOL.md         # rules the LLM follows
└── wiki/index.md            # auto-generated wiki map
```

### Global data directory (never committed)

```
~/.wiki/
├── config.yaml              # global config — model, brains registry
│                           #   activeBrainId: uuid
│                           #   brains: [{id, name, path, icon, createdAt}, ...]
└── brains/
    └── <uuid>/              # per-brain data, keyed by UUID (not dirname)
        ├── metadata.db      # SQLite: pages, sources, jobs, change requests
        └── change_requests/  # staged diffs (JSON) — applied or rejected
            └── CR-2026-0001/
                ├── meta.json        # summary, changes, + execution telemetry
                └── 000-*.diff       # per-file unified diffs
```

Each change request's **`meta.json`** records how the agent run went, under the
`execution` block — handy for auditing model quality and cost over time:

```json
{
  "id": "CR-2026-0001",
  "summary": "Created RAG concept page",
  "execution": {
    "model": "ollama:llama3.1",
    "tokens_in": 3120,
    "tokens_out": 845,
    "tool_calls": 4,
    "latency_ms": 18342,
    "used_fallback": false
  },
  "changes": [{ "path": "wiki/concepts/rag.md", "operation": "create",
                "category": "new", "confidence": "medium", "diff": "…" }]
}
```

Config lives **outside** the brain repo so it is never accidentally committed
or pushed. All brains share a single `config.yaml`; the database is isolated
per brain by UUID.

---

## Configuration

Global config file: **`~/.wiki/config.yaml`**

Created automatically on the first `wiki brain create`. Edit it to change the model
or search limit for all your brains.

```yaml
model: ollama:llama3.1      # provider:model  (see examples below)
fts_limit: 20               # max full-text search results
num_ctx: 8192               # Ollama context window
temperature: null           # null = provider default
request_timeout: 300        # seconds
agent_max_retries: 2        # agent.invoke attempts on transient errors (1 = no retry)
onboarded: true             # completed first-run setup
providers:                  # per-provider base_url + model (NOT the key)
  openai:
    base_url: https://api.openai.com/v1
    model: gpt-4o
# ── brain registry ────────────────────────────────────────────────────────
activeBrainId: uuid         # ID of the currently active brain
brains:                     # registered brains (created via Settings UI)
  - id: uuid
    name: my-wiki
    path: /Users/roger/wiki/my-wiki
    icon: brain              # Lucide icon name (brain, book, code, briefcase, flask, lightbulb, rocket, folder)
    createdAt: '2026-05-23T10:00:00Z'
```

### Remote providers & secure keys

Configure hosted providers (Anthropic, OpenAI, Google) from **Settings →
Remote providers**: base URL, model, and API key. You can also point at any
OpenAI/Anthropic-compatible endpoint via the base URL (proxies, Azure,
self-hosted gateways).

**API keys are never written to `config.yaml`.** They are stored in your OS
keychain (macOS Keychain / Linux Secret Service / Windows Credential Manager)
via the `keyring` library. Only the non-secret `base_url` and `model` land in
the config file. Reading also falls back to the conventional env vars
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`) if no key is stored.

### Model configuration examples

#### Ollama — local

Requires [Ollama](https://ollama.ai) running on `localhost:11434`.

```yaml
model: ollama:llama3.1
```

```yaml
model: ollama:qwen2.5:7b
```

```yaml
model: ollama:gemma3:12b
```

No API key needed. Pull the model first: `ollama pull qwen2.5:7b`

#### Ollama — cloud (ollama.com)

Hosted models via the Ollama cloud proxy. Append `-cloud` to the model name.

```yaml
model: ollama:gemma4:27b-cloud
```

```yaml
model: ollama:llama4:scout-cloud
```

No local GPU needed. Requires an Ollama account.

#### Anthropic (Claude)

```yaml
model: anthropic:claude-sonnet-4-5
```

```yaml
model: anthropic:claude-opus-4-5
```

```yaml
model: anthropic:claude-haiku-3-5
```

Requires `ANTHROPIC_API_KEY` env var.  
Install extra: `pip install "llm-wiki[anthropic]"`

#### OpenAI

```yaml
model: openai:gpt-4o
```

```yaml
model: openai:gpt-4o-mini
```

```yaml
model: openai:o3-mini
```

Requires `OPENAI_API_KEY` env var.  
Install extra: `pip install "llm-wiki[openai]"`

#### Google (Gemini)

```yaml
model: google:gemini-2.0-flash
```

```yaml
model: google:gemini-2.5-pro
```

Requires `GOOGLE_API_KEY` env var.  
Install extra: `pip install "llm-wiki[google]"`

### Supported model string format

| Provider | Format | Example |
|----------|--------|---------|
| Ollama (local) | `ollama:<model>` | `ollama:qwen2.5:7b` |
| Ollama (cloud) | `ollama:<model>-cloud` | `ollama:gemma4:27b-cloud` |
| Anthropic | `anthropic:<model>` | `anthropic:claude-sonnet-4-5` |
| OpenAI | `openai:<model>` | `openai:gpt-4o` |
| Google | `google:<model>` | `google:gemini-2.0-flash` |

---

## Logs & telemetry

Every agent run records how it went. There are **two ways** to access it:

### 1. Structured telemetry (persisted, queryable)

The richest data is written to disk — no log level needed:

- **Per change request** — the `execution` block in
  `~/.wiki/brains/<uuid>/change_requests/CR-…/meta.json` (model, tokens in/out,
  tool calls, latency, whether the structured-output fallback fired). See the
  example under [Directory layout](#global-data-directory-never-committed).
- **Per job** — the same telemetry is stored in the job `result` (visible via
  `wiki jobs` / the `/api/jobs` endpoint and the desktop app). Long jobs also
  expose a coarse `progress` step and can be **cancelled** cooperatively
  (`POST /api/jobs/{id}/cancel`) — the agent stops at the next step and the job
  ends in the `cancelled` state. Progress/cancel events are pushed over the
  job SSE stream (`/api/jobs/{id}/events`).

```bash
# Inspect the telemetry of the latest change request
cat ~/.wiki/brains/*/change_requests/CR-2026-0001/meta.json | jq .execution
```

### 2. Runtime logs (stderr / file)

Logs go to **stderr** by default. Two environment variables control them:

| Variable | Default | Effect |
|----------|---------|--------|
| `LLMWIKI_LOG_LEVEL` | `WARNING` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`. Use `INFO` to see the per-run telemetry line (`model / tokens / latency / tool_calls / fallback`). |
| `LLMWIKI_LOG_FILE` | _(unset)_ | When set, logs are **also** appended to this file. |

At the default `WARNING` level you already see the important audit events:
structured-output **fallback** (weak model), **write attempts during a read-only
`ask`**, **phantom change requests** (the model promised pages but wrote none),
and declared/written **mismatches**.

```bash
# See the full per-run telemetry line in the terminal
LLMWIKI_LOG_LEVEL=INFO wiki ingest raw/articles/architecture.md

# Persist everything to a file (e.g. for the background worker / API server)
LLMWIKI_LOG_LEVEL=INFO LLMWIKI_LOG_FILE=~/.wiki/wiki.log wiki serve
```

> The background job worker and the API server pick up the same variables — set
> them in the environment before `wiki serve` (or the desktop app launch) to
> capture ingestion/maintenance telemetry from long-running jobs.

---

## CLI reference

### Brain management

One **shared registry** (`~/.wiki/config.yaml`) holds every brain and the
active selection. The CLI, MCP server and web UI all resolve the **same active
brain** — selecting one in any channel is instantly honoured everywhere. You no
longer need to be inside a brain directory to run commands.

| Command | Description |
|---------|-------------|
| `wiki brain list` | List registered brains (✓ active, ⚠ folder missing) |
| `wiki brain current` | Show the active brain |
| `wiki brain use <name\|id\|path>` | Set the active brain (shared with app/MCP) |
| `wiki brain create <path> [--name] [--no-git] [--force]` | Scaffold a new brain, register + activate |
| `wiki brain add <path> [--name]` | Register an existing brain folder |
| `wiki brain rm <name\|id\|path>` | Remove a brain from the registry (keeps files) |
| `wiki init [--brain] [--agents] [--claude] [--remove]` | Write wiki-usage rules into this workspace's `AGENTS.md`/`CLAUDE.md` (teach an agent to use the brain). For creating a brain use `wiki brain create` |
| `wiki skills install \| list \| doctor \| update \| remove` | Install agent skills that operate the brain via the CLI |
| `wiki index` | Rebuild FTS index + regenerate `wiki/index.md` |
| `wiki log` | Print `wiki/log.md` (applied change history) |

The same is exposed in the **Settings UI** (`wiki serve` → Settings → Brains)
and the REST API (`/api/brains*`). If the active brain's folder disappears, the
resolver self-heals to the first valid registered brain.

### Sources

| Command | Description |
|---------|-------------|
| `wiki source add <file>` | Register a raw file into `raw/` |
| `wiki source list` | List registered sources and their status |

### Ingestion (LLM-powered)

| Command | Description |
|---------|-------------|
| `wiki ingest <path>` | Read source with LLM → create change request |

The LLM reads the source, searches existing pages for context, then writes new
or updated pages. All writes are staged — not applied until you `apply`.

### Change requests

| Command | Description |
|---------|-------------|
| `wiki review` | List pending change requests |
| `wiki review <CR-id>` | Show full diff for a specific CR |
| `wiki apply <CR-id>` | Apply changes: write files, reindex, log |
| `wiki reject <CR-id>` | Reject — keeps diff for audit |

### Search & query

| Command | Description |
|---------|-------------|
| `wiki search <query>` | Full-text search (FTS5) |
| `wiki ask "<question>"` | Grounded Q&A using wiki as source |
| `wiki ask "<question>" --save` | Same, and save the answer as a wiki page |

### Quality

| Command | Description |
|---------|-------------|
| `wiki lint` | Structural checks (broken links, missing frontmatter) |
| `wiki lint --all` | Adds semantic checks via LLM (contradictions, duplicates) |
| `wiki maintain` | Run lint + auto-propose fixes as change request |

### Pages

| Command | Description |
|---------|-------------|
| `wiki page create "<title>" --type <type>` | Create a page from type template |
| `wiki page open <path>` | Print a wiki page |

### Server & integrations

| Command | Description |
|---------|-------------|
| `wiki serve` | Start the web UI + REST API on `http://localhost:8000` |
| `wiki mcp` | Start MCP server (stdio) for agent integrations |
| `wiki jobs` | List background jobs (ingest / lint / query) |

---

## Wiki page format

Every wiki page is a Markdown file with YAML frontmatter:

```markdown
---
title: RAG
type: concept
tags: [rag, retrieval, llm]
sources: [raw/articles/rag-overview.md]
updated_at: 2026-05-21
confidence: high
---

# Retrieval-Augmented Generation (RAG)

RAG combines a retrieval system with a generative LLM to produce
grounded, factual answers. See also: [[Vector Store]], [[Embedding Model]].

## Definition
...
```

### Page types

| Type | Directory | Use for |
|------|-----------|---------|
| `concept` | `wiki/concepts/` | Definitions, explanations |
| `entity` | `wiki/entities/` | People, products, companies |
| `source_summary` | `wiki/synthesis/` | Summaries of a single source |
| `synthesis` | `wiki/synthesis/` | Cross-source synthesis |
| `decision` | `wiki/decisions/` | Architecture / design decisions |
| `project` | `wiki/projects/` | Project context and notes |
| `research` | `wiki/research/` | Research questions and findings |

### Internal links

Use `[[Page Title]]` to link between pages. The indexer resolves and tracks
these links; broken ones are reported by `wiki lint`.

---

## Web UI

A full React single-page app ships with the server. Start it and open the
browser:

```bash
wiki serve               # default: http://localhost:8000
wiki serve --port 9000
```

The UI is a local-first companion to the CLI with eight screens:

| Screen | What it does |
|--------|--------------|
| **Review** | Change-request queue + diff viewer; apply/reject with `⌘↵` / `⌘⌫` |
| **Wiki** | Browse pages in a tree; render Markdown with clickable `[[wikilinks]]` |
| **Sources** | List sources, drag-and-drop upload or paste text, trigger ingest |
| **Ask** | Grounded Q&A with sources; optionally save the answer as a page |
| **Graph** | Force-directed knowledge graph; drag nodes, click to open a page |
| **Lint** | Run structural / LLM lint and read findings by severity |
| **Jobs** | Background-job status |
| **Settings** | Edit `~/.wiki/config.yaml` (model picker + presets, FTS limit) |

Press `⌘K` anywhere for the command palette (search pages, sources, CRs, or
jump straight to Ask).

The compiled SPA is embedded in the Python package and served from the same
process as the API — no separate frontend server in production.

### REST API

All JSON endpoints live under the `/api` prefix so they never collide with
client-side SPA routes. Non-API paths fall through to the SPA shell.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sources` | List sources |
| `POST` | `/api/sources/upload` | Upload a file as a source (multipart) |
| `POST` | `/api/sources/text` | Add a source from pasted text |
| `POST` | `/api/sources/ingest` | Ingest a source → creates a CR |
| `GET` | `/api/wiki/pages` | List wiki pages |
| `GET` | `/api/wiki/pages/{path}` | Read a page (frontmatter + body) |
| `POST` | `/api/query` | Grounded Q&A query |
| `GET` | `/api/search?q=<query>` | Full-text search |
| `GET` | `/api/change-requests` | List change requests |
| `GET` | `/api/change-requests/{id}` | Full CR with diffs |
| `POST` | `/api/change-requests/{id}/apply` | Apply a CR |
| `POST` | `/api/change-requests/{id}/reject` | Reject a CR |
| `POST` | `/api/lint` | Run lint (structural or `{semantic:true}`) |
| `GET` | `/api/jobs` / `/api/jobs/{id}` | List jobs / get one (incl. `progress`) |
| `GET` | `/api/jobs/{id}/events` | SSE stream: `status` / `progress` / `result` / `cancelled` |
| `POST` | `/api/jobs/{id}/cancel` | Request cooperative cancellation |
| `GET` | `/api/graph` | Page graph (nodes + edges) |
| `GET`/`PATCH` | `/api/config` | Read / update global config |
| `GET` | `/api/brains` | List registered brains |
| `POST` | `/api/brains` | Register a new brain |
| `GET` | `/api/brains/{id}` | Get a brain by ID |
| `PATCH` | `/api/brains/{id}` | Update brain name / path / icon |
| `DELETE` | `/api/brains/{id}` | Remove a brain |
| `GET` | `/api/brains/active` | Get the active brain |
| `POST` | `/api/brains/active` | Set active brain (`{id}` or `{path}`) |
| `POST` | `/api/brains/{id}/activate` | Activate a specific brain |
| `GET` | `/api/health` | Readiness probe (no brain required) |
| `POST` | `/api/shutdown` | Graceful stop (used by the desktop shell) |

---

## Desktop app (macOS)

The wiki ships a native macOS app built with **Tauri v2** (`ui/src-tauri/`).
The Python backend runs as a **sidecar** on a dynamic port; the WebView points
at it. Because the backend serves both the SPA and `/api` on the same origin,
the React app works unchanged.

```
┌─ Tauri (Rust) ─────────────────────────────┐
│  finds a free port                          │
│  spawns  wiki-backend serve --port <p>      │  ← sidecar
│          --brain ~/.wiki/brains/desktop     │
│  waits until reachable → opens WebView      │
│  kills the sidecar on exit                  │
└─────────────────────────────────────────────┘
```

### Build

> ⚠️ **The desktop app runs a compiled Python backend (the "sidecar"), not your
> working tree.** `tauri build` only rebuilds the SPA — it does **not** recompile
> the sidecar. After changing any Python code you must rebuild the sidecar, or
> the app will keep running the old backend. Use `npm run build:app` (below),
> which chains both, to avoid shipping a stale backend.

```bash
rustup default stable
npm --prefix ui install
cd ui && cargo tauri icon path/to/icon.png # generate icons (once)

# One command: rebuild the sidecar (PyInstaller) THEN the Tauri app.
npm --prefix ui run build:app              # → target/release/bundle/{macos,dmg}/
```

`build:app` runs `build:sidecar` (→ `ui/src-tauri/binaries/wiki-backend-<triple>`)
and then `tauri build`. It uses the project venv at `../.venv` by default;
override with `PYTHON=/path/to/python npm --prefix ui run build:app`.

Output: `llm-wiki.app` and `llm-wiki_<version>_aarch64.dmg`.

**Fast iteration (no rebuild):** run the backend from your venv and the SPA in
dev mode — Vite proxies `/api` → `localhost:8000`, so you hit your working-tree
backend directly:

```bash
.venv/bin/wiki serve            # backend on :8000 (your current code)
npm --prefix ui run dev         # SPA with hot reload → http://localhost:5173
```

### Running without an Apple Developer account

If you don't have a paid Apple Developer account, macOS will block the app from
launching (Gatekeeper quarantine). After copying the app to your Applications
folder, remove the quarantine attribute:

```bash
xattr -cr /Applications/llm-wiki.app
```

On first launch, macOS may still show a "cannot be opened because it is from
an unidentified developer" warning. Control-click the app icon, choose "Open",
and confirm. After the first successful open, the app launches normally from
Launchpad/Spotlight.

### Dev

For fast iteration, skip Tauri and run the web stack directly:

```bash
wiki serve                 # backend on :8000
npm --prefix ui run dev    # frontend on :5173 (hot reload)
```

A dev sidecar wrapper (a shell script that execs the installed `wiki`) can
stand in for the PyInstaller binary while iterating on the Rust shell — see
`ui/src-tauri/README.md`.

### Notes

- **Dynamic port** — never hardcoded; the Rust shell passes `--port` and points
  the WebView at it.
- **Default brain** — auto-created at `wiki serve --brain` on first launch;
  brain data lives at `~/.wiki/brains/<uuid>/`.
- **Graceful exit** — the sidecar is killed on app exit (also exposes
  `POST /api/shutdown`).
- For distribution to other machines, the **PyInstaller** sidecar
  (`scripts/build_sidecar.sh`) is required — it bundles Python + all deps so no
  local install is needed.

---

## MCP server

Expose the wiki to Claude Desktop, Cursor, or any MCP-compatible agent:

```bash
wiki mcp                      # serve the active brain (shared registry)
wiki mcp --brain ~/notes      # activate that brain first (affects app/CLI too)
```

The MCP server follows the **active brain** from the shared registry and picks
up brain switches live (no restart). Configure your MCP client to run `wiki mcp`
— no `cwd` pinning required.

Available MCP tools:

| Tool | Description |
|------|-------------|
| `wiki_search` | Full-text search the wiki |
| `wiki_get_page` | Read a wiki page by path |
| `wiki_list_pages` | List wiki pages |
| `wiki_list_sources` | List sources (raw/) |
| `wiki_ask` | Grounded Q&A with citations |
| `wiki_ingest` | Ingest a source (creates a CR) |
| `wiki_lint` | Run structural lint |
| `wiki_maintain` | Lint + propose fixes as a CR |
| `wiki_pending_changes` | List pending change requests |
| `wiki_apply` / `wiki_reject` | Apply / reject a change request |
| `wiki_list_brains` | List registered brains |
| `wiki_current_brain` | Show the active brain |
| `wiki_use_brain` | Switch the active brain (affects app/CLI too) |

---

## Evaluation harness

`wiki evals run` measures the **ingestion agent** reproducibly: it ingests a
versioned dataset of test sources into a throwaway brain (never touching your
`~/.wiki` or active brain) and scores each case against an `expected.json`.
Run it **before and after** any prompt/model/tool change to catch silent
regressions.

```bash
# Run with the configured model (writes evals/results/<ts>-<model>.json)
wiki evals run

# Machine-readable output (stdout = JSON only; everything else → stderr)
wiki evals run --json

# Use a different dataset, or keep the temp brain for debugging
wiki evals run --dataset path/to/dataset --keep-brain
```

**Dataset** (`tests/evals/dataset/`, versioned): a short single concept, a rich
multi-concept source, a long source (>30k chars, exercises chunking), a
duplicate of the short concept (expects an **edit**, not a new page), and an
entities source. Each `NN-*.md` is paired with `NN-*.expected.json`
(`min_pages`, `max_pages`, `expected_titles_any`, `expected_types`, `must_link`,
`expect_edit`).

**Per-case score (weighted 0–100):**

| Metric | Weight | Description |
|--------|--------|-------------|
| page count in `[min,max]` | 30 | Correct concept decomposition |
| expected title produced | 20 | At least one expected title appears |
| expected types | 15 | Enough pages of each expected type |
| `must_link` satisfied | 15 | Required wikilinks present |
| wikilink resolution | 10 | Fraction of `[[links]]` that resolve |
| frontmatter validity | 10 | Fraction of pages with valid frontmatter |

A case that creates a **duplicate** (when an edit was expected) is hard-capped
at 25. Telemetry (tokens, latency, fallback) comes from `ExecutionMeta`.
Compare two `evals/results/*.json` files to A/B prompts or models. CI exercises
the harness mechanics with a fake runner (no network); real runs are local.

---

## Development

### Backend (Python)

```bash
# Install dev dependencies
pip install -e ".[agent,ollama,api,mcp,dev]"

# Run tests
python -m pytest

# Type checking
python -m mypy src/llmwiki

# Lint
python -m ruff check src/ tests/
```

### Frontend (React UI)

The web UI lives in `ui/` (Vite + React + TypeScript + Tailwind v4 + shadcn/ui).

```bash
cd ui
npm install

# Dev server with hot reload (proxies /api → http://localhost:8000)
npm run dev          # http://localhost:5173  — run `wiki serve` in another shell

# Type-check + lint
npm run build
npx eslint .
```

`npm run build` compiles the SPA straight into
`src/llmwiki/interfaces/api/dist/`, where FastAPI serves it. Rebuild after
UI changes so `wiki serve` picks them up.

Stack: **react-router** (routing) · **zustand** (state) ·
**react-diff-viewer-continued** (diffs) · **react-markdown** + **rehype-highlight**
(page rendering) · **lucide-react** (icons).

### Project structure

```
src/llmwiki/
├── core/           # paths, config, models, frontmatter, markdown parser
├── db/             # SQLite schema, connection, repo layer
├── services/       # business logic (ingest, query, lint, scaffold…)
├── sources/        # source extractors (Markdown, PDF)
├── agents/         # DeepAgents factory, backend, tools, prompts
├── interfaces/
│   ├── cli/        # Typer CLI
│   ├── api/        # FastAPI + SPA (dist/ holds the built UI)
│   └── mcp/        # FastMCP server
├── search/         # hybrid search (FTS5 + pluggable embeddings)
└── workers/        # background job runners

ui/                 # React SPA source (Vite)
├── src/
│   ├── views/      # one file per screen (Review, Wiki, Sources, Ask…)
│   ├── components/ # layout (shell, sidebar, command palette) + shared + ui (shadcn)
│   ├── stores/     # zustand stores (crs, ingest, app)
│   ├── lib/        # api client, diff/format helpers
│   └── types/      # shared TypeScript types
└── vite.config.ts  # dev proxy + build → ../src/llmwiki/interfaces/api/dist
```

---

## Uninstall

```bash
./uninstall.sh          # interactive — asks for confirmation
./uninstall.sh --yes    # non-interactive (CI / scripts)
```

What gets removed:
- `~/.wiki/venv` — the dedicated Python venv
- `~/.local/bin/wiki` — the binary symlink

What is **never** touched:
- Your brain directories (plain Markdown folders you own)
- Shell config files (`~/.zshrc`, `~/.bashrc`)

Custom paths follow the same env vars as `install.sh`:

```bash
LLMWIKI_HOME=~/.config/wiki LLMWIKI_BIN=~/.local/bin ./uninstall.sh --yes
```

---

## License

MIT
