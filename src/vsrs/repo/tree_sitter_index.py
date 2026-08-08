"""Tree-sitter based structural indexing for multi-language repositories.

Provides symbol extraction using tree-sitter parsers for Python, JavaScript,
TypeScript, Go, Rust, and Java. Falls back to the existing Python AST-based
SymbolIndex when tree-sitter is not installed or a language is unsupported.

Tree-sitter is an optional dependency. Install with:
    pip install tree-sitter tree-sitter-languages
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from vsrs.core.logging import get_logger
from vsrs.repo.symbols import SymbolEntry, SymbolKind

logger = get_logger("repo.tree_sitter_index")

# Try to import tree-sitter
try:
    import tree_sitter  # type: ignore[import-not-found]
    from tree_sitter_languages import get_language, get_parser  # type: ignore[import-not-found]
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False
    tree_sitter = None  # type: ignore[assignment]
    get_language = None  # type: ignore[assignment]
    get_parser = None  # type: ignore[assignment]

logger.info(f"Tree-sitter available: {HAS_TREE_SITTER}")


# --- Language mapping ---

LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".rb": "ruby",
}


def detect_language(file_path: str) -> str | None:
    """Detect tree-sitter language from file extension.

    Args:
        file_path: File path or extension.

    Returns:
        Language name or None if unsupported.
    """
    ext = Path(file_path).suffix.lower()
    return LANGUAGE_MAP.get(ext)


# --- Node type patterns per language ---

# Maps tree-sitter node types to SymbolKind
NODE_TYPE_MAP: dict[str, dict[str, SymbolKind]] = {
    "python": {
        "function_definition": SymbolKind.function,
        "class_definition": SymbolKind.class_,
        "import_statement": SymbolKind.import_,
        "import_from_statement": SymbolKind.import_from,
    },
    "javascript": {
        "function_declaration": SymbolKind.function,
        "class_declaration": SymbolKind.class_,
        "method_definition": SymbolKind.method,
    },
    "typescript": {
        "function_declaration": SymbolKind.function,
        "class_declaration": SymbolKind.class_,
        "method_definition": SymbolKind.method,
        "interface_declaration": SymbolKind.class_,
        "type_alias_declaration": SymbolKind.module_variable,
        "import_statement": SymbolKind.import_,
    },
    "go": {
        "function_declaration": SymbolKind.function,
        "method_declaration": SymbolKind.method,
        "type_declaration": SymbolKind.class_,
        "import_declaration": SymbolKind.import_,
    },
    "rust": {
        "function_item": SymbolKind.function,
        "struct_item": SymbolKind.class_,
        "enum_item": SymbolKind.class_,
        "trait_item": SymbolKind.class_,
        "impl_item": SymbolKind.class_,
        "use_declaration": SymbolKind.import_,
    },
    "java": {
        "method_declaration": SymbolKind.method,
        "class_declaration": SymbolKind.class_,
        "interface_declaration": SymbolKind.class_,
        "enum_declaration": SymbolKind.class_,
        "import_declaration": SymbolKind.import_,
    },
}


# --- Name extraction ---

def _get_node_name(node: Any, language: str) -> str:
    """Extract the name identifier from a tree-sitter node."""
    name_fields = ["name", "identifier", "declarator"]
    for field_name in name_fields:
        child = node.child_by_field_name(field_name)
        if child:
            text = child.text
            if isinstance(text, bytes):
                return text.decode("utf-8")
            return str(text)

    # For Python function_definition, name is a direct child
    for child in node.children:
        if child.type == "identifier":
            text = child.text
            if isinstance(text, bytes):
                return text.decode("utf-8")
            return str(text)

    return "<anonymous>"


def _get_node_text(node: Any) -> str:
    """Get text content of a node as string."""
    text = node.text
    if isinstance(text, bytes):
        return text.decode("utf-8")
    return str(text)


def _get_start_line(node: Any) -> int:
    """Get 1-indexed start line of a node."""
    return node.start_point[0] + 1


def _get_end_line(node: Any) -> int:
    """Get 1-indexed end line of a node."""
    return node.end_point[0] + 1


def _format_signature(node: Any, language: str, source_lines: list[str]) -> str:
    """Build a signature string from the first line(s) of a node."""
    start = _get_start_line(node) - 1
    end = min(start + 3, len(source_lines))
    lines = source_lines[start:end]
    # Take first line, trim trailing whitespace
    sig = lines[0].strip() if lines else ""
    # For multi-line signatures, try to capture the closing paren
    if sig and not sig.endswith(")") and not sig.endswith(":") and not sig.endswith("{"):
        for line in lines[1:]:
            sig += " " + line.strip()
            if line.strip().endswith(")") or line.strip().endswith(":") or line.strip().endswith("{"):
                break
    return sig[:200]  # Cap at 200 chars


def _extract_decorators(node: Any, language: str, source_lines: list[str]) -> list[str]:
    """Extract decorator/annotation names from a node."""
    decorators: list[str] = []
    if language == "python":
        for child in node.children:
            if child.type == "decorator":
                decorators.append(_get_node_text(child).strip().lstrip("@"))
    return decorators


def _extract_docstring(node: Any, language: str, source_lines: list[str]) -> str:
    """Extract docstring/comment from a node."""
    if language == "python":
        for child in node.children:
            if child.type in ("expression_statement", "string"):
                text = _get_node_text(child).strip()
                if text.startswith(('"""', "'''", '"', "'")):
                    return text.strip('\"\'').strip()
    elif language in ("javascript", "typescript"):
        for child in node.children:
            if child.type == "comment":
                return _get_node_text(child).strip("/* */\n")
    return ""


