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
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  type         TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'queued',
  payload      TEXT,
  result       TEXT,
  error        TEXT,
  created_at   TEXT NOT NULL,
  completed_at TEXT
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
  created_at        TEXT NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
  path UNINDEXED, title, body, tags
);
