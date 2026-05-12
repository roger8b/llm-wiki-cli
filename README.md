# wiki

CLI for your personal AI-maintained brain — a persistent, compounding knowledge base operated by LLM agents.

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
```

**Manual install (from source):**

```bash
git clone <repo> && cd wiki-cli
npm install && npm run build && npm link
wiki bootstrap ~/brain --git
```

## Mental model

- **One brain per machine.** Created once with `wiki bootstrap` — the CLI ships everything needed, no extra repo to clone.
- **Any project wires to the brain** with `wiki init` — interactive setup that appends wiki rules to existing agent config files and installs skills.
- **All commands work from any directory** — the global brain is always resolved automatically.

## First-time setup

```bash
# 1. install (brain created at ~/brain automatically)
curl -fsSL .../install.sh | bash

# 2. wire a project — run inside any repo
cd ~/code/my-project
wiki init
#    → select which agents (Claude Code, PI, Gemini, Cursor…)
#    → symlink or copy skills
#    → appends wiki rules to existing CLAUDE.md / AGENTS.md / etc.

# 3. from anywhere — add sources and let the agent ingest them
wiki source add ./some-article.md --type article
wiki ingest prepare raw/articles/some-article.md
# agent reads .wiki/cache/ingest-context.md and updates brain pages
wiki ingest commit raw/articles/some-article.md
```

## Commands

```bash
# project setup — interactive, run inside a project repo
wiki init [path] [--wiki <path>] [--force] [-y]
#   -y / --yes: non-interactive, installs claude-code with copy method

# brain creation (run once per machine, default: ~/brain)
wiki bootstrap [path] [--git] [--force] [--no-register]

# global config (~/.llm-wiki/config.json)
wiki config show
wiki config set-root <path>
wiki config clear

# health & introspection
wiki doctor

# sources (work from any directory)
wiki source add <file> --type <type>   # article|book|document|transcript|spec|image|external
wiki source list [--status <status>]
wiki source status <source>

# ingestion (raw → brain pages)
wiki ingest prepare <source>           # writes .wiki/cache/ingest-context.md for the agent
wiki ingest commit  <source>           # validates and flips manifest to ingested

# query
wiki search <query> [--type <type>] [--status <status>]
wiki query prepare <question>          # writes context file for agent to answer
wiki query save <file> --as <type> --title <title>

# maintenance
wiki index rebuild
wiki lint
wiki page new <type> <title>
wiki page validate <path>
wiki links check
wiki log add --type <type> --message <message>
```

## Brain root resolution

The CLI resolves the brain in this order:

1. `$LLM_WIKI_ROOT` env var
2. `wiki_root` in `~/.llm-wiki/config.json` (set by `wiki bootstrap` or `wiki config set-root`)
3. Walk-up search for `wiki.config.yaml` starting from the current directory

Once the global root is set, every command works from any directory.

## Use cases

The brain is a persistent, agent-maintained knowledge base. The CLI handles bookkeeping; an LLM agent (Claude Code, PI, Codex, Cursor, Gemini) reads sources and writes the brain via the installed skills.

### 1. Personal knowledge base

Track psychology, health, goals, self-improvement. Drop journal entries, articles, podcast notes into `raw/`; the agent files them, updates entity pages about people in your life, threads themes across entries.

```bash
wiki source add ~/journal/2026-05-11.md --type document
wiki ingest prepare raw/documents/2026-05-11.md
wiki ingest commit  raw/documents/2026-05-11.md
```

### 2. Deep research over weeks or months

Reading 30 papers on a topic. Each paper becomes a `brain/sources/` page; recurring concepts become `brain/concepts/`; the evolving thesis lives in `brain/synthesis/`. Contradictions surface automatically as new papers contradict old claims.

```bash
wiki source add ./paper-12.pdf --type document
wiki ingest prepare raw/documents/paper-12.pdf
wiki query prepare "Where does this paper disagree with what we have?"
```

### 3. Companion wiki for a book

Read a novel or non-fiction with a brain growing alongside. Characters → `entities/`, themes → `concepts/`, plot threads → `synthesis/`. By chapter 30 you have your own cross-referenced companion.

```bash
wiki source add ./book/chapter-04.md --type book
wiki ingest prepare raw/books/chapter-04.md
```

### 4. Team / project knowledge base

Slack threads, meeting transcripts, customer calls, design docs all ingested. The brain keeps current because the LLM (not a human) does the maintenance. Decisions live under `decisions/`, playbooks under `playbooks/`, comparisons under `comparisons/`.

```bash
cd ~/work/my-product && wiki init
wiki source add ./meetings/2026-05-11-architecture.md --type transcript
```

### 5. Competitive analysis / due diligence

Track competitors over time. Each competitor → `entities/`, each report → `sources/`, each cross-comparison → `comparisons/`. The brain becomes the durable artifact instead of one-shot decks.

```bash
wiki query prepare "How has Competitor X's pricing strategy evolved over the past year?"
wiki query save ./answer.md --as synthesis --title "Competitor X pricing evolution"
```

### 6. Course notes / hobby deep-dive

Lecture notes, practice problems, references, tutorials accumulate. The brain cross-links by topic so review covers connections, not isolated pages.

```bash
wiki source add ./lectures/week-05.md --type document
wiki search "fourier transform" --type concept
```

### 7. Decision log

Architectural choices, hiring rubrics, product principles. `decisions/` captures the *why* and the rejected alternatives. New decisions can `supersedes` old ones — the audit trail is preserved.

```bash
wiki page new decision "Adopt Postgres over MongoDB for new services"
```

### 8. Trip / event planning

Restaurants, neighborhoods, contacts, itineraries, prior trips. Cumulative across years — useful next time you go.

```bash
wiki source add ./trips/lisbon-2026.md --type document
wiki query prepare "Best ramen places in Lisbon based on what we've collected?"
```

### Common workflow

1. **Add a source** — `wiki source add <file> --type <type>`
2. **Prepare ingest** — `wiki ingest prepare <raw-path>` writes a context file the agent reads
3. **Agent updates the brain** — using the `wiki-ingest` skill installed via `wiki init`
4. **Commit** — `wiki ingest commit <raw-path>` validates and flips status to `ingested`
5. **Query** — `wiki query prepare "<question>"` gives the agent candidate pages; agent answers grounded in the brain
6. **Save durable answers** — `wiki query save <file> --as synthesis --title "..."` so answers compound instead of dying in chat
7. **Lint periodically** — `wiki lint` flags broken links, orphan pages, uncited claims, duplicates
8. **Refactor when messy** — agent uses `wiki-refactor` skill to merge, split, deprecate without losing knowledge

Everything is plain Markdown in a Git repo. Obsidian works as a viewer.
