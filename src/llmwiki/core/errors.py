"""Exceções de domínio. Interfaces capturam e traduzem em mensagens ao usuário."""

from __future__ import annotations


class WikiError(Exception):
    """Base de todos os erros de domínio."""


class BrainNotFoundError(WikiError):
    """Nenhum brain encontrado a partir do diretório atual."""


class BrainExistsError(WikiError):
    """Tentativa de inicializar sobre um brain já existente sem --force."""


class PathOutsideBrainError(WikiError):
    """Caminho resolvido cai fora da raiz do brain."""


class PageExistsError(WikiError):
    """Tentativa de criar página que já existe."""


class InvalidFrontmatterError(WikiError):
    """Frontmatter YAML ausente ou inválido onde era obrigatório."""
