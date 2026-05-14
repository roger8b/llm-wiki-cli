# wiki — LLM-Maintained Knowledge Base CLI

[![CI](https://github.com/roger8b/llm-wiki-cli/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/roger8b/llm-wiki-cli/actions/workflows/ci.yml)
[![npm version](https://img.shields.io/npm/v/llm-wiki.svg)](https://www.npmjs.com/package/llm-wiki)
[![Node.js ≥20](https://img.shields.io/badge/node-%E2%89%A520-brightgreen)](https://nodejs.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Mutation score](https://img.shields.io/badge/mutation%20score-92%25-brightgreen)](#)

A persistent, compounding knowledge base operated by LLM agents. Drop in sources, the agent reads and integrates them; ask questions, the agent answers grounded in your brain.

## The Core Idea

Most RAG systems retrieve relevant chunks at query time — the LLM re-derives knowledge from scratch on every question. Nothing accumulates. Ask a subtle question that requires synthesizing five documents, and the LLM has to find and piece together the relevant fragments every time.

The wiki works differently: the LLM **incrementally builds and maintains a persistent wiki** — a structured, interlinked collection of markdown files. When you add a new source, the LLM reads it, extracts key information, and integrates it into the existing wiki — updating entity pages, revising topic summaries, noting contradictions. The knowledge is compiled once and then *kept current*.

**The wiki is a persistent, compounding artifact.** Cross-references are already there. Contradictions are flagged. Synthesis reflects everything you've read. The wiki gets richer with every source you add and every question you ask.

You never (or rarely) write the wiki yourself. You're in charge of sourcing, exploration, and asking questions. The LLM does the bookkeeping — summarizing, cross-referencing, filing — that makes a knowledge base actually useful over time.

> This pattern is inspired by [Andrej Karpathy's LLM Wiki concept](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f#file-llm-wiki-md).
> This is related to Vannevar Bush's Memex (1945) — a personal, curated knowledge store with associative trails. Bush couldn't solve who does the maintenance. LLMs do it now.

---

## Architecture

```
~/brain/                  Your knowledge base (the "vault")
├── raw/                  Curated source documents (immutable)
├── wiki/                 LLM-generated markdown pages (LLM writes, you read)
├── schemas/              Page templates and conventions
└── .wiki/                Cache, manifests, and reports

~/.wiki-cli/              CLI install + skill source-of-truth
├── (clone of llm-wiki-cli)
└── templates/skills/     Canonical skill definitions (symlinked into agents)
```

Skills do **not** live inside the brain. They live in `~/.wiki-cli/templates/skills/` and are symlinked into each agent's skill dir when you run `wiki init`. Updating the CLI updates the skills automatically.

**Three layers:**

1. **Raw sources** — articles, papers, images, transcripts. Immutable — the LLM reads but never modifies. Your source of truth.

2. **The wiki** — LLM-generated pages: summaries, entity pages, concept pages, comparisons, decisions, synthesis. The LLM creates, updates, and maintains cross-references.

3. **The schema** — `WIKI_PROTOCOL.md` and skills tell the LLM how the wiki is structured, conventions to follow, and workflows for ingest, query, and maintenance.

---

## Why This Works

The tedious part of a knowledge base is not the reading or thinking — it's the bookkeeping. Updating cross-references, keeping summaries current, noting contradictions, maintaining consistency across dozens of pages. Humans abandon wikis because maintenance grows faster than value. LLMs don't get bored, don't forget to update a cross-reference, and can touch 15 files in one pass. The wiki stays maintained because the cost of maintenance is near zero.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/your-org/wiki-cli/main/install.sh | bash
```

The script installs the `wiki` command globally and bootstraps `~/brain` in one step.

**Options:**

```bash
# custom brain location
curl -fsSL .../install.sh | bash -s -- --brain ~/knowledge

# install CLI only, skip brain creation
curl -fsSL .../install.sh | bash -s -- --no-brain

# skip git init inside the brain
curl -fsSL .../install.sh | bash -s -- --no-git

# use existing ~/.wiki-cli/ (skip clone — useful when iterating after pull)
bash install.sh --local

# sync a local checkout into ~/.wiki-cli/ (development iteration)
bash install.sh --local /path/to/llm-wiki-cli --no-brain
```

**Manual install (from source):**

```bash
git clone <repo> ~/.wiki-cli && cd ~/.wiki-cli
npm install && npm run build && npm link
wiki bootstrap ~/brain --git
```

---

## First-Time Setup

```bash
# 1. Install (brain created at ~/brain automatically)
curl -fsSL .../install.sh | bash

# 2. Wire a project — run inside any repo
cd ~/code/my-project
wiki init
#    → lists detected agents on your machine (Claude Code, Cursor, Gemini, PI…)
#    → pre-selects agents that already have wiki skills set up (none on first run)
#    → choose scope: local (project), global (agent home dir), or both
#    → choose method: symlink (recommended) or copy
#    → appends wiki rules to existing CLAUDE.md / AGENTS.md / etc.

# 3. From anywhere — add sources and let the agent ingest them
wiki source add ./some-article.md --type article
wiki ingest prepare raw/articles/some-article.md
# agent reads .wiki/cache/ingest-context.md and updates brain pages
wiki ingest commit raw/articles/some-article.md
```

---

## Commands

### Project Setup

```bash
wiki init [path] [options]
#   --wiki <path>              brain root override
#   --scope <local|global|both>  where to install skills (default: ask)
#   --method <symlink|copy>     installation method (default: ask, symlink recommended)
#   --update                   re-sync existing skills instead of asking
#   --show-all                 show every supported agent (default: only detected)
#   --force                    overwrite even if wiki section already present
#   -y, --yes                  non-interactive (detected agents, local, symlink)

# Remove wiki skills + rule sections from a project (and/or global dirs)
wiki uninstall [path] [options]
#   --scope <local|global|both>  where to remove from
#   --force                    skip confirmation
#   -y, --yes                  remove from all detected (local+global)
```

**Supported agents (54 total, 14 share `.agents/skills/`):**
aider-desk, amp, antigravity, augment, bob, claude-code, cline, codearts-agent,
codebuddy, codemaker, codestudio, codex, command-code, continue, cortex, crush,
cursor, deepagents, devin, dexto, droid, firebender, forgecode, gemini-cli,
github-copilot, goose, hermes-agent, iflow-cli, junie, kilo, kimi-cli, kiro-cli,
kode, mcpjam, mistral-vibe, mux, neovate, openclaw, opencode, openhands, pi,
pochi, qoder, qwen-code, replit, roo, rovodev, tabnine-cli, trae, trae-cn, warp,
windsurf, zencoder, adal.

**Skill installation scopes:**

| Scope    | Where skills go | Use when |
|----------|-----------------|----------|
| `local`  | `<project>/<agent-skills-dir>/wiki-*` | Project-scoped — checks into repo |
| `global` | `<agent home>/skills/wiki-*` (e.g. `~/.claude/skills/`) | Once per machine, applies everywhere |
| `both`   | local + global | Belt and suspenders |

Symlink (default) makes skill updates from `wiki` CLI propagate automatically. Copy creates a static snapshot.

### Brain Creation (run once per machine)

```bash
wiki bootstrap [path] [--git] [--force] [--no-register]

# Global config (~/.llm-wiki/config.json)
wiki config show
wiki config set-root <path>
wiki config clear
```

### Health & Introspection

```bash
wiki doctor          # validate structure, files, and git state
```

### Sources

```bash
wiki source add <file> --type <type>   # article|book|document|transcript|spec|image|external
wiki source list [--status <status>]
wiki source status <source>
```

### Ingestion (raw → wiki pages)

```bash
wiki ingest prepare <source>           # writes .wiki/cache/ingest-context.md for the agent
wiki ingest commit  <source>           # validates and flips manifest to ingested
```

### Query

```bash
wiki search <query> [--type <type>] [--status <status>]
wiki query prepare <question>          # writes context file for agent to answer
wiki query save <file> --as <type> --title <title>
```

### Maintenance

```bash
wiki index rebuild    # rebuild wiki/index.md from frontmatter
wiki lint             # audit: broken links, orphan pages, uncited claims, duplicates
wiki page new <type> <title>
wiki page validate <path>
wiki links check
wiki log add --type <type> --message <message>
```

---

## Brain Root Resolution

The CLI resolves the brain in this order:

1. `$LLM_WIKI_ROOT` env var
2. `wiki_root` in `~/.llm-wiki/config.json` (set by `wiki bootstrap` or `wiki config set-root`)
3. Walk-up search for `wiki.config.yaml` starting from the current directory

Once the global root is set, every command works from any directory.

---

## Common Workflow

1. **Add a source** — `wiki source add <file> --type <type>`
2. **Prepare ingest** — `wiki ingest prepare <raw-path>` writes a context file the agent reads
3. **Agent updates the brain** — using the `wiki-ingest` skill installed via `wiki init`
4. **Commit** — `wiki ingest commit <raw-path>` validates and flips status to `ingested`
5. **Query** — `wiki query prepare "<question>"` gives the agent candidate pages; agent answers grounded in the brain
6. **Save durable answers** — `wiki query save <file> --as synthesis --title "..."` so answers compound instead of dying in chat
7. **Lint periodically** — `wiki lint` flags broken links, orphan pages, uncited claims, duplicates
8. **Refactor when messy** — agent uses `wiki-refactor` skill to merge, split, deprecate without losing knowledge

---

## Use Cases

### Personal Knowledge Base
Track psychology, health, goals, self-improvement. Drop journal entries, articles, podcast notes into `raw/`; the agent files them, updates entity pages about people in your life, threads themes across entries.

### Deep Research
Reading 30 papers on a topic. Each paper becomes a `wiki/sources/` page; recurring concepts become `wiki/concepts/`; the evolving thesis lives in `wiki/synthesis/`. Contradictions surface automatically.

### Book Companion
Read a novel or non-fiction with a brain growing alongside. Characters → `entities/`, themes → `concepts/`, plot threads → `synthesis/`. By chapter 30 you have your own cross-referenced companion.

### Team / Project Knowledge Base
Slack threads, meeting transcripts, customer calls, design docs all ingested. The brain keeps current because the LLM does the maintenance. Decisions live under `decisions/`, playbooks under `playbooks/`.

### Competitive Analysis
Track competitors over time. Each competitor → `entities/`, each report → `sources/`, each cross-comparison → `comparisons/`. The brain becomes the durable artifact instead of one-shot decks.

### Decision Log
Architectural choices, hiring rubrics, product principles. `decisions/` captures the *why* and rejected alternatives. New decisions can `supersedes` old ones — audit trail preserved.

---

## Tips & Tricks

- **Obsidian** works as a viewer/IDE — the wiki is just a git repo of markdown files.
- **Obsidian Web Clipper** converts web articles to markdown. Useful for quickly getting sources into `raw/`.
- **Graph view** shows the shape of your wiki — what's connected, which pages are hubs, which are orphans.
- **Download images locally** (in Obsidian settings) so the LLM can view and reference them directly.
- **Marp** generates slide decks from wiki content.
- **Dataview** runs queries over page frontmatter — dynamic tables and lists from YAML metadata.

---

## Mental Model

- **One brain per machine.** Created once with `wiki bootstrap` — the CLI ships everything needed, no extra repo to clone.
- **Skills live with the CLI, not the brain.** Canonical skill source is `~/.wiki-cli/templates/skills/`. The brain stays pure knowledge.
- **Any project wires to the brain** with `wiki init` — symlinks (or copies) skills into your agent's dir and appends rules to CLAUDE.md / AGENTS.md / etc.
- **Symlink default** means `git pull` on `~/.wiki-cli/` instantly updates every project's skills.
- **All commands work from any directory** — the global brain is always resolved automatically.

Everything is plain Markdown in a Git repo. You get version history, branching, and collaboration for free.
