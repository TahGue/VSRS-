"""Import/dependency index: source, target, package, version (Section 6.1).

Tracks which files import which modules, and resolves external dependencies
from lockfiles/manifests. Used to prevent invented dependencies and find
impact of changes.
"""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger

logger = get_logger("repo.dependencies")


@dataclass
class ImportEdge:
    """An import relationship between files."""

    source_file: str  # relative path of the importing file
    target_module: str  # dotted module name being imported
    target_file: str | None = None  # resolved relative path, or None if external
    is_external: bool = False
    imported_names: list[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class PackageDependency:
    """An external package dependency."""

    name: str
    version: str = ""
    source: str = ""  # "pyproject.toml", "requirements.txt", etc.
    is_dev: bool = False


class DependencyIndex:
    """Index of import relationships and external dependencies.

    Provides:
    - Import graph: which files import which modules
    - External dependency list from manifest/lockfile
    - Resolution of module names to file paths
    - Impact analysis: who imports a given module
    """

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self._imports: list[ImportEdge] = []
        self._by_source: dict[str, list[ImportEdge]] = {}  # file -> imports
        self._by_target: dict[str, list[ImportEdge]] = {}  # module -> importers
        self._packages: dict[str, PackageDependency] = {}
        self._module_to_file: dict[str, str] = {}  # module path -> relative file path

    def register_module(self, module: str, file_path: str) -> None:
        """Register a module-to-file mapping."""
        self._module_to_file[module] = file_path

    def index_file_imports(self, file_path: str, content: str) -> list[ImportEdge]:
        """Parse a file's imports and add them to the index.

        Args:
            file_path: Relative path within the repo.
            content: File contents as a string.

        Returns:
            List of import edges extracted from this file.
        """
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError:
            return []

        edges: list[ImportEdge] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    edge = ImportEdge(
                        source_file=file_path,
                        target_module=alias.name,
                        imported_names=[alias.asname or alias.name],
                        line_number=node.lineno,
                    )
                    self._resolve_edge(edge)
                    edges.append(edge)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level and node.level > 0:
                    # Relative import — resolve against file location
                    module = self._resolve_relative_import(file_path, node.level, module)

                names = [alias.asname or alias.name for alias in node.names]
                edge = ImportEdge(
                    source_file=file_path,
                    target_module=module,
                    imported_names=names,
                    line_number=node.lineno,
                )
                self._resolve_edge(edge)
                edges.append(edge)

        for edge in edges:
            self._add(edge)

        return edges

    def _resolve_relative_import(self, file_path: str, level: int, module: str) -> str:
        """Resolve a relative import to an absolute module path."""
        parts = Path(file_path).parts[:-1]  # drop filename
        # Go up `level` directories
        if level <= len(parts):
            base_parts = parts[: len(parts) - level + 1]
        else:
            base_parts = parts
        if module:
            return ".".join(base_parts) + "." + module
        return ".".join(base_parts)

    def _resolve_edge(self, edge: ImportEdge) -> None:
        """Resolve whether an import target is internal or external."""
        # Check if the target module maps to a known file
        target_file = self._module_to_file.get(edge.target_module)
        if target_file:
            edge.target_file = target_file
            edge.is_external = False
            return

        # Try with __init__.py
        init_module = edge.target_module
        target_file = self._module_to_file.get(init_module)
        if target_file:
            edge.target_file = target_file
            edge.is_external = False
            return

        # Check if it's a stdlib or known external module
        edge.is_external = True

    def _add(self, edge: ImportEdge) -> None:
        """Add an import edge to the index."""
        self._imports.append(edge)
        self._by_source.setdefault(edge.source_file, []).append(edge)
        self._by_target.setdefault(edge.target_module, []).append(edge)

    # --- Manifest parsing ---

    def parse_pyproject_toml(self, toml_path: Path) -> list[PackageDependency]:
        """Parse pyproject.toml for dependencies."""
        deps: list[PackageDependency] = []
        if not toml_path.exists():
            return deps

        try:
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            logger.warning(f"Could not parse {toml_path}: {e}")
            return deps

        project = data.get("project", {})
        for dep_str in project.get("dependencies", []):
            dep = self._parse_dependency_string(dep_str, "pyproject.toml", is_dev=False)
            deps.append(dep)
            self._packages[dep.name] = dep

        optional = project.get("optional-dependencies", {})
        for group, dep_list in optional.items():
            for dep_str in dep_list:
                dep = self._parse_dependency_string(dep_str, "pyproject.toml", is_dev=True)
                deps.append(dep)
                self._packages[dep.name] = dep

        return deps

    def parse_requirements_txt(self, req_path: Path) -> list[PackageDependency]:
        """Parse requirements.txt for dependencies."""
        deps: list[PackageDependency] = []
        if not req_path.exists():
            return deps

        try:
            content = req_path.read_text()
        except OSError as e:
            logger.warning(f"Could not read {req_path}: {e}")
            return deps

        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            dep = self._parse_dependency_string(line, "requirements.txt", is_dev=False)
            deps.append(dep)
            self._packages[dep.name] = dep

        return deps

    def _parse_dependency_string(self, dep_str: str, source: str, is_dev: bool) -> PackageDependency:
        """Parse a PEP 508 dependency string."""
        # Extract name and version specifier
        match = re.match(r"^([a-zA-Z0-9_-]+)\s*(.*)$", dep_str.strip())
        if match:
            name = match.group(1).lower()
            version = match.group(2).strip()
        else:
            name = dep_str.strip().lower()
            version = ""

        return PackageDependency(
            name=name,
            version=version,
            source=source,
            is_dev=is_dev,
        )

    # --- Query methods ---

    def imports_of(self, file_path: str) -> list[ImportEdge]:
        """Get all imports made by a file."""
        return self._by_source.get(file_path, [])

    def importers_of(self, module: str) -> list[ImportEdge]:
        """Get all files that import a given module."""
        return self._by_target.get(module, [])

    def external_imports(self) -> list[ImportEdge]:
        """Get all external (non-stdlib, non-repo) imports."""
        return [e for e in self._imports if e.is_external]

    def internal_imports(self) -> list[ImportEdge]:
        """Get all internal (within-repo) imports."""
        return [e for e in self._imports if not e.is_external]

    def get_package(self, name: str) -> PackageDependency | None:
        """Get a package dependency by name."""
        return self._packages.get(name.lower())

    def is_known_dependency(self, name: str) -> bool:
        """Check if a package is declared in the manifest."""
        return name.lower() in self._packages

    def all_packages(self) -> list[PackageDependency]:
        """Get all declared package dependencies."""
        return list(self._packages.values())

    def impact_analysis(self, file_path: str) -> list[str]:
        """Find all files that transitively depend on the given file.

        Returns a list of file paths that import (directly or through
        a chain) the given file's module.
        """
        # Get the module name for this file
        target_module = None
        for module, fpath in self._module_to_file.items():
            if fpath == file_path:
                target_module = module
                break

        if not target_module:
            return []

        # BFS through importers
        visited: set[str] = set()
        queue: list[str] = [target_module]
        impacted: list[str] = []

        while queue:
            current = queue.pop(0)
            for edge in self._by_target.get(current, []):
                if edge.source_file not in visited and edge.source_file != file_path:
                    visited.add(edge.source_file)
                    impacted.append(edge.source_file)
                    # Find the module for this source file
                    for mod, fp in self._module_to_file.items():
                        if fp == edge.source_file:
                            queue.append(mod)
                            break

        return impacted

    @property
    def import_count(self) -> int:
        """Total number of import edges."""
        return len(self._imports)

    @property
    def package_count(self) -> int:
        """Number of declared external packages."""
        return len(self._packages)
