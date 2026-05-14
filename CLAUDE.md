# Claude Code — llm-wiki-cli

## Code Intelligence (GitNexus)

This project is indexed by GitNexus as **llm-wiki-cli** (813 symbols, 876 relationships).

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` first.

### Always do

- **Run impact analysis before editing any symbol.** Before modifying a function, class, or method run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius to the user.
- **Run `gitnexus_detect_changes()` before committing** to verify changes only touch expected symbols.
- **Warn the user** if impact analysis returns HIGH or CRITICAL risk.
- Use `gitnexus_query({query: "concept"})` to explore unfamiliar code instead of grepping.
- Use `gitnexus_context({name: "symbolName"})` for full caller/callee context on a specific symbol.

### Never do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename`.
- NEVER commit without running `gitnexus_detect_changes()`.

---

## Project Overview

TypeScript ESM CLI (`wiki` command) — a persistent, LLM-maintained knowledge base. The CLI manages sources, ingestion, querying, linting, and agent skill installation for a brain directory.

```
src/
├── commands/     # one file per CLI command (bootstrap, ingest, lint, page, project, …)
├── utils/        # pure utilities (paths, misc, agents, global-config, templates-dir)
├── services/     # (reserved for future shared services)
├── validators/   # (reserved for validation logic)
└── index.ts      # commander root — registers all commands
tests/            # vitest unit tests (mirrors src/utils/ structure)
templates/        # brain scaffold files + agent skill definitions
```

---

## Code Conventions

### Language & module system

- TypeScript strict mode (`"strict": true`), `ES2022` target, `ESNext` modules.
- All imports use `.js` extension (ESM interop): `import { foo } from "./bar.js"`.
- Node built-ins always use the `node:` prefix: `import path from "node:path"`.
- No default exports in `src/` — named exports only.

### Imports order

1. Node built-ins (`node:path`, `node:os`, …)
2. Third-party packages
3. Internal `../utils/…` then `../commands/…`

### Error handling in CLI commands

- Use `process.exitCode = 1` (not `process.exit(1)`) so cleanup hooks still run.
- Print errors with `picocolors`: `console.error(pc.red("message"))`.
- Never throw from a command handler — catch and set exit code instead.

### Path resolution

- Always attempt `path.resolve(userInput)` first; fall back to `path.resolve(ctx.root, userInput)` if the absolute path doesn't exist (mirrors `ingestPrepare` / `validatePage` pattern).
- Never hardcode brain paths — always resolve via `loadContext()`.

### Async patterns

- Prefer `async/await` over `.then()` chains.
- Use `p-limit` for bounded parallelism over large file sets (see `lintCmd`).
- Use `Promise.all` + `pLimit(n)` rather than sequential loops when IO-bound.

### Types

- Prefer explicit interfaces over inline object types for anything exported.
- Use `Record<string, unknown>` (not `any`) where shape is dynamic; cast with `as` only after validation.
- Frontmatter values: type as `Record<string, any>` only inside parsing boundaries.

---

## Testing

### Framework & location

- **Vitest** — tests live in `tests/`, named `<module>.test.ts`.
- Import from `src/` directly (no compiled `dist/`): `import { fn } from "../src/utils/foo"`.

### Test structure

```typescript
describe("module name", () => {
  describe("functionName", () => {
    it("should <behaviour> when <condition>", async () => { … });
    it("should reject/throw when <error case>", async () => { … });
  });
});
```

### Isolation

- Each test suite creates its own temp directory: `path.join(os.tmpdir(), "wiki-test-" + Math.random().toString(36).slice(2))`.
- Clean up in `afterAll` / `afterEach` with `fs.remove(tempDir)`.
- Use `vi.spyOn` + `vi.restoreAllMocks()` in `afterEach` — never leave global state mutated.
- Mock `process.env` by copying in `beforeEach` and restoring in `afterEach`.

### Coverage targets (lines / statements / functions ≥ 90%)

- Branch coverage is tracked but not enforced (utility files have many optional-chaining branches that are impractical to exercise fully).
- New utility functions in `src/utils/` must have corresponding tests.
- Command handlers do not need unit tests unless they contain non-trivial logic extractable into a utility.

### Mutation testing (Stryker)

- Runs on PRs only (CI `mutation-test` job).
- Target score ≥ 80% (breaks build), ≥ 90% = green.
- Config: `stryker.conf.json`. Uses `vitest.stryker.config.ts` (reporters: `['default']` — prevents GitHub Actions reporter spam).
- Mutated files: `src/utils/paths.ts`, `src/utils/global-config.ts`.

---

## CI Pipeline

```
push / PR
  └─ lint       (tsc)
       └─ test  (vitest --coverage → badges branch push on main)
            └─ mutation-test  (Stryker — PRs only)
```

- **Node version:** 24 (`NODE_VERSION` env in `ci.yml`).
- Coverage badge is self-hosted: CI writes `coverage.json` to the `badges` branch on every push to `main`; shields.io reads it dynamically.
- PR comments: both coverage and mutation reports upsert (update existing bot comment, never spam).
- `set -o pipefail` is set on the coverage run — threshold failures propagate correctly.

---

## Commit & Branch Conventions

- **Conventional commits:** `feat:`, `fix:`, `perf:`, `refactor:`, `test:`, `chore:`, `docs:`, `ci:`.
- Scope optional but recommended: `fix(ci):`, `feat(commands):`.
- Branch names: `feat/<short-description>`, `fix/<short-description>`, `chore/<topic>`.
- Never commit `coverage/`, `reports/`, `.stryker-tmp/`, `dist/` — all in `.gitignore`.
- Always add `Co-Authored-By: Claude …` trailer when AI-assisted.

---

## Key files quick-reference

| File | Purpose |
|------|---------|
| `src/index.ts` | Commander root — all subcommands registered here |
| `src/commands/project.ts` | `wiki init` — agent detection, skill installation, rule file injection |
| `src/commands/uninstall.ts` | `wiki uninstall` — removes wiki-* skills + rule sections |
| `src/utils/agents.ts` | 54-agent registry with `skillsDir`, `globalSkillsDir`, `ruleFile` |
| `src/utils/paths.ts` | `loadContext()`, `findWikiRoot()`, `WikiConfig` / `WikiContext` types |
| `src/utils/misc.ts` | `sha256()`, `slugify()`, `today()` |
| `templates/` | Brain scaffold (AGENTS.md, WIKI_PROTOCOL.md, schemas, skills) |
| `stryker.conf.json` | Mutation testing config |
| `vitest.config.ts` | Coverage: v8, json-summary reporter, 90% thresholds |
