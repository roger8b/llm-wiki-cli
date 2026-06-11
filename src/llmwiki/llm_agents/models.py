"""Schemas de saída estruturada dos agentes (canal 2 — metadados/resumo).

O conteúdo das páginas vem pelo ChangeRequestBackend (canal 1); estes modelos
carregam só o resumo da operação.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IngestionResult(BaseModel):
    summary: str = Field(description="Resumo do que a fonte traz e o que mudou na wiki.")
    affected_pages: list[str] = Field(default_factory=list)
    new_pages: list[str] = Field(default_factory=list)


class Citation(BaseModel):
    page: str | None = None
    source: str | None = None
    quote: str | None = None
    # Set by query_service after resolving page/source against the index/raw.
    # Default keeps old history payloads (without the field) loading. (#172)
    invalid: bool = False


class SuggestedPage(BaseModel):
    path: str
    content: str


class QueryResult(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    suggested_page: SuggestedPage | None = None


class LintFindingOut(BaseModel):
    kind: str
    severity: str = "warn"
    message: str
    pages: list[str] = Field(default_factory=list)


class LintReport(BaseModel):
    findings: list[LintFindingOut] = Field(default_factory=list)


class MaintenanceResult(BaseModel):
    summary: str = Field(description="Resumo das correções propostas.")
    fixed: list[str] = Field(default_factory=list)
