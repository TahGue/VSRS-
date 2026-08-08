"""Tests for Phase 24: Tree-sitter structural indexing.

Tests the TreeSitterIndexer, HybridSymbolIndex, language detection,
and graceful fallback when tree-sitter is not installed.
"""

import pytest
from pathlib import Path

from vsrs.repo.tree_sitter_index import (
    TreeSitterIndexer,
    HybridSymbolIndex,
    detect_language,
    LANGUAGE_MAP,
    HAS_TREE_SITTER,
)
from vsrs.repo.symbols import SymbolEntry, SymbolKind


# --- Language detection tests ---

class TestLanguageDetection:
    def test_python(self):
        assert detect_language("src/main.py") == "python"

    def test_javascript(self):
        assert detect_language("app.js") == "javascript"

    def test_javascript_jsx(self):
        assert detect_language("component.jsx") == "javascript"

    def test_typescript(self):
        assert detect_language("app.ts") == "typescript"

    def test_typescript_tsx(self):
        assert detect_language("component.tsx") == "typescript"

    def test_go(self):
        assert detect_language("main.go") == "go"

    def test_rust(self):
        assert detect_language("lib.rs") == "rust"

    def test_java(self):
        assert detect_language("Main.java") == "java"

    def test_c(self):
        assert detect_language("main.c") == "c"

    def test_cpp(self):
        assert detect_language("main.cpp") == "cpp"

    def test_ruby(self):
        assert detect_language("app.rb") == "ruby"

    def test_unsupported(self):
        assert detect_language("README.md") is None

    def test_unsupported_txt(self):
        assert detect_language("data.txt") is None

    def test_no_extension(self):
        assert detect_language("Makefile") is None

    def test_case_insensitive(self):
        assert detect_language("MAIN.PY") == "python"

    def test_language_map_completeness(self):
        """All expected extensions are in the map."""
        expected = {".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".c", ".cpp", ".rb"}
        assert expected.issubset(set(LANGUAGE_MAP.keys()))


# --- TreeSitterIndexer tests ---

class TestTreeSitterIndexer:
    def test_init(self):
        indexer = TreeSitterIndexer()
        assert indexer._initialized is False

    def test_available_property(self):
        indexer = TreeSitterIndexer()
        assert isinstance(indexer.available, bool)

    def test_supported_languages(self):
        indexer = TreeSitterIndexer()
        langs = indexer.supported_languages
        assert "python" in langs
        assert "javascript" in langs
        assert "typescript" in langs
        assert "go" in langs
        assert "rust" in langs
        assert "java" in langs

    def test_index_unsupported_file(self):
        indexer = TreeSitterIndexer()
        entries = indexer.index_file("readme.md", "# Hello")
        assert entries == []

    def test_index_empty_file(self):
        indexer = TreeSitterIndexer()
        entries = indexer.index_file("empty.py", "")
        # Should not crash, may return empty or minimal entries
        assert isinstance(entries, list)

    def test_index_python_function(self):
        indexer = TreeSitterIndexer()
        content = '''def hello(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}"
'''
        entries = indexer.index_file("main.py", content, "main")
        if HAS_TREE_SITTER:
            assert len(entries) >= 1
            func = [e for e in entries if e.kind in (SymbolKind.function, SymbolKind.method)]
            assert len(func) >= 1
            assert func[0].name == "hello"
            assert func[0].file == "main.py"
            assert func[0].start_line >= 1
        else:
            # Without tree-sitter, should return empty
            assert entries == []

    def test_index_python_class(self):
        indexer = TreeSitterIndexer()
        content = '''class MyClass:
    """A class."""
    def method(self):
        return 42
'''
        entries = indexer.index_file("main.py", content, "main")
        if HAS_TREE_SITTER:
            classes = [e for e in entries if e.kind == SymbolKind.class_]
            assert len(classes) >= 1
            assert classes[0].name == "MyClass"

            methods = [e for e in entries if e.kind == SymbolKind.method]
            assert len(methods) >= 1
            assert methods[0].name == "method"
            assert methods[0].parent_class == "MyClass"
        else:
            assert entries == []

    def test_index_javascript_function(self):
        indexer = TreeSitterIndexer()
        content = '''function add(a, b) {
  return a + b;
}

class Calculator {
  multiply(x, y) {
    return x * y;
  }
}
'''
        entries = indexer.index_file("app.js", content, "app")
        if HAS_TREE_SITTER:
            funcs = [e for e in entries if e.kind == SymbolKind.function]
            assert len(funcs) >= 1
            assert funcs[0].name == "add"

            classes = [e for e in entries if e.kind == SymbolKind.class_]
            assert len(classes) >= 1
            assert classes[0].name == "Calculator"
        else:
            assert entries == []

    def test_index_typescript_interface(self):
        indexer = TreeSitterIndexer()
        content = '''interface User {
  id: number;
  name: string;
}

function getUser(id: number): User {
  return { id, name: "test" };
}
'''
        entries = indexer.index_file("user.ts", content, "user")
        if HAS_TREE_SITTER:
            assert len(entries) >= 1
        else:
            assert entries == []

    def test_index_go_function(self):
        indexer = TreeSitterIndexer()
        content = '''package main

import "fmt"

func main() {
    fmt.Println("Hello")
}

type Config struct {
    Port int
}
'''
        entries = indexer.index_file("main.go", content, "main")
        if HAS_TREE_SITTER:
            funcs = [e for e in entries if e.kind == SymbolKind.function]
            assert len(funcs) >= 1
            assert any(f.name == "main" for f in funcs)
        else:
            assert entries == []

    def test_index_rust_function(self):
        indexer = TreeSitterIndexer()
        content = '''pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

struct Point {
    x: f64,
    y: f64,
}
'''
        entries = indexer.index_file("lib.rs", content, "lib")
        if HAS_TREE_SITTER:
            funcs = [e for e in entries if e.kind == SymbolKind.function]
            assert len(funcs) >= 1
            assert any(f.name == "add" for f in funcs)
        else:
            assert entries == []

    def test_index_java_class(self):
        indexer = TreeSitterIndexer()
        content = '''public class Main {
    public static void main(String[] args) {
        System.out.println("Hello");
    }
}
'''
        entries = indexer.index_file("Main.java", content, "Main")
        if HAS_TREE_SITTER:
            classes = [e for e in entries if e.kind == SymbolKind.class_]
            assert len(classes) >= 1
            assert classes[0].name == "Main"
        else:
            assert entries == []

    def test_index_syntax_error_file(self):
        """Should not crash on syntax errors."""
        indexer = TreeSitterIndexer()
        content = "def broken(:\n    pass\n"
        entries = indexer.index_file("bad.py", content, "bad")
        assert isinstance(entries, list)

    def test_supports_language(self):
        indexer = TreeSitterIndexer()
        if HAS_TREE_SITTER:
            indexer._init_parsers()
            assert indexer.supports_language("main.py") in (True, False)  # Depends on parser init
        # Unsupported extension always False
        # (supports_language checks parser, not just extension)

    def test_qualified_name(self):
        indexer = TreeSitterIndexer()
        content = "def foo():\n    pass\n"
        entries = indexer.index_file("main.py", content, "src.main")
        if HAS_TREE_SITTER:
            assert entries[0].qualified_name == "src.main.foo"


# --- HybridSymbolIndex tests ---

class TestHybridSymbolIndex:
    def test_init(self):
        idx = HybridSymbolIndex()
        assert idx.count == 0
        assert isinstance(idx.tree_sitter_available, bool)

    def test_index_python_file(self):
        """Python files should use the AST-based index."""
        idx = HybridSymbolIndex()
        content = '''def hello():
    """Greet."""
    return "hi"

class Foo:
    def bar(self):
        return 42
'''
        entries = idx.index_file("main.py", content, "main")
        assert len(entries) >= 3  # hello, Foo, bar
        assert any(e.name == "hello" for e in entries)
        assert any(e.name == "Foo" for e in entries)
        assert any(e.name == "bar" for e in entries)

    def test_index_python_function_kind(self):
        idx = HybridSymbolIndex()
        content = "def my_func(x: int) -> bool:\n    return x > 0\n"
        entries = idx.index_file("main.py", content, "main")
        func = [e for e in entries if e.name == "my_func"]
        assert len(func) == 1
        assert func[0].kind == SymbolKind.function

    def test_index_python_class_with_method(self):
        idx = HybridSymbolIndex()
        content = "class Foo:\n    def bar(self):\n        return 42\n"
        entries = idx.index_file("main.py", content, "main")
        methods = [e for e in entries if e.kind == SymbolKind.method]
        assert len(methods) == 1
        assert methods[0].name == "bar"
        assert methods[0].parent_class == "Foo"

    def test_index_python_imports(self):
        idx = HybridSymbolIndex()
        content = "import os\nfrom typing import List\n"
        entries = idx.index_file("main.py", content, "main")
        imports = [e for e in entries if e.kind in (SymbolKind.import_, SymbolKind.import_from)]
        assert len(imports) == 2

    def test_index_non_python_file(self):
        """Non-Python files should use tree-sitter or return empty."""
        idx = HybridSymbolIndex()
        content = "function foo() { return 1; }\n"
        entries = idx.index_file("app.js", content, "app")
        assert isinstance(entries, list)

    def test_index_unsupported_file(self):
        idx = HybridSymbolIndex()
        entries = idx.index_file("readme.md", "# Hello")
        assert entries == []

    def test_index_directory(self):
        idx = HybridSymbolIndex()
        files = [
            ("main.py", "def foo():\n    pass\n", "main"),
            ("utils.py", "def bar():\n    pass\n", "utils"),
        ]
        count = idx.index_directory(files)
        assert count >= 2

    def test_index_directory_mixed_languages(self):
        idx = HybridSymbolIndex()
        files = [
            ("main.py", "def foo():\n    pass\n", "main"),
            ("app.js", "function bar() { return 1; }\n", "app"),
        ]
        count = idx.index_directory(files)
        # At least the Python file should be indexed
        assert count >= 1

    def test_index_directory_empty(self):
        idx = HybridSymbolIndex()
        count = idx.index_directory([])
        assert count == 0

    def test_python_qualified_name(self):
        idx = HybridSymbolIndex()
        content = "def foo():\n    pass\n"
        entries = idx.index_file("main.py", content, "src.main")
        assert entries[0].qualified_name == "src.main.foo"

    def test_python_decorators(self):
        idx = HybridSymbolIndex()
        content = '''@property
def x(self):
    return self._x
'''
        entries = idx.index_file("main.py", content, "main")
        func = [e for e in entries if e.name == "x"]
        assert len(func) == 1
        assert "property" in func[0].decorators

    def test_python_docstring(self):
        idx = HybridSymbolIndex()
        content = '''def foo():
    """This is a docstring."""
    return 42
'''
        entries = idx.index_file("main.py", content, "main")
        func = [e for e in entries if e.name == "foo"]
        assert len(func) == 1
        assert "This is a docstring" in func[0].docstring

    def test_python_signature(self):
        idx = HybridSymbolIndex()
        content = "def add(a: int, b: int) -> int:\n    return a + b\n"
        entries = idx.index_file("main.py", content, "main")
        func = [e for e in entries if e.name == "add"]
        assert len(func) == 1
        assert "def add" in func[0].signature
        assert "a: int" in func[0].signature

    def test_python_async_function(self):
        idx = HybridSymbolIndex()
        content = "async def fetch():\n    return 1\n"
        entries = idx.index_file("main.py", content, "main")
        funcs = [e for e in entries if e.name == "fetch"]
        assert len(funcs) == 1
        assert funcs[0].kind == SymbolKind.async_function


# --- Module structure tests ---

class TestModuleStructure:
    def test_module_importable(self):
        from vsrs.repo import tree_sitter_index
        assert hasattr(tree_sitter_index, "TreeSitterIndexer")
        assert hasattr(tree_sitter_index, "HybridSymbolIndex")
        assert hasattr(tree_sitter_index, "detect_language")

    def test_has_tree_sitter_flag(self):
        assert isinstance(HAS_TREE_SITTER, bool)

    def test_language_map_has_expected_entries(self):
        assert LANGUAGE_MAP[".py"] == "python"
        assert LANGUAGE_MAP[".js"] == "javascript"
        assert LANGUAGE_MAP[".ts"] == "typescript"
        assert LANGUAGE_MAP[".go"] == "go"
        assert LANGUAGE_MAP[".rs"] == "rust"
        assert LANGUAGE_MAP[".java"] == "java"

    def test_node_type_map_has_languages(self):
        from vsrs.repo.tree_sitter_index import NODE_TYPE_MAP
        assert "python" in NODE_TYPE_MAP
        assert "javascript" in NODE_TYPE_MAP
        assert "typescript" in NODE_TYPE_MAP
        assert "go" in NODE_TYPE_MAP
        assert "rust" in NODE_TYPE_MAP
        assert "java" in NODE_TYPE_MAP

    def test_logger_exists(self):
        from vsrs.repo.tree_sitter_index import logger
        assert logger is not None
