"""sqlite-vec-backed vector store for local semantic search (#169).

Vectors live in a ``vec0`` virtual table whose rowid is shared with the
``page_embeddings`` bookkeeping table (path, chunk_idx, content_hash). The vec0
table is created lazily on the first upsert, when the embedding dimension is
known, so a brain without the ``[semantic]`` extra keeps working untouched.

All methods are no-ops (or return empties) when the sqlite-vec extension could
not be loaded, so search never breaks because of the semantic layer.
"""

from __future__ import annotations

import logging
import sqlite3

from ..db.connection import load_vec_extension

logger = logging.getLogger("llmwiki.search.vector_store")

_VEC_TABLE = "vec_page_embeddings"


class SqliteVecStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.available = load_vec_extension(conn)

    # --- internal helpers ----------------------------------------------
    @staticmethod
    def _serialize(vector: list[float]) -> bytes:
        import sqlite_vec  # type: ignore[import-untyped] # noqa: PLC0415

        return bytes(sqlite_vec.serialize_float32(vector))

    def _vec_table_dim(self) -> int | None:
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (_VEC_TABLE,),
        ).fetchone()
        if row is None:
            return None
        sql = row["sql"]
        # ... float[<dim>] ...
        import re  # noqa: PLC0415

        m = re.search(r"float\[(\d+)\]", sql)
        return int(m.group(1)) if m else None

    def _ensure_table(self, dim: int) -> None:
        existing = self._vec_table_dim()
        if existing == dim:
            return
        if existing is not None and existing != dim:
            # Embedding model (dimension) changed — rebuild from scratch.
            logger.info("embedding dim changed %d->%d; rebuilding vector table", existing, dim)
            self.conn.execute(f"DROP TABLE IF EXISTS {_VEC_TABLE}")
            self.conn.execute("DELETE FROM page_embeddings")
        self.conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {_VEC_TABLE} USING vec0(embedding float[{dim}])"
        )
        self.conn.commit()

    # --- bookkeeping ----------------------------------------------------
    def page_hash(self, path: str) -> str | None:
        """The stored content hash for ``path`` (chunk 0), or None if unindexed."""
        row = self.conn.execute(
            "SELECT content_hash FROM page_embeddings WHERE path=? AND chunk_idx=0",
            (path,),
        ).fetchone()
        return row["content_hash"] if row else None

    def indexed_paths(self) -> set[str]:
        rows = self.conn.execute("SELECT DISTINCT path FROM page_embeddings").fetchall()
        return {r["path"] for r in rows}

    # --- mutations ------------------------------------------------------
    def delete_page(self, path: str) -> None:
        if not self.available:
            return
        rows = self.conn.execute(
            "SELECT rowid FROM page_embeddings WHERE path=?", (path,)
        ).fetchall()
        ids = [r["rowid"] for r in rows]
        if ids and self._vec_table_dim() is not None:
            self.conn.executemany(
                f"DELETE FROM {_VEC_TABLE} WHERE rowid=?", [(i,) for i in ids]
            )
        self.conn.execute("DELETE FROM page_embeddings WHERE path=?", (path,))
        self.conn.commit()

    def replace_page(
        self, path: str, vectors: list[list[float]], content_hash: str
    ) -> None:
        """Replace all chunk vectors for ``path`` (delete + insert)."""
        if not self.available or not vectors:
            return
        self._ensure_table(len(vectors[0]))
        self.delete_page(path)
        for idx, vector in enumerate(vectors):
            cur = self.conn.execute(
                "INSERT INTO page_embeddings (path, chunk_idx, content_hash) VALUES (?, ?, ?)",
                (path, idx, content_hash),
            )
            rowid = cur.lastrowid
            self.conn.execute(
                f"INSERT INTO {_VEC_TABLE} (rowid, embedding) VALUES (?, ?)",
                (rowid, self._serialize(vector)),
            )
        self.conn.commit()

    # --- query (VectorStore protocol) -----------------------------------
    def query(self, vector: list[float], limit: int) -> list[tuple[str, str, float]]:
        """KNN search; aggregates chunks per page (best distance) → (path, title, score).

        ``score`` is the negated best distance (higher = closer). Returns [] when
        the vector layer is unavailable or empty.
        """
        if not self.available or self._vec_table_dim() is None:
            return []
        try:
            rows = self.conn.execute(
                f"""
                SELECT pe.path AS path, v.distance AS distance
                FROM {_VEC_TABLE} v
                JOIN page_embeddings pe ON pe.rowid = v.rowid
                WHERE v.embedding MATCH ? ORDER BY v.distance LIMIT ?
                """,
                (self._serialize(vector), max(limit * 4, limit)),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            logger.warning("semantic query failed, falling back to FTS: %s", exc)
            return []

        best: dict[str, float] = {}
        for r in rows:
            d = float(r["distance"])
            if r["path"] not in best or d < best[r["path"]]:
                best[r["path"]] = d
        ranked = sorted(best.items(), key=lambda kv: kv[1])[:limit]
        titles = self._titles({p for p, _ in ranked})
        return [(p, titles.get(p, p), -d) for p, d in ranked]

    def _titles(self, paths: set[str]) -> dict[str, str]:
        if not paths:
            return {}
        placeholders = ",".join("?" * len(paths))
        rows = self.conn.execute(
            f"SELECT path, title FROM wiki_pages WHERE path IN ({placeholders})",
            tuple(paths),
        ).fetchall()
        return {r["path"]: r["title"] for r in rows}
