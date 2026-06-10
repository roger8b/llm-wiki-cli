"""Domain exceptions. Interfaces capture and translate them into user-facing messages."""

from __future__ import annotations


class WikiError(Exception):
    """Base class for all domain errors."""


class BrainNotFoundError(WikiError):
    """No brain found starting from the current directory."""


class BrainExistsError(WikiError):
    """Attempted to initialize over an existing brain without --force."""


class PathOutsideBrainError(WikiError):
    """Resolved path falls outside the brain root."""


class PageExistsError(WikiError):
    """Attempted to create a page that already exists."""


class InvalidFrontmatterError(WikiError):
    """Missing or invalid YAML frontmatter where it is required."""


class SourceAlreadyProcessedError(WikiError):
    """Source with this content hash was already ingested and applied.

    Raised before any LLM call so re-ingesting identical content does not waste
    a model invocation or create a duplicate change request. Pass ``force=True``
    to ingest anyway.
    """


class JobCancelledError(WikiError):
    """A running agent job was cancelled cooperatively by the user."""


class ExtractorUnavailableError(WikiError):
    """An extractor's optional dependency is not installed.

    The message instructs the user which extra to install
    (e.g. ``pip install 'llm-wiki[pdf]'``).
    """


class EmptyExtractionError(WikiError):
    """An extractor produced no usable text from the source.

    Raised, for example, for a scanned PDF with no text layer. Prevents an
    empty/garbage source from reaching the LLM. OCR is out of scope.
    """
