"""Symbol index: name, kind, file, span, signature (Section 6.1).

Parses Python ASTs to extract functions, classes, imports, and their
spans (line ranges) and signatures. Provides lookup by name, file, and kind.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from vsrs.core.logging import get_logger

logger = get_logger("repo.symbols")


class SymbolKind(str, Enum):
    """Kind of a symbol in the index."""

    function = "function"
    async_function = "async_function"
    class_ = "class"
    method = "method"
    import_ = "import"
    import_from = "import_from"
    module_variable = "module_variable"


@dataclass
class SymbolEntry:
    """A single indexed symbol."""

    name: str
    kind: SymbolKind
    file: str  # relative path
    start_line: int
    end_line: int
    signature: str  # e.g., "def foo(x: int, y: str) -> bool"
    qualified_name: str  # e.g., "src.auth.validate_password"
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    parent_class: str | None = None  # for methods


class SymbolIndex:
    """Index of all symbols in a repository, built from Python ASTs.

    Provides:
    - Lookup by name (exact and fuzzy)
    - Lookup by file
    - Lookup by kind
    - Call graph data (which symbols call which)
    """

    def __init__(self) -> None:
        self._symbols: list[SymbolEntry] = []
        self._by_name: dict[str, list[SymbolEntry]] = {}
        self._by_file: dict[str, list[SymbolEntry]] = {}
        self._by_qualified: dict[str, SymbolEntry] = {}

    def index_file(self, file_path: str, content: str, module: str = "") -> list[SymbolEntry]:
        """Parse a single Python file and index its symbols.

        Args:
            file_path: Relative path within the repo.
            content: File contents as a string.
            module: Dotted module path (e.g., src.auth).

        Returns:
            List of symbol entries extracted from this file.
        """
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return []

        entries = self._extract_symbols(tree, file_path, module)
        for entry in entries:
            self._add(entry)

        logger.debug(f"Indexed {len(entries)} symbols from {file_path}")
        return entries

    def index_directory(self, file_entries: list[tuple[str, str, str]]) -> int:
        """Index multiple files.

        Args:
            file_entries: List of (relative_path, content, module) tuples.

        Returns:
            Number of symbols indexed.
        """
        self._symbols.clear()
        self._by_name.clear()
        self._by_file.clear()
        self._by_qualified.clear()

        for rel_path, content, module in file_entries:
            self.index_file(rel_path, content, module)

        logger.info(f"Symbol index: {len(self._symbols)} symbols across {len(self._by_file)} files")
        return len(self._symbols)

    def _extract_symbols(
        self, tree: ast.AST, file_path: str, module: str
    ) -> list[SymbolEntry]:
        """Extract all symbol entries from an AST."""
        entries: list[SymbolEntry] = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entries.append(self._make_function_entry(node, file_path, module))
            elif isinstance(node, ast.ClassDef):
                entries.append(self._make_class_entry(node, file_path, module))
                # Extract methods
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        entries.append(
                            self._make_method_entry(child, node.name, file_path, module)
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    entries.append(self._make_import_entry(alias, node, file_path))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    entries.append(
                        self._make_import_from_entry(alias, node, file_path)
                    )

        return entries

    def _make_function_entry(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str, module: str,
    ) -> SymbolEntry:
        kind = SymbolKind.async_function if isinstance(node, ast.AsyncFunctionDef) else SymbolKind.function
        qual = f"{module}.{node.name}" if module else node.name
        return SymbolEntry(
            name=node.name,
            kind=kind,
            file=file_path,
            start_line=node.lineno,
            end_line=self._get_end_line(node),
            signature=self._format_signature(node),
            qualified_name=qual,
            decorators=self._extract_decorators(node),
            docstring=ast.get_docstring(node) or "",
        )

    def _make_class_entry(
        self, node: ast.ClassDef, file_path: str, module: str
    ) -> SymbolEntry:
        qual = f"{module}.{node.name}" if module else node.name
        bases = [self._format_name(b) for b in node.bases]
        sig = f"class {node.name}"
        if bases:
            sig += f"({', '.join(bases)})"
        return SymbolEntry(
            name=node.name,
            kind=SymbolKind.class_,
            file=file_path,
            start_line=node.lineno,
            end_line=self._get_end_line(node),
            signature=sig,
            qualified_name=qual,
            decorators=self._extract_decorators(node),
            docstring=ast.get_docstring(node) or "",
        )

    def _make_method_entry(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef,
        class_name: str, file_path: str, module: str,
    ) -> SymbolEntry:
        kind = SymbolKind.async_function if isinstance(node, ast.AsyncFunctionDef) else SymbolKind.method
        qual = f"{module}.{class_name}.{node.name}" if module else f"{class_name}.{node.name}"
        return SymbolEntry(
            name=node.name,
            kind=kind,
            file=file_path,
            start_line=node.lineno,
            end_line=self._get_end_line(node),
            signature=self._format_signature(node),
            qualified_name=qual,
            decorators=self._extract_decorators(node),
            docstring=ast.get_docstring(node) or "",
            parent_class=class_name,
        )

    def _make_import_entry(
        self, alias: ast.alias, node: ast.Import, file_path: str
    ) -> SymbolEntry:
        name = alias.asname or alias.name
        return SymbolEntry(
            name=name,
            kind=SymbolKind.import_,
            file=file_path,
            start_line=node.lineno,
            end_line=node.lineno,
            signature=f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
            qualified_name=name,
        )

    def _make_import_from_entry(
        self, alias: ast.alias, node: ast.ImportFrom, file_path: str
    ) -> SymbolEntry:
        name = alias.asname or alias.name
        module = node.module or ""
        return SymbolEntry(
            name=name,
            kind=SymbolKind.import_from,
            file=file_path,
            start_line=node.lineno,
            end_line=node.lineno,
            signature=f"from {module} import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
            qualified_name=name,
        )

    def _format_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Format a function signature string."""
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        args = self._format_args(node.args)
        returns = ""
        if node.returns:
            returns = f" -> {self._format_name(node.returns)}"
        return f"{prefix} {node.name}({args}){returns}"

    def _format_args(self, args: ast.arguments) -> str:
        """Format function arguments."""
        parts: list[str] = []

        # Positional args
        for arg in args.posonlyargs:
            parts.append(self._format_arg(arg))
        for arg in args.args:
            parts.append(self._format_arg(arg))

        # *args
        if args.vararg:
            parts.append(f"*{self._format_arg(args.vararg)}")
        elif args.kwonlyargs:
            parts.append("*")

        # Keyword-only args
        for arg in args.kwonlyargs:
            parts.append(self._format_arg(arg))

        # **kwargs
        if args.kwarg:
            parts.append(f"**{self._format_arg(args.kwarg)}")

        return ", ".join(parts)

    def _format_arg(self, arg: ast.arg) -> str:
        """Format a single argument."""
        if arg.annotation:
            return f"{arg.arg}: {self._format_name(arg.annotation)}"
        return arg.arg

    def _format_name(self, node: ast.AST) -> str:
        """Format an AST node as a type/name string."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._format_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Subscript):
            return f"{self._format_name(node.value)}[{self._format_name(node.slice)}]"
        if isinstance(node, ast.BitOr):
            return f"{self._format_name(node.left)} | {self._format_name(node.right)}"
        if isinstance(node, ast.Tuple):
            return ", ".join(self._format_name(e) for e in node.elts)
        return ast.dump(node)

    def _extract_decorators(self, node: ast.AST) -> list[str]:
        """Extract decorator names."""
        decorators: list[str] = []
        if hasattr(node, "decorator_list"):
            for dec in node.decorator_list:
                decorators.append(self._format_name(dec))
        return decorators

    def _get_end_line(self, node: ast.AST) -> int:
        """Get the end line of a node."""
        if hasattr(node, "end_lineno") and node.end_lineno:
            return node.end_lineno
        if hasattr(node, "body") and node.body:
            return self._get_end_line(node.body[-1])
        return getattr(node, "lineno", 0)

    def _add(self, entry: SymbolEntry) -> None:
        """Add a symbol entry to all indexes."""
        self._symbols.append(entry)
        self._by_name.setdefault(entry.name, []).append(entry)
        self._by_file.setdefault(entry.file, []).append(entry)
        if entry.qualified_name not in self._by_qualified:
            self._by_qualified[entry.qualified_name] = entry

    # --- Query methods ---

    def find_by_name(self, name: str) -> list[SymbolEntry]:
        """Find all symbols with the given name (exact match)."""
        return self._by_name.get(name, [])

    def find_by_qualified_name(self, qual: str) -> SymbolEntry | None:
        """Find a symbol by its qualified name."""
        return self._by_qualified.get(qual)

    def find_in_file(self, file_path: str) -> list[SymbolEntry]:
        """Get all symbols in a specific file."""
        return self._by_file.get(file_path, [])

    def find_by_kind(self, kind: SymbolKind) -> list[SymbolEntry]:
        """Get all symbols of a specific kind."""
        return [s for s in self._symbols if s.kind == kind]

    def find_functions(self) -> list[SymbolEntry]:
        """Get all function symbols (including async and methods)."""
        return [
            s for s in self._symbols
            if s.kind in (SymbolKind.function, SymbolKind.async_function, SymbolKind.method)
        ]

    def find_classes(self) -> list[SymbolEntry]:
        """Get all class symbols."""
        return self.find_by_kind(SymbolKind.class_)

    def find_imports(self) -> list[SymbolEntry]:
        """Get all import symbols."""
        return [
            s for s in self._symbols
            if s.kind in (SymbolKind.import_, SymbolKind.import_from)
        ]

    def fuzzy_search(self, query: str, limit: int = 20) -> list[SymbolEntry]:
        """Fuzzy search for symbols by name.

        Matches symbols whose name contains the query string (case-insensitive).
        """
        query_lower = query.lower()
        matches = [
            s for s in self._symbols
            if query_lower in s.name.lower()
        ]
        return matches[:limit]

    def resolve_symbol(self, name: str, file_path: str | None = None) -> SymbolEntry | None:
        """Resolve a symbol reference to its definition.

        Tries exact name match first, then qualified name.
        If file_path is given, prefers symbols in the same file.
        """
        # Try exact name match
        candidates = self._by_name.get(name, [])
        if not candidates:
            return None

        if file_path:
            same_file = [s for s in candidates if s.file == file_path]
            if same_file:
                return same_file[0]

        return candidates[0]

    @property
    def count(self) -> int:
        """Total number of indexed symbols."""
        return len(self._symbols)
