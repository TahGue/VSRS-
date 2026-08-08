"""Retrieval: exact/structural first, semantic fallback (Section 6.2).

Task-driven evidence retrieval from repository indexes. Ranks current
repository code and tests above external examples. Records what evidence
was shown to the model for reproducibility.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.repo.dependencies import DependencyIndex, ImportEdge
from vsrs.repo.files import FileEntry, FileIndex
from vsrs.repo.symbols import SymbolEntry, SymbolIndex
from vsrs.repo.tests import TestEntry, TestIndex

logger = get_logger("repo.retrieval")


@dataclass
class RetrievedEvidence:
    """A single piece of retrieved evidence with its source locator."""

    kind: str  # "symbol", "file", "test", "import", "config", "git"
    locator: str  # file:line or symbol qualified name
    content: str
    source: str  # which index produced this
    rank: int = 0  # lower is more relevant
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    """Result of a retrieval operation."""

    query: str
    evidence: list[RetrievedEvidence] = field(default_factory=list)
    expanded: bool = False  # whether one-hop expansion was done

    def all_locators(self) -> list[str]:
        """Get all evidence locators."""
        return [e.locator for e in self.evidence]


class Retriever:
    """Task-driven evidence retrieval from repository indexes.

    Implements the retrieval policy from Section 6.2:
    1. Start from task entities: filenames, symbols, error messages, etc.
    2. Retrieve exact structural matches first; use semantic search second.
    3. Expand one hop through imports, callers/callees, tests and config.
    4. Rank current repository code and tests above external examples.
    5. Retrieve additional evidence only when a hypothesis or verification
       failure creates a concrete question.
    6. Record what evidence was actually shown to the model.
    """

    def __init__(
        self,
        file_index: FileIndex,
        symbol_index: SymbolIndex,
        test_index: TestIndex,
        dependency_index: DependencyIndex,
        repo_root: Path,
    ) -> None:
        self.file_index = file_index
        self.symbol_index = symbol_index
        self.test_index = test_index
        self.dependency_index = dependency_index
        self.repo_root = repo_root

    def retrieve(
        self,
        query: str,
        entities: list[str] | None = None,
        expand: bool = True,
        max_results: int = 50,
    ) -> RetrievalResult:
        """Retrieve evidence for a task query.

        Args:
            query: Natural language task description.
            entities: Explicit entity names to search for (symbols, files, etc.).
            expand: Whether to do one-hop expansion through imports/tests.
            max_results: Maximum number of evidence items to return.

        Returns:
            RetrievalResult with ranked evidence.
        """
        entities = entities or self._extract_entities(query)
        result = RetrievalResult(query=query)

        # Step 1: Exact structural matches
        for entity in entities:
            self._retrieve_exact(entity, result)

        # Step 2: File name matches
        for entity in entities:
            self._retrieve_files(entity, result)

        # Step 3: Test matches
        for entity in entities:
            self._retrieve_tests(entity, result)

        # Step 4: One-hop expansion
        if expand:
            self._expand_one_hop(result)
            result.expanded = True

        # Step 5: Rank and limit
        result.evidence.sort(key=lambda e: e.rank)
        result.evidence = result.evidence[:max_results]

        logger.info(f"Retrieved {len(result.evidence)} evidence items for query: {query[:80]}")
        return result

    def _extract_entities(self, query: str) -> list[str]:
        """Extract entity names from a natural language query.

        Looks for:
        - File paths (e.g., src/auth.py)
        - Symbol names (camelCase, snake_case identifiers)
        - Function/method names mentioned after keywords
        """
        import re

        entities: list[str] = []

        # File paths
        file_patterns = re.findall(r'[\w/]+\.\w+', query)
        entities.extend(file_patterns)

        # Identifiers (snake_case or camelCase, 3+ chars)
        identifiers = re.findall(r'\b[a-z_][a-z0-9_]{2,}\b', query.lower())
        # Filter common words
        stop_words = {"the", "and", "for", "that", "this", "with", "from", "should",
                       "must", "will", "been", "have", "has", "was", "were", "are",
                       "not", "but", "all", "add", "fix", "new", "old", "use"}
        entities.extend(w for w in identifiers if w not in stop_words)

        # CamelCase identifiers
        camel = re.findall(r'\b[A-Z][a-zA-Z0-9]{2,}\b', query)
        entities.extend(camel)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for e in entities:
            if e.lower() not in seen:
                seen.add(e.lower())
                unique.append(e)

        return unique

    def _retrieve_exact(self, entity: str, result: RetrievalResult) -> None:
        """Retrieve exact structural matches for an entity."""
        # Try symbol index
        symbols = self.symbol_index.find_by_name(entity)
        for sym in symbols:
            content = self._read_symbol_content(sym)
            result.evidence.append(RetrievedEvidence(
                kind="symbol",
                locator=f"{sym.file}:{sym.start_line}",
                content=content,
                source="symbol_index",
                rank=1,
                metadata={
                    "name": sym.name,
                    "kind": sym.kind.value,
                    "qualified_name": sym.qualified_name,
                    "signature": sym.signature,
                },
            ))

        # Fuzzy search if no exact matches
        if not symbols:
            fuzzy = self.symbol_index.fuzzy_search(entity, limit=5)
            for sym in fuzzy:
                content = self._read_symbol_content(sym)
                result.evidence.append(RetrievedEvidence(
                    kind="symbol",
                    locator=f"{sym.file}:{sym.start_line}",
                    content=content,
                    source="symbol_index_fuzzy",
                    rank=3,
                    metadata={
                        "name": sym.name,
                        "kind": sym.kind.value,
                        "qualified_name": sym.qualified_name,
                    },
                ))

    def _retrieve_files(self, entity: str, result: RetrievalResult) -> None:
        """Retrieve file matches for an entity."""
        # If entity looks like a file path
        if "." in entity and "/" in entity:
            entry = self.file_index.get(entity)
            if entry:
                content = self._read_file(entry.path)
                result.evidence.append(RetrievedEvidence(
                    kind="file",
                    locator=entry.path,
                    content=content[:5000],  # limit size
                    source="file_index",
                    rank=2,
                    metadata={"module": entry.module, "size": str(entry.size)},
                ))
                return

        # Search by name
        matches = self.file_index.find_by_name(entity)
        for entry in matches[:3]:
            content = self._read_file(entry.path)
            result.evidence.append(RetrievedEvidence(
                kind="file",
                locator=entry.path,
                content=content[:5000],
                source="file_index_name",
                rank=4,
                metadata={"module": entry.module},
            ))

    def _retrieve_tests(self, entity: str, result: RetrievalResult) -> None:
        """Retrieve test matches for an entity."""
        # Tests targeting this module
        tests = self.test_index.tests_for_module(entity)
        for test in tests:
            content = self._read_test_content(test)
            result.evidence.append(RetrievedEvidence(
                kind="test",
                locator=f"{test.file}:{test.start_line}",
                content=content,
                source="test_index",
                rank=2,
                metadata={
                    "name": test.name,
                    "target_module": test.target_module,
                    "test_type": test.test_type,
                },
            ))

        # Tests with matching name
        test = self.test_index.find_by_name(entity)
        if test:
            content = self._read_test_content(test)
            result.evidence.append(RetrievedEvidence(
                kind="test",
                locator=f"{test.file}:{test.start_line}",
                content=content,
                source="test_index_name",
                rank=2,
                metadata={"name": test.name},
            ))

    def _expand_one_hop(self, result: RetrievalResult) -> None:
        """Expand one hop through imports, callers/callees, and tests."""
        existing_locators = set(result.all_locators())
        new_evidence: list[RetrievedEvidence] = []

        for ev in list(result.evidence):
            if ev.kind == "symbol":
                # Find the file for this symbol and get its imports
                file_path = ev.locator.split(":")[0]
                imports = self.dependency_index.imports_of(file_path)
                for imp in imports:
                    if imp.is_external:
                        continue
                    loc = imp.target_file or imp.target_module
                    if loc and loc not in existing_locators:
                        content = self._read_file(loc) if not loc.endswith(".") else ""
                        if content:
                            new_evidence.append(RetrievedEvidence(
                                kind="import",
                                locator=loc,
                                content=content[:3000],
                                source="dependency_expansion",
                                rank=5,
                                metadata={"imported_from": file_path},
                            ))
                            existing_locators.add(loc)

                # Find tests for the file's module
                file_entry = self.file_index.get(file_path)
                if file_entry:
                    # Try full module name and short name
                    test_candidates = self.test_index.tests_for_module(file_entry.module)
                    if not test_candidates:
                        short_name = file_entry.module.split(".")[-1]
                        test_candidates = self.test_index.tests_for_module(short_name)
                    for test in test_candidates:
                        loc = f"{test.file}:{test.start_line}"
                        if loc not in existing_locators:
                            content = self._read_test_content(test)
                            new_evidence.append(RetrievedEvidence(
                                kind="test",
                                locator=loc,
                                content=content,
                                source="test_expansion",
                                rank=5,
                                metadata={"name": test.name},
                            ))
                            existing_locators.add(loc)

            elif ev.kind == "file":
                # Find symbols in this file
                file_path = ev.locator
                symbols = self.symbol_index.find_in_file(file_path)
                for sym in symbols[:5]:
                    loc = f"{sym.file}:{sym.start_line}"
                    if loc not in existing_locators:
                        content = self._read_symbol_content(sym)
                        new_evidence.append(RetrievedEvidence(
                            kind="symbol",
                            locator=loc,
                            content=content,
                            source="symbol_expansion",
                            rank=5,
                            metadata={"name": sym.name, "kind": sym.kind.value},
                        ))
                        existing_locators.add(loc)

        result.evidence.extend(new_evidence)

    def _read_file(self, rel_path: str) -> str:
        """Read a file from the repo."""
        full_path = self.repo_root / rel_path
        try:
            return full_path.read_text()
        except OSError:
            return ""

    def _read_symbol_content(self, sym: SymbolEntry) -> str:
        """Read the source content of a symbol."""
        full_path = self.repo_root / sym.file
        try:
            lines = full_path.read_text().splitlines()
            start = max(0, sym.start_line - 1)
            end = min(len(lines), sym.end_line)
            return "\n".join(lines[start:end])
        except OSError:
            return sym.signature

    def _read_test_content(self, test: TestEntry) -> str:
        """Read the source content of a test function."""
        full_path = self.repo_root / test.file
        try:
            content = full_path.read_text()
            # Find the test function and read until next def or class
            lines = content.splitlines()
            start = max(0, test.start_line - 1)
            end = start + 1
            while end < len(lines):
                stripped = lines[end].strip()
                if stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("@"):
                    if end > start + 1:
                        break
                end += 1
            return "\n".join(lines[start:end])
        except OSError:
            return f"# test {test.name} in {test.file}"

    def retrieve_by_error(self, error_message: str) -> RetrievalResult:
        """Retrieve evidence based on an error message.

        Extracts file paths, symbol names, and line numbers from error output.
        """
        import re

        entities: list[str] = []

        # File:line patterns
        file_line_matches = re.findall(r'["\']?([^"\':\s]+\.\w+)["\']?:\d+', error_message)
        entities.extend(file_line_matches)

        # "NameError: name 'xxx' is not defined"
        name_matches = re.findall(r"name '(\w+)' is not defined", error_message)
        entities.extend(name_matches)

        # "AttributeError: 'xxx' object has no attribute 'yyy'"
        attr_matches = re.findall(r"has no attribute '(\w+)'", error_message)
        entities.extend(attr_matches)

        # "ModuleNotFoundError: No module named 'xxx'"
        module_matches = re.findall(r"No module named '([\w.]+)'", error_message)
        entities.extend(module_matches)

        # "ImportError: cannot import name 'xxx'"
        import_matches = re.findall(r"cannot import name '(\w+)'", error_message)
        entities.extend(import_matches)

        return self.retrieve(error_message, entities=entities, expand=True)

    def grounding_check(self, symbol_name: str, file_path: str | None = None) -> bool:
        """Check if a symbol reference resolves in the repository.

        Implements Section 6.3: every referenced symbol in a proposed patch
        should resolve in the repository or be intentionally introduced.
        """
        entry = self.symbol_index.resolve_symbol(symbol_name, file_path)
        return entry is not None

    def grounding_check_import(self, module_name: str) -> bool:
        """Check if an import resolves to a known module or declared dependency.

        Implements Section 6.3: every dependency import must exist in the
        lockfile/manifest or be explicitly proposed as a dependency change.
        """
        # Check if it's an internal module
        if module_name in self.dependency_index._module_to_file:
            return True
        # Check if it's a declared external dependency
        top_level = module_name.split(".")[0]
        return self.dependency_index.is_known_dependency(top_level)
