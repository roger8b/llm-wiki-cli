"""Modelos de domínio (Pydantic v2). Compartilhados por services e interfaces."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SourceStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    processed = "processed"
    error = "error"


class PageType(StrEnum):
    concept = "concept"
    entity = "entity"
    source_summary = "source_summary"
    synthesis = "synthesis"
    decision = "decision"
    project = "project"
    research = "research"


class Confidence(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class Severity(StrEnum):
    info = "info"
    warn = "warn"
    error = "error"


class Source(BaseModel):
    id: int | None = None
    path: str
    type: str
    title: str | None = None
    hash: str
    added_at: datetime
    processed_at: datetime | None = None
    status: SourceStatus = SourceStatus.pending


class Page(BaseModel):
    id: int | None = None
    path: str
    title: str
    type: PageType
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    last_updated_at: datetime
    source_count: int = 0
    confidence: Confidence | None = None


class Link(BaseModel):
    id: int | None = None
    from_page: str
    to_page: str
    link_type: str = "wikilink"


class FileChange(BaseModel):
    path: str
    operation: str  # create|update|delete
    diff: str
    new_content: str | None = None
    # Review aids, derived at capture time (optional / backward-compatible):
    category: str | None = None  # new|edited|removed (review grouping)
    confidence: str | None = None  # low|medium|high, from the page frontmatter
    # Heuristic quality (issue #168): 0–100 score + descriptive flags. None on
    # delete and on change requests created before this field existed.
    quality_score: int | None = None
    quality_flags: list[str] = Field(default_factory=list)


class ChangeRequest(BaseModel):
    id: str
    status: str = "pending_review"
    summary: str | None = None
    files_changed: int = 0
    diff_dir: str
    created_at: datetime
    applied_at: datetime | None = None
    changes: list[FileChange] = Field(default_factory=list)
    # True once a reviewer manually edited a file's content before apply (#183).
    edited_by_reviewer: bool = False


class LintFinding(BaseModel):
    kind: str
    severity: Severity = Severity.warn
    message: str
    pages: list[str] = Field(default_factory=list)
    # Id of a pending change request that already fixes one of ``pages`` (if any).
    related_cr: str | None = None
