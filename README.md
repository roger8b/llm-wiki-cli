# llm-wiki

> A local-first, LLM-maintained personal knowledge base — built for engineers
> who think in plain text and want their notes to stay sharp over time.

```
wiki init my-brain
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

### Dev install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[agent,ollama,api,mcp,dev]"
```

---

## Quick start

```bash
# 1. Create a brain
wiki init my-brain
cd my-brain

# 2. Configure the model (edit .llmwiki/config.yaml)
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
├── config.yaml              # global config — model, fts_limit
└── brains/
    └── my-brain/
        ├── metadata.db      # SQLite: pages, sources, jobs, change requests
        └── change_requests/ # staged diffs (JSON) — applied or rejected
```

Config and the database live **outside** the brain repo so they are never
accidentally committed or pushed. All brains on the same machine share a
single `config.yaml`; the database is isolated per brain by directory name.

---

## Configuration

Global config file: **`~/.wiki/config.yaml`**

Created automatically on the first `wiki init`. Edit it to change the model
or search limit for all your brains.

```yaml
model: ollama:llama3.1      # provider:model  (see examples below)
fts_limit: 20               # max full-text search results
```

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

## CLI reference

### Brain management

| Command | Description |
|---------|-------------|
| `wiki init <dir>` | Create a new brain at `<dir>` |
| `wiki index` | Rebuild FTS index + regenerate `wiki/index.md` |
| `wiki log` | Print `wiki/log.md` (applied change history) |

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
| `GET` | `/api/graph` | Page graph (nodes + edges) |
| `GET`/`PATCH` | `/api/config` | Read / update global config |
| `GET` | `/api/brains` | List known brains in `~/.wiki/brains/` |

---

## MCP server

Expose the wiki to Claude Desktop, Cursor, or any MCP-compatible agent:

```bash
wiki mcp          # starts stdio MCP server
```

Available MCP tools:

| Tool | Description |
|------|-------------|
| `wiki_search` | Full-text search the wiki |
| `get_page` | Read a wiki page by path |
| `ask` | Grounded Q&A |
| `ingest` | Ingest a source (creates CR) |
| `lint` | Run structural lint |
| `pending_changes` | List pending change requests |

---

## Evaluation harness

The eval harness runs ingestion against a test corpus and scores output quality.
Useful for tuning prompts or comparing models.

```bash
# Single run
python scripts/eval_ingestion.py --model ollama:gemma4:31b-cloud

# Multiple rounds (measures variance)
python scripts/eval_ingestion.py --rounds 3

# Custom source
python scripts/eval_ingestion.py --source my-doc.md

# Compare last two result files
python scripts/eval_ingestion.py --compare
```

**Scored metrics (weighted composite):**

| Metric | Weight | Description |
|--------|--------|-------------|
| `frontmatter_complete` | 2.0 | All required fields present |
| `has_sources` | 2.0 | At least one source cited |
| `body_substantial` | 2.0 | Body ≥ 200 characters |
| `granularity` | 2.5 | ≥ 5 pages = 100% (encourages concept decomposition) |
| `type_valid` | 1.5 | Valid page type |
| `correct_dir` | 1.5 | Page in correct type directory |
| `has_internal_links` | 1.5 | At least one `[[link]]` |
| `confidence_valid` | 1.0 | Valid confidence value |
| `has_headings` | 1.0 | At least one heading |

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