def _get_parent_class(node: Any, language: str) -> str | None:
    """Get parent class name if this node is a method."""
    parent = node.parent
    while parent is not None:
        if parent.type in ("class_declaration", "class_definition", "impl_item", "interface_declaration"):
            return _get_node_name(parent, language)
        parent = parent.parent
    return None


# --- Main indexer ---

class TreeSitterIndexer:
    """Indexes symbols from source files using tree-sitter.

    Supports Python, JavaScript, TypeScript, Go, Rust, and Java.
    Falls back gracefully when tree-sitter is not installed.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}
        self._initialized = False

    def _init_parsers(self) -> None:
        """Initialize parsers for all supported languages."""
        if self._initialized or not HAS_TREE_SITTER:
            return
        for ext, lang_name in LANGUAGE_MAP.items():
            if lang_name not in self._parsers:
                try:
                    parser = get_parser(lang_name)
                    self._parsers[lang_name] = parser
                except Exception as e:
                    logger.debug(f"Could not init parser for {lang_name}: {e}")
        self._initialized = True

    def index_file(
        self,
        file_path: str,
        content: str,
        module: str = "",
    ) -> list[SymbolEntry]:
        """Parse a file with tree-sitter and extract symbols.

        Args:
            file_path: Relative path within the repo.
            content: File contents as a string.
            module: Dotted module path (for qualified names).

        Returns:
            List of symbol entries. Empty list if language unsupported or
            tree-sitter not available.
        """
        if not HAS_TREE_SITTER:
            return []

        self._init_parsers()

        language = detect_language(file_path)
        if not language:
            return []

        parser = self._parsers.get(language)
        if not parser:
            logger.debug(f"No parser for language: {language}")
            return []

        source_bytes = content.encode("utf-8")
        source_lines = content.splitlines()

        try:
            tree = parser.parse(source_bytes)
        except Exception as e:
            logger.warning(f"Parse error in {file_path}: {e}")
            return []

        return self._extract_symbols(
            tree.root_node,
            file_path,
            module,
            language,
            source_lines,
        )

    def _extract_symbols(
        self,
        root_node: Any,
        file_path: str,
        module: str,
        language: str,
        source_lines: list[str],
    ) -> list[SymbolEntry]:
        """Walk the tree-sitter AST and extract symbol entries."""
        entries: list[SymbolEntry] = []
        type_map = NODE_TYPE_MAP.get(language, {})

        def walk(node: Any, parent_class: str | None = None) -> None:
            node_type = node.type
            symbol_kind = type_map.get(node_type)

            if symbol_kind is not None:
                name = _get_node_name(node, language)
                start_line = _get_start_line(node)
                end_line = _get_end_line(node)
                signature = _format_signature(node, language, source_lines)
                decorators = _extract_decorators(node, language, source_lines)
                docstring = _extract_docstring(node, language, source_lines)

                # Determine parent class for methods
                actual_parent = parent_class or _get_parent_class(node, language)

                # Adjust kind for methods
                kind = symbol_kind
                if kind == SymbolKind.function and actual_parent:
                    kind = SymbolKind.method

                # Build qualified name
                if actual_parent:
                    qual = f"{module}.{actual_parent}.{name}" if module else f"{actual_parent}.{name}"
                else:
                    qual = f"{module}.{name}" if module else name

                entry = SymbolEntry(
                    name=name,
                    kind=kind,
                    file=file_path,
                    start_line=start_line,
                    end_line=end_line,
                    signature=signature,
                    qualified_name=qual,
                    decorators=decorators,
                    docstring=docstring,
                    parent_class=actual_parent,
                )
                entries.append(entry)

                # Recurse into class bodies to find methods
                if symbol_kind == SymbolKind.class_:
                    for child in node.children:
                        walk(child, name)
                    return

            # Recurse into children
            for child in node.children:
                walk(child, parent_class)

        walk(root_node)

        logger.debug(f"Tree-sitter indexed {len(entries)} symbols from {file_path} ({language})")
        return entries

    def supports_language(self, file_path: str) -> bool:
        """Check if this indexer supports the language of a file."""
        lang = detect_language(file_path)
        return lang is not None and lang in self._parsers

    @property
    def available(self) -> bool:
        """Whether tree-sitter is installed and ready."""
        return HAS_TREE_SITTER

    @property
    def supported_languages(self) -> list[str]:
        """List of supported language names."""
        return list(set(LANGUAGE_MAP.values()))


# --- Hybrid indexer: tree-sitter + Python AST fallback ---

class HybridSymbolIndex:
    """Symbol index that uses tree-sitter when available, Python AST otherwise.

    For Python files, uses tree-sitter if installed, falls back to the
    existing ast-based SymbolIndex. For non-Python files, uses tree-sitter.

    This class wraps the existing SymbolIndex and augments it with
    tree-sitter for multi-language support.
    """

    def __init__(self) -> None:
        from vsrs.repo.symbols import SymbolIndex
        self._ast_index = SymbolIndex()
        self._ts_indexer = TreeSitterIndexer()

    def index_file(
        self,
        file_path: str,
        content: str,
        module: str = "",
    ) -> list[SymbolEntry]:
        """Index a file using the best available parser.

        For .py files: uses Python AST (more accurate for Python).
        For other languages: uses tree-sitter if available.

        Returns:
            List of symbol entries.
        """
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            # Python AST is more accurate for Python
            return self._ast_index.index_file(file_path, content, module)

        if self._ts_indexer.available:
            entries = self._ts_indexer.index_file(file_path, content, module)
            if entries:
                return entries

        # No parser available for this file type
        return []

    def index_directory(
        self,
        file_entries: list[tuple[str, str, str]],
    ) -> int:
        """Index multiple files.

        Args:
            file_entries: List of (relative_path, content, module) tuples.

        Returns:
            Number of symbols indexed.
        """
        total = 0
        for rel_path, content, module in file_entries:
            entries = self.index_file(rel_path, content, module)
            total += len(entries)
        return total

    @property
    def all_symbols(self) -> list[SymbolEntry]:
        """Get all indexed symbols (Python AST only)."""
        return self._ast_index._symbols

    @property
    def count(self) -> int:
        """Total number of indexed symbols."""
        return len(self._ast_index._symbols)

    @property
    def tree_sitter_available(self) -> bool:
        """Whether tree-sitter is installed."""
        return self._ts_indexer.available
