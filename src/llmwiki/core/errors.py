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
