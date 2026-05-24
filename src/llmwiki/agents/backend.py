"""ChangeRequestBackend — DeepAgents filesystem backend that captures writes.

Core principle: the LLM never writes to ``.md`` files directly. This backend subclasses
the ``FilesystemBackend`` from DeepAgents and overrides write operations
(``write``/``edit`` and async variants) to store content in an in-memory *staging*
area instead of writing to disk. Reads come from the real disk, overlaid with the
staging area (the agent sees what it has "written" in this run).

Writes to ``raw/`` are blocked — security in the backend, not just in the prompt.

At the end of the run, ``collect_changes()`` compares staging with the disk and
returns a list of ``FileChange`` (with diffs) that becomes the change request.
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
        # virtual_mode=True confines paths to root (blocks '..' and absolute paths).
        super().__init__(root_dir=brain_root, virtual_mode=True)
        self.brain_root = Path(brain_root).resolve()
        self.staging: dict[str, str] = {}

    # --- normalization --------------------------------------------------
    @staticmethod
    def _norm(file_path: str) -> str:
        """Relative path to the brain, with POSIX slashes and no leading slash."""
        return file_path.lstrip("/")

    def _escapes_root(self, norm: str) -> bool:
        """True if ``norm`` resolves outside the brain root (path traversal)."""
        resolved = (self.brain_root / norm).resolve()
        return self.brain_root != resolved and self.brain_root not in resolved.parents

    def _disk_content(self, norm: str) -> str | None:
        target = self.brain_root / norm
        if target.is_file():
            return target.read_text(encoding="utf-8")
        return None

    def _current(self, norm: str) -> str | None:
        """Current content visible to the agent: staging has priority over disk."""
        if norm in self.staging:
            return self.staging[norm]
        return self._disk_content(norm)

    # --- write: capture in staging --------------------------------------
    def write(self, file_path: str, content: str) -> WriteResult:
        norm = self._norm(file_path)
        if self._escapes_root(norm):
            return WriteResult(error=f"'{file_path}': path outside the brain is not allowed.")
        if norm.startswith(_RAW_PREFIX):
            return WriteResult(error=f"'{file_path}': raw/ is immutable — cannot be written.")
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
            return EditResult(error=f"'{file_path}': path outside the brain is not allowed.")
        if norm.startswith(_RAW_PREFIX):
            return EditResult(error=f"'{file_path}': raw/ is immutable.")
        current = self._current(norm)
        if current is None:
            return EditResult(error=f"File '{file_path}' not found.")
        occurrences = current.count(old_string)
        if occurrences == 0:
            return EditResult(error=f"old_string not found in '{file_path}'.")
        if occurrences > 1 and not replace_all:
            return EditResult(
                error=(
                    f"old_string appears {occurrences} times in '{file_path}'. "
                    "Use replace_all=True or a more specific snippet."
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

    # --- async variants: delegate to synchronous ones -------------------
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

    # --- collect changes ------------------------------------------------
    def collect_changes(self) -> list[FileChange]:
        """Compares staging with the disk and returns a list of FileChange (with diffs)."""
        changes: list[FileChange] = []
        for norm in sorted(self.staging):
            new_content = self.staging[norm]
            old = self._disk_content(norm)
            if old is not None and old == new_content:
                continue  # no real change
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
