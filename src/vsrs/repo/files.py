"""File index: path, language, hash, size, module (Section 6.1).

Indexes all source files in a repository for navigation and change detection.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from vsrs.core.logging import get_logger

logger = get_logger("repo.files")


class Language(str, Enum):
    """Supported programming languages for V1."""

    python = "python"
    unknown = "unknown"


_EXTENSION_MAP: dict[str, Language] = {
    ".py": Language.python,
}

_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__", ".git", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "node_modules", ".venv", "venv", "env", ".tox", ".eggs", "build", "dist",
    ".hg", ".svn", ".idea", ".vscode",
})


@dataclass
class FileEntry:
    """A single indexed file."""

    path: str
    language: Language
    hash: str
    size: int
    module: str

    @property
    def suffix(self) -> str:
        return Path(self.path).suffix


class FileIndex:
    """Index of all source files in a repository."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self._files: dict[str, FileEntry] = {}
        self._by_module: dict[str, list[FileEntry]] = {}

    def index(self) -> list[FileEntry]:
        """Scan the repository and index all source files."""
        self._files.clear()
        self._by_module.clear()

        for path in self._walk_source_files():
            rel = str(path.relative_to(self.repo_root))
            language = _EXTENSION_MAP.get(path.suffix, Language.unknown)
            if language == Language.unknown:
                continue

            try:
                content = path.read_bytes()
            except OSError as e:
                logger.warning(f"Could not read {rel}: {e}")
                continue

            entry = FileEntry(
                path=rel,
                language=language,
                hash=hashlib.sha256(content).hexdigest(),
                size=len(content),
                module=self._path_to_module(rel),
            )
            self._files[rel] = entry
            self._by_module.setdefault(entry.module, []).append(entry)

        logger.info(f"Indexed {len(self._files)} source files in {self.repo_root}")
        return list(self._files.values())

    def _walk_source_files(self) -> list[Path]:
        """Walk the repo and return all source file paths."""
        results: list[Path] = []
        for path in self.repo_root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.relative_to(self.repo_root).parts):
                continue
            if path.suffix in _EXTENSION_MAP:
                results.append(path)
        return results

    def _path_to_module(self, rel_path: str) -> str:
        """Convert a relative file path to a dotted module path."""
        parts = Path(rel_path).with_suffix("").parts
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else rel_path

    def get(self, path: str) -> FileEntry | None:
        """Get a file entry by relative path."""
        return self._files.get(path)

    def all(self) -> list[FileEntry]:
        """Get all file entries."""
        return list(self._files.values())

    def by_language(self, language: Language) -> list[FileEntry]:
        """Get files by language."""
        return [f for f in self._files.values() if f.language == language]

    def by_module(self, module: str) -> list[FileEntry]:
        """Get files by module path."""
        return self._by_module.get(module, [])

    def find_by_name(self, name: str) -> list[FileEntry]:
        """Find files whose path contains the given name."""
        name_lower = name.lower()
        return [f for f in self._files.values() if name_lower in f.path.lower()]

    def has_changed(self, path: str, current_hash: str) -> bool:
        """Check if a file has changed since indexing."""
        entry = self._files.get(path)
        if entry is None:
            return True
        return entry.hash != current_hash

    @property
    def count(self) -> int:
        """Number of indexed files."""
        return len(self._files)
