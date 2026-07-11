PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  path         TEXT NOT NULL UNIQUE,
  type         TEXT NOT NULL,
  title        TEXT,
  hash         TEXT NOT NULL,
  added_at     TEXT NOT NULL,
  processed_at TEXT,
  status       TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS wiki_pages (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  path            TEXT NOT NULL UNIQUE,
  title           TEXT NOT NULL,
  type            TEXT NOT NULL,
  summary         TEXT,
  tags            TEXT,
  last_updated_at TEXT NOT NULL,
  source_count    INTEGER NOT NULL DEFAULT 0,
  confidence      TEXT
);

CREATE TABLE IF NOT EXISTS links (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  from_page TEXT NOT NULL,
  to_page   TEXT NOT NULL,
  link_type TEXT NOT NULL DEFAULT 'wikilink',
  UNIQUE(from_page, to_page, link_type)
);

CREATE TABLE IF NOT EXISTS claims (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  page_path  TEXT NOT NULL,
  claim_text TEXT NOT NULL,
  source_id  INTEGER REFERENCES sources(id) ON DELETE SET NULL,
  confidence TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  type             TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'queued',
  payload          TEXT,
  result           TEXT,
  error            TEXT,
  progress         TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  stream_text      TEXT,
  created_at       TEXT NOT NULL,
  completed_at     TEXT
);

CREATE TABLE IF NOT EXISTS change_requests (
  id            TEXT PRIMARY KEY,
  job_id        INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
  status        TEXT NOT NULL DEFAULT 'pending_review',
  summary       TEXT,
  files_changed INTEGER NOT NULL DEFAULT 0,
  diff_dir      TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  applied_at    TEXT
);

CREATE TABLE IF NOT EXISTS ask_history (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  question          TEXT NOT NULL,
  answer            TEXT NOT NULL,
  citations         TEXT,
  change_request_id TEXT REFERENCES change_requests(id) ON DELETE SET NULL,
  created_at        TEXT NOT NULL,
  conversation_id   TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
  path UNINDEXED, title, body, tags
);

-- Bookkeeping for local semantic search (#169). The vector data itself lives in
-- a sqlite-vec vec0 virtual table created lazily (only when an embedding model
-- is configured), so this schema stays loadable without the sqlite-vec
-- extension. ``rowid`` here is the key shared with the vec0 table.
CREATE TABLE IF NOT EXISTS page_embeddings (
  path         TEXT NOT NULL,
  chunk_idx    INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  -- Short excerpt of the embedded chunk (#354), shown as the search snippet
  -- for semantic hits. NULL on rows indexed before the migration.
  chunk_text   TEXT,
  PRIMARY KEY (path, chunk_idx)
);

-- Queryable tag index for tag navigation (#189). Tags are normalised
-- (lowercase, trimmed) so different casings collapse to one. Rebuilt on reindex.
CREATE TABLE IF NOT EXISTS page_tags (
  path TEXT NOT NULL,
  tag  TEXT NOT NULL,
  PRIMARY KEY (path, tag)
);

-- Small per-brain key/value store for bookkeeping that isn't worth a table of
-- its own (e.g. last_curation_at for the scheduled curator, #41).
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- Append-only event log for a job's live progress (#272). One row per discrete
-- event (step started/ended, tool call, page written, telemetry, warning) so the
-- UI can render a real timeline instead of a single overwritten progress label.
-- ``payload`` holds metadata only (path, tool name, counters) — never the page
-- body — and the SSE endpoint replays rows after the client's last seen id.
CREATE TABLE IF NOT EXISTS job_events (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id  INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  ts      TEXT NOT NULL,
  kind    TEXT NOT NULL,
  payload TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, id);
