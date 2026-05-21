"""ChangeRequestBackend — backend de filesystem do DeepAgents que captura escritas.

Princípio nuclear: o LLM nunca escreve ``.md`` direto. Este backend subclassa o
``FilesystemBackend`` do DeepAgents e sobrescreve as operações de escrita
(``write``/``edit`` e variantes async) para guardar o conteúdo num *staging* em
memória em vez de gravar no disco. Leituras vêm do disco real, com overlay do
staging (o agente vê o que ele mesmo "escreveu" neste run).

Escritas em ``raw/`` são bloqueadas — segurança no backend, não só no prompt.

Ao final do run, ``collect_changes()`` compara o staging com o disco e devolve a
lista de ``FileChange`` (com diffs) que vira o change request.
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.backends.protocol import EditResult, FileData, ReadResult, WriteResult

from ..core.diff import make_diff
from ..core.models import FileChange

_RAW_PREFIX = "raw/"


class ChangeRequestBackend(FilesystemBackend):
    def __init__(self, brain_root: Path) -> None:
        # virtual_mode=True confina paths ao root (bloqueia '..' e absolutos).
        super().__init__(root_dir=brain_root, virtual_mode=True)
        self.brain_root = Path(brain_root).resolve()
        self.staging: dict[str, str] = {}

    # --- normalização ---------------------------------------------------
    @staticmethod
    def _norm(file_path: str) -> str:
        """Caminho relativo ao brain, com barras POSIX e sem barra inicial."""
        return file_path.lstrip("/")

    def _escapes_root(self, norm: str) -> bool:
        """True se ``norm`` resolve para fora da raiz do brain (path traversal)."""
        resolved = (self.brain_root / norm).resolve()
        return self.brain_root != resolved and self.brain_root not in resolved.parents

    def _disk_content(self, norm: str) -> str | None:
        target = self.brain_root / norm
        if target.is_file():
            return target.read_text(encoding="utf-8")
        return None

    def _current(self, norm: str) -> str | None:
        """Conteúdo atual visível ao agente: staging tem prioridade sobre disco."""
        if norm in self.staging:
            return self.staging[norm]
        return self._disk_content(norm)

    # --- escrita: captura em staging ------------------------------------
    def write(self, file_path: str, content: str) -> WriteResult:
        norm = self._norm(file_path)
        if self._escapes_root(norm):
            return WriteResult(error=f"'{file_path}': caminho fora do brain não é permitido.")
        if norm.startswith(_RAW_PREFIX):
            return WriteResult(error=f"'{file_path}': raw/ é imutável — não pode ser escrito.")
        self.staging[norm] = content
        return WriteResult(path=file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        norm = self._norm(file_path)
        if self._escapes_root(norm):
            return EditResult(error=f"'{file_path}': caminho fora do brain não é permitido.")
        if norm.startswith(_RAW_PREFIX):
            return EditResult(error=f"'{file_path}': raw/ é imutável.")
        current = self._current(norm)
        if current is None:
            return EditResult(error=f"Arquivo '{file_path}' não encontrado.")
        occurrences = current.count(old_string)
        if occurrences == 0:
            return EditResult(error=f"old_string não encontrada em '{file_path}'.")
        if occurrences > 1 and not replace_all:
            return EditResult(
                error=(
                    f"old_string aparece {occurrences} vezes em '{file_path}'. "
                    "Use replace_all=True ou um trecho mais específico."
                )
            )
        count = -1 if replace_all else 1
        self.staging[norm] = current.replace(old_string, new_string, count)
        return EditResult(path=file_path, occurrences=occurrences)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        norm = self._norm(file_path)
        if norm in self.staging:
            lines = self.staging[norm].splitlines(keepends=True)
            window = "".join(lines[offset : offset + limit])
            return ReadResult(file_data=FileData(content=window, encoding="utf-8"))
        return super().read(file_path, offset, limit)

    # --- variantes async: delegam às síncronas --------------------------
    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return self.write(file_path, content)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self.edit(file_path, old_string, new_string, replace_all)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self.read(file_path, offset, limit)

    # --- coleta de mudanças ---------------------------------------------
    def collect_changes(self) -> list[FileChange]:
        """Compara staging com o disco e devolve a lista de FileChange (com diffs)."""
        changes: list[FileChange] = []
        for norm in sorted(self.staging):
            new_content = self.staging[norm]
            old = self._disk_content(norm)
            if old is not None and old == new_content:
                continue  # sem mudança real
            operation = "update" if old is not None else "create"
            changes.append(
                FileChange(
                    path=norm,
                    operation=operation,
                    new_content=new_content,
                    diff=make_diff(old or "", new_content, norm),
                )
            )
        return changes
