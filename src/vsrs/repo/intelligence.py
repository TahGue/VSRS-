"""Repository intelligence facade.

Ties together all indexes (files, symbols, tests, dependencies, git)
into a single interface for the orchestrator. Builds all indexes from
a repository root in one call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.repo.dependencies import DependencyIndex
from vsrs.repo.files import FileEntry, FileIndex
from vsrs.repo.git import GitIndex
from vsrs.repo.retrieval import RetrievedEvidence, RetrievalResult, Retriever
from vsrs.repo.symbols import SymbolEntry, SymbolIndex
from vsrs.repo.tests import ProjectConfig, TestEntry, TestIndex

logger = get_logger("repo.intelligence")


@dataclass
class RepositoryModel:
    """Complete repository model with all indexes built.

    Provides a unified interface to all repository intelligence.
    """

    repo_root: Path
    file_index: FileIndex
    symbol_index: SymbolIndex
    test_index: TestIndex
    dependency_index: DependencyIndex
    git_index: GitIndex
    config: ProjectConfig | None = None
    retriever: Retriever | None = None

    def build_retriever(self) -> Retriever:
        """Build or return the retriever."""
        if self.retriever is None:
            self.retriever = Retriever(
                file_index=self.file_index,
                symbol_index=self.symbol_index,
                test_index=self.test_index,
                dependency_index=self.dependency_index,
                repo_root=self.repo_root,
            )
        return self.retriever


class RepositoryIntelligence:
    """Builds a complete repository model from a repository root.

    Usage:
        intel = RepositoryIntelligence(repo_root)
        model = intel.build()
        result = model.build_retriever().retrieve("Fix auth bug in validate_password")
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def build(self) -> RepositoryModel:
        """Build all indexes and return a complete repository model."""
        logger.info(f"Building repository intelligence for {self.repo_root}")

        # Build file index
        file_index = FileIndex(self.repo_root)
        file_entries = file_index.index()

        # Build symbol index
        symbol_index = SymbolIndex()
        file_data: list[tuple[str, str, str]] = []
        for entry in file_entries:
            try:
                content = (self.repo_root / entry.path).read_text()
                file_data.append((entry.path, content, entry.module))
            except OSError:
                continue
        symbol_index.index_directory(file_data)

        # Build dependency index
        dependency_index = DependencyIndex(self.repo_root)
        for entry in file_entries:
            dependency_index.register_module(entry.module, entry.path)
        for rel_path, content, _ in file_data:
            dependency_index.index_file_imports(rel_path, content)

        # Parse manifests
        pyproject = self.repo_root / "pyproject.toml"
        if pyproject.exists():
            dependency_index.parse_pyproject_toml(pyproject)
        requirements = self.repo_root / "requirements.txt"
        if requirements.exists():
            dependency_index.parse_requirements_txt(requirements)

        # Build test index
        test_index = TestIndex(self.repo_root)
        test_file_data: list[tuple[str, str]] = []
        for rel_path, content, _ in file_data:
            test_file_data.append((rel_path, content))
        test_index.discover_tests(test_file_data)
        config = test_index.discover_config()

        # Build git index
        git_index = GitIndex(self.repo_root)

        model = RepositoryModel(
            repo_root=self.repo_root,
            file_index=file_index,
            symbol_index=symbol_index,
            test_index=test_index,
            dependency_index=dependency_index,
            git_index=git_index,
            config=config,
        )

        logger.info(
            f"Repository model built: {file_index.count} files, "
            f"{symbol_index.count} symbols, {test_index.test_count} tests, "
            f"{dependency_index.import_count} imports, "
            f"{dependency_index.package_count} packages"
        )
        return model
