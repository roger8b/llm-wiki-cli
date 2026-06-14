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
  PRIMARY KEY (path, chunk_idx)
);

-- Queryable tag index for tag navigation (#189). Tags are normalised
-- (lowercase, trimmed) so different casings collapse to one. Rebuilt on reindex.
CREATE TABLE IF NOT EXISTS page_tags (
  path TEXT NOT NULL,
  tag  TEXT NOT NULL,
  PRIMARY KEY (path, tag)
);
