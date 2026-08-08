"""Base classes for language adapters.

Each language adapter provides language-specific commands and parsing
for syntax checking, building, testing, linting, and type checking.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vsrs.core.schemas import CheckResult, CheckStatus


@dataclass
class LanguageInfo:
    """Metadata about a language."""

    name: str
    file_extensions: list[str]
    display_name: str = ""
    build_tool: str = ""
    test_framework: str = ""
    linter: str = ""
    type_checker: str = ""


class LanguageAdapter(ABC):
    """Base class for language-specific verification adapters.

    Each adapter provides the commands and parsing logic for:
    - Syntax checking
    - Building/compiling
    - Running tests
    - Linting
    - Type checking

    Adapters are used by the verification runner to run language-appropriate
    checks on patch candidates.
    """

    @property
    @abstractmethod
    def info(self) -> LanguageInfo:
        """Return language metadata."""
        ...

    @abstractmethod
    def detect(self, repo_path: Path) -> bool:
        """Check if this language is used in the repository.

        Args:
            repo_path: Path to the repository root.

        Returns:
            True if the repository contains files of this language.
        """
        ...

    @abstractmethod
    def syntax_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Check that all changed files have valid syntax.

        Args:
            worktree_path: Path to the worktree with patch applied.
            files: List of changed file paths (relative to worktree).
            timeout: Wall-time limit in seconds.

        Returns:
            CheckResult with syntax check outcome.
        """
        ...

    @abstractmethod
    def build(
        self,
        worktree_path: Path,
        timeout: int = 120,
    ) -> CheckResult:
        """Build/compile the project.

        Args:
            worktree_path: Path to the worktree.
            timeout: Wall-time limit in seconds.

        Returns:
            CheckResult with build outcome.
        """
        ...

    @abstractmethod
    def run_tests(
        self,
        worktree_path: Path,
        test_paths: list[str] | None = None,
        timeout: int = 120,
    ) -> CheckResult:
        """Run the test suite.

        Args:
            worktree_path: Path to the worktree.
            test_paths: Specific test files/dirs to run. None = all tests.
            timeout: Wall-time limit in seconds.

        Returns:
            CheckResult with test outcome.
        """
        ...

    def lint(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 60,
    ) -> CheckResult:
        """Run linter on changed files.

        Default implementation returns a skip result. Override for
        languages with a linter.

        Args:
            worktree_path: Path to the worktree.
            files: List of changed file paths.
            timeout: Wall-time limit in seconds.

        Returns:
            CheckResult with lint outcome.
        """
        return CheckResult(
            check_type="lint",
            command=f"{self.info.linter or 'none'}",
            status=CheckStatus.skip,
            error_message=f"No linter configured for {self.info.name}",
        )

    def type_check(
        self,
        worktree_path: Path,
        files: list[str],
        timeout: int = 120,
    ) -> CheckResult:
        """Run type checker on changed files.

        Default implementation returns a skip result. Override for
        languages with a type checker.

        Args:
            worktree_path: Path to the worktree.
            files: List of changed file paths.
            timeout: Wall-time limit in seconds.

        Returns:
            CheckResult with type check outcome.
        """
        return CheckResult(
            check_type="type_check",
            command=f"{self.info.type_checker or 'none'}",
            status=CheckStatus.skip,
            error_message=f"No type checker configured for {self.info.name}",
        )

    def matches_files(self, files: list[str]) -> bool:
        """Check if any of the given files match this language's extensions.

        Args:
            files: List of file paths.

        Returns:
            True if any file has a matching extension.
        """
        extensions = set(self.info.file_extensions)
        return any(
            any(f.endswith(ext) for ext in extensions)
            for f in files
        )

    def filter_files(self, files: list[str]) -> list[str]:
        """Filter a list of files to only those matching this language.

        Args:
            files: List of file paths.

        Returns:
            Filtered list of files belonging to this language.
        """
        extensions = set(self.info.file_extensions)
        return [
            f for f in files
            if any(f.endswith(ext) for ext in extensions)
        ]
