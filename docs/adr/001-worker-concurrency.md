# ADR 001 — Worker concurrency (ask parallel to ingest)

Status: **Accepted** (2026-06-14) — implements #140 (epic #159).

## Context

The background `JobWorker` (`src/llmwiki/workers/runner.py`) consumed the job
queue **single-threaded**: it picked the oldest `queued` job, ran it to
completion, then looked for the next. A long ingestion (made longer by #162
multi-pass and #108 batch ingest) therefore blocked every other job — most
painfully `ask`, which is read-mostly and fast. With the desktop app running in
the background (#204) the queue only gets busier.

SQLite is already in `WAL` mode with a `busy_timeout` and a `retry_on_locked`
helper for the `SQLITE_BUSY` variants that bypass the timeout (see
`db/connection.py`). Tools/services each open their own short-lived connection,
so the data layer is already friendly to parallel readers and a single writer.
Cooperative cancellation (#138) and per-job SSE progress (#191) are per-job.

## Measured pain

Reproduced the production setup (the same scenario as
`tests/test_workers/test_worker_concurrency.py`): a worker ingest job with a
fake ~1.5 s LLM call, plus an `ask`. Single-threaded, the ask cannot even start
until the ingest finishes — it waits the **full** ingest duration. Batches make
this linear in the number of sources. The wait is pure head-of-line blocking,
not DB contention.

## Options considered

- **A. Pool of N threads, any job type in parallel.** Highest throughput, but
  two write-heavy agents would run at once: double the provider rate-limit
  pressure and sidecar memory, and two change-request writers contending on the
  DB. Most risk for the least common need (parallel ingests).
- **B. Read/write split.** Read-mostly jobs (`ask`, `lint`) run concurrently in
  a small pool; write jobs (`ingest`, `maintain`) stay **serialized** — never
  two at once. Kills the head-of-line blocking that actually hurts (ask behind
  ingest) while keeping exactly one heavy writer, so provider/memory/DB-write
  pressure is unchanged from today.
- **C. Single-thread + priority queue (ask jumps the line).** Smallest change,
  but an ask still waits for the *current* ingest to finish — multi-pass makes
  that wait long. Doesn't solve the stated problem.

## Decision

**Option B (read/write split).** Best risk/reward: it directly removes the
observed blocking, leaves the heavy-writer profile identical to the proven
single-writer path, and degrades to today's behaviour at `worker_concurrency=1`.

### Risks and how they're handled

- **SQLite write contention** — only one write job runs at a time; reads are
  WAL-concurrent; `busy_timeout` + `retry_on_locked` already cover the residual
  contention with an external CLI writer (existing, tested).
- **Provider rate limits / sidecar memory** — bounded: at most one heavy
  (ingest/maintain) agent at a time, exactly as before. Concurrency only adds
  light read agents.
- **Same brain path written twice** — change requests get unique ids → unique
  diff dirs; jobs only *stage* changes (disk writes happen at apply, which is
  not a job). No two jobs target the same path.
- **CR ordering** — write jobs remain FIFO-serialized, so CR creation order is
  preserved.

## Implementation

- Config `worker_concurrency: int = 1` (`core/config.py`). `1` = the legacy
  single-threaded path, **byte for byte** (the existing suite passes unchanged).
- `> 1` enables a `ThreadPoolExecutor` dispatcher (`runner._poll_concurrent`):
  it marks jobs `running` before submitting (so they're never re-selected), runs
  each job on its **own** connection (`_run_job_threaded`), and skips a `queued`
  write job while another write is in flight — letting a later `ask`/`lint` run
  instead. `_WRITE_TYPES = {"ingest", "maintain"}`.
- Per-job execution is shared (`_run_job`) between both paths, so behaviour and
  telemetry/SSE/cancellation are identical regardless of dispatch mode.

## Verification

- `worker_concurrency=1`: full suite green with no changes.
- `worker_concurrency=2`: integration test asserts an `ask` reaches `done` while
  a long ingest is still `running`, and the ingest then completes cleanly
  (`tests/test_workers/test_worker_concurrency.py::TestReadWriteSplit`).
- Existing WAL contention test (worker job + concurrent CLI ingest) still green.
