"""Resolução de caminhos do brain.

Regras (ver CLAUDE.md / plano §11):
- Nunca hardcode caminhos do brain — sempre derive de uma raiz descoberta.
- Para entrada do usuário: tente o caminho absoluto; se não existir, caia para
  ``brain_root / user_input``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import BrainNotFoundError, PathOutsideBrainError

# Marcadores que identificam a raiz de um brain.
_MARKERS = (".llmwiki", "wiki")


@dataclass(frozen=True)
class BrainPaths:
    """Caminhos canônicos derivados da raiz do brain."""

    root: Path

    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def wiki(self) -> Path:
        return self.root / "wiki"

    @property
    def schemas(self) -> Path:
        return self.root / "schemas"

    @property
    def dot(self) -> Path:
        return self.root / ".llmwiki"

    @property
    def db_path(self) -> Path:
        return self.dot / "metadata.db"

    @property
    def change_requests(self) -> Path:
        return self.dot / "change_requests"

    @property
    def index_path(self) -> Path:
        return self.wiki / "index.md"

    @property
    def log_path(self) -> Path:
        return self.wiki / "log.md"

    def relative(self, target: Path) -> str:
        """Caminho de ``target`` relativo à raiz do brain, com barras POSIX."""
        return target.resolve().relative_to(self.root.resolve()).as_posix()


def find_brain_root(start: Path | None = None) -> Path | None:
    """Sobe a árvore de diretórios procurando um marcador de brain.

    Retorna a raiz ou ``None`` se nenhuma for encontrada.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if any((candidate / marker).is_dir() for marker in _MARKERS):
            return candidate
    return None


def load_brain(start: Path | None = None) -> BrainPaths:
    """Descobre a raiz e devolve ``BrainPaths`` ou levanta ``BrainNotFoundError``."""
    root = find_brain_root(start)
    if root is None:
        raise BrainNotFoundError(
            "Nenhum brain encontrado. Rode 'llmwiki init' primeiro."
        )
    return BrainPaths(root=root)


def resolve_input(user_input: str, brain_root: Path) -> Path:
    """Resolve uma entrada de caminho do usuário.

    Tenta o caminho absoluto/relativo ao cwd; se não existir, cai para
    ``brain_root / user_input``. Garante que o resultado fica dentro do brain.
    """
    direct = Path(user_input).resolve()
    chosen = direct if direct.exists() else (brain_root / user_input).resolve()

    root = brain_root.resolve()
    if root not in (chosen, *chosen.parents):
        raise PathOutsideBrainError(
            f"Caminho '{user_input}' resolve para fora do brain ({chosen})."
        )
    return chosen
