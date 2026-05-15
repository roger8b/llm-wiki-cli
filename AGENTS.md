# Agent Instructions — llm-wiki-cli

TypeScript ESM CLI for the LLM-maintained knowledge base. Read this before making any changes.

---

## Repository Layout

```
src/commands/     CLI command handlers (one file per command)
src/utils/        Pure utility modules — no side effects, fully testable
tests/            Vitest unit tests — mirrors src/utils/ structure
templates/        Brain scaffold files + agent skill definitions
.github/          CI workflow (ci.yml): lint → test → mutation
```

---

## Before Editing Code

This project uses **GitNexus** for code intelligence. Required steps before any edit:

1. Run `gitnexus_impact({target: "symbolName", direction: "upstream"})` — see blast radius.
2. If risk is HIGH or CRITICAL, warn the user before proceeding.
3. After edits, run `gitnexus_detect_changes()` to verify scope.
4. Never rename symbols with find-and-replace — use `gitnexus_rename`.

---

## Code Rules

### TypeScript

- Strict mode, ES2022, ESNext modules. No implicit any.
- All internal imports use `.js` extension: `import { x } from "./foo.js"`.
- Node built-ins: always `node:` prefix — `import path from "node:path"`.
- Named exports only — no default exports in `src/`.
- Prefer explicit `interface` over inline object types for anything exported.

### CLI commands (`src/commands/`)

- Set `process.exitCode = 1` on failure — never `process.exit(1)`.
- Print user-facing errors with `picocolors` (`pc.red`, `pc.yellow`, `pc.green`).
- Catch errors inside command handlers — never let uncaught exceptions reach the user.
- Path inputs: resolve with `path.resolve(input)` first, fall back to `path.resolve(ctx.root, input)` if the path doesn't exist on disk.

### Utilities (`src/utils/`)

- Pure functions — no direct file I/O unless the function's sole purpose is I/O.
- Every new utility must have a test in `tests/<name>.test.ts`.
- Brain paths always resolved via `loadContext()` — never hardcoded.

### Async & concurrency

- `async/await` over `.then()` chains.
- Use `p-limit` for bounded parallelism over file sets (see `lintCmd`).
- `Promise.all` + `pLimit(n)` for IO-bound loops, not sequential `for…of`.

---

## Testing Rules

### Structure

```typescript
describe("module name", () => {
  describe("functionName", () => {
    it("should <expected behaviour>", async () => { … });
    it("should <error case>", async () => { … });
  });
});
```

### Isolation requirements

- Each suite owns a unique temp dir: `path.join(os.tmpdir(), "wiki-<name>-" + randomSuffix)`.
- `afterAll`: clean up with `fs.remove(tempDir)`.
- `beforeEach` / `afterEach`: snapshot and restore `process.env`; call `vi.restoreAllMocks()`.
- Never mutate global state across tests.

### Coverage gates (enforced in CI)

| Metric | Threshold |
|--------|-----------|
| Lines | ≥ 90% |
| Statements | ≥ 90% |
| Functions | ≥ 90% |
| Branches | informational only |

New utilities in `src/utils/` require tests. Command handlers need tests only when they contain extractable logic.

---

## CI

| Job | Trigger | What it does |
|-----|---------|--------------|
| `lint` | every push/PR | `tsc` — type-check only |
| `test` | after lint | vitest + coverage; pushes `coverage.json` to `badges` branch on `main` |
| `mutation-test` | PRs only | Stryker mutation score ≥ 80% required, ≥ 90% green |

- Node 24, `set -o pipefail` on coverage step.
- PR comments (coverage + mutation) **upsert** — never create duplicates.
- Coverage badge: self-hosted via `badges` branch + shields.io endpoint (no external service needed).

---

## Commits

Format: `<type>[optional scope]: <description>`

| Type | When |
|------|------|
| `feat` | new user-facing behaviour |
| `fix` | bug fix |
| `perf` | performance improvement |
| `refactor` | internal restructure, no behaviour change |
| `test` | tests only |
| `ci` | CI / workflow changes |
| `chore` | tooling, deps, config |
| `docs` | documentation only |

- Keep subject line ≤ 72 characters.
- Reference the affected symbol or file in the body when non-obvious.
- Add `Co-Authored-By: Claude …` trailer for AI-assisted commits.

---

## What NOT to do

- Do not edit any symbol without running `gitnexus_impact` first.
- Do not commit `dist/`, `coverage/`, `reports/`, `.stryker-tmp/` — all gitignored.
- Do not use `process.exit()` in command handlers.
- Do not hardcode brain paths — always use `loadContext()`.
- Do not write `any` outside frontmatter parsing boundaries.
- Do not add tests that touch the real brain at `~/brain` — always use temp dirs.
- Do not create new branches from `dist/` or `coverage/` content.
