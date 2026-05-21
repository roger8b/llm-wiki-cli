# llm-wiki

> A local-first, LLM-maintained personal knowledge base — built for engineers
> who think in plain text and want their notes to stay sharp over time.

```
llmwiki init my-brain
llmwiki source add docs/architecture.md
llmwiki ingest raw/articles/architecture.md
llmwiki ask "What are the trade-offs of our current auth approach?"
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
1. Creates a dedicated venv at `~/.llmwiki/venv`
2. Installs `llm-wiki[api,mcp,agent,ollama]` and all extras
3. Symlinks `llmwiki` → `~/.local/bin/llmwiki`

Add `~/.local/bin` to your `PATH` if not already there:

```bash
export PATH="$HOME/.local/bin:$PATH"   # add to ~/.zshrc or ~/.bashrc
```

### Custom paths / extras

```bash
LLMWIKI_HOME=~/.config/llmwiki \
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
| `api` | FastAPI review UI + REST API |
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
llmwiki init my-brain
cd my-brain

# 2. Configure the model (edit .llmwiki/config.yaml)
#    Default: ollama:llama3.1
#    Examples: ollama:gemma4:31b-cloud  |  anthropic:claude-sonnet-4-6

# 3. Add a raw source
llmwiki source add ~/articles/rag-overview.md

# 4. Ingest it — the LLM reads the source and proposes wiki pages
llmwiki ingest raw/articles/rag-overview.md

# 5. Review the proposed changes
llmwiki review            # list pending change requests
llmwiki review CR-2026-0001  # see the diffs

# 6. Apply or reject
llmwiki apply CR-2026-0001
# llmwiki reject CR-2026-0001

# 7. Search and query
llmwiki search "retrieval augmented generation"
llmwiki ask "What are the trade-offs of RAG vs fine-tuning?"
```

---

## Brain directory layout

```
my-brain/
├── .llmwiki/
│   ├── config.yaml          # model, fts_limit
│   ├── metadata.db          # SQLite: pages, sources, jobs, change requests
│   └── change_requests/     # staged diffs (JSON) — applied or rejected
├── raw/                     # immutable raw sources (never edited by LLM)
│   ├── articles/
│   ├── books/
│   ├── notes/
│   └── videos/
├── wiki/                    # LLM-written knowledge pages
│   ├── concepts/
│   ├── entities/
│   ├── synthesis/
│   ├── decisions/
│   ├── projects/
│   └── research/
├── schemas/                 # YAML schemas for page types
├── WIKI_PROTOCOL.md         # rules the LLM follows
└── wiki/index.md            # auto-generated wiki map
```

---

## Configuration

`my-brain/.llmwiki/config.yaml`:

```yaml
model: ollama:llama3.1      # provider:model
fts_limit: 20               # max FTS5 search results
```

### Supported model strings

| Provider | Format | Example |
|----------|--------|---------|
| Ollama (local) | `ollama:<model>` | `ollama:qwen2.5:7b` |
| Ollama (cloud) | `ollama:<model>-cloud` | `ollama:gemma4:31b-cloud` |
| Anthropic | `anthropic:<model>` | `anthropic:claude-sonnet-4-6` |
| OpenAI | `openai:<model>` | `openai:gpt-4o` |
| Google | `google:<model>` | `google:gemini-2.0-flash` |

---

## CLI reference

### Brain management

| Command | Description |
|---------|-------------|
| `llmwiki init <dir>` | Create a new brain at `<dir>` |
| `llmwiki index` | Rebuild FTS index + regenerate `wiki/index.md` |
| `llmwiki log` | Print `wiki/log.md` (applied change history) |

### Sources

| Command | Description |
|---------|-------------|
| `llmwiki source add <file>` | Register a raw file into `raw/` |
| `llmwiki source list` | List registered sources and their status |

### Ingestion (LLM-powered)

| Command | Description |
|---------|-------------|
| `llmwiki ingest <path>` | Read source with LLM → create change request |

The LLM reads the source, searches existing pages for context, then writes new
or updated pages. All writes are staged — not applied until you `apply`.

### Change requests

| Command | Description |
|---------|-------------|
| `llmwiki review` | List pending change requests |
| `llmwiki review <CR-id>` | Show full diff for a specific CR |
| `llmwiki apply <CR-id>` | Apply changes: write files, reindex, log |
| `llmwiki reject <CR-id>` | Reject — keeps diff for audit |

### Search & query

| Command | Description |
|---------|-------------|
| `llmwiki search <query>` | Full-text search (FTS5) |
| `llmwiki ask "<question>"` | Grounded Q&A using wiki as source |
| `llmwiki ask "<question>" --save` | Same, and save the answer as a wiki page |

### Quality

| Command | Description |
|---------|-------------|
| `llmwiki lint` | Structural checks (broken links, missing frontmatter) |
| `llmwiki lint --all` | Adds semantic checks via LLM (contradictions, duplicates) |
| `llmwiki maintain` | Run lint + auto-propose fixes as change request |

### Pages

| Command | Description |
|---------|-------------|
| `llmwiki page create "<title>" --type <type>` | Create a page from type template |
| `llmwiki page open <path>` | Print a wiki page |

### Server & integrations

| Command | Description |
|---------|-------------|
| `llmwiki serve` | Start FastAPI review UI on `http://localhost:8000` |
| `llmwiki mcp` | Start MCP server (stdio) for agent integrations |
| `llmwiki jobs` | List background jobs (ingest / lint / query) |

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
these links; broken ones are reported by `llmwiki lint`.

---

## API & Review UI

Start the server:

```bash
llmwiki serve               # default: http://localhost:8000
llmwiki serve --port 9000
```

Endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Review UI (diff viewer) |
| `GET` | `/sources` | List sources |
| `GET` | `/wiki/pages` | List wiki pages |
| `POST` | `/query` | Q&A query |
| `GET` | `/search?q=<query>` | Full-text search |
| `GET` | `/change-requests` | List change requests |
| `POST` | `/change-requests/{id}/apply` | Apply a CR |
| `POST` | `/change-requests/{id}/reject` | Reject a CR |
| `GET` | `/lint` | Run structural lint |
| `GET` | `/graph` | Page graph (nodes + edges) |

---

## MCP server

Expose the wiki to Claude Desktop, Cursor, or any MCP-compatible agent:

```bash
llmwiki mcp          # starts stdio MCP server
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
│   ├── api/        # FastAPI + review UI
│   └── mcp/        # FastMCP server
├── search/         # hybrid search (FTS5 + pluggable embeddings)
└── workers/        # background job runners
```

---

## Uninstall

```bash
./uninstall.sh          # interactive — asks for confirmation
./uninstall.sh --yes    # non-interactive (CI / scripts)
```

What gets removed:
- `~/.llmwiki/venv` — the dedicated Python venv
- `~/.local/bin/llmwiki` — the binary symlink

What is **never** touched:
- Your brain directories (plain Markdown folders you own)
- Shell config files (`~/.zshrc`, `~/.bashrc`)

Custom paths follow the same env vars as `install.sh`:

```bash
LLMWIKI_HOME=~/.config/llmwiki LLMWIKI_BIN=~/.local/bin ./uninstall.sh --yes
```

---

## License

MIT
