"""Tests for the symbol index (Phase 2.1)."""

from vsrs.repo.symbols import SymbolIndex, SymbolKind


SAMPLE_AUTH = '''\
"""Auth module."""

import os
from typing import Optional


def validate_password(pw: str) -> bool:
    """Validate a password."""
    return bool(pw)


def login(username: str, password: str) -> bool:
    """Login a user."""
    if not validate_password(password):
        return False
    return True


class AuthManager:
    """Manages authentication."""

    def __init__(self, secret: str):
        self.secret = secret

    def authenticate(self, token: str) -> bool:
        """Check token."""
        return token == self.secret

    async def async_refresh(self) -> str:
        """Refresh token."""
        return self.secret
'''


SAMPLE_UTILS = '''\
"""Utils module."""

from src.auth import validate_password

MAX_RETRIES = 3


def retry(fn, retries: int = MAX_RETRIES):
    """Retry a function."""
    for i in range(retries):
        try:
            return fn()
        except Exception:
            continue
    return None
'''


class TestSymbolIndex:
    def test_index_file_functions(self):
        index = SymbolIndex()
        entries = index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        names = {e.name for e in entries}
        assert "validate_password" in names
        assert "login" in names
        assert "AuthManager" in names

    def test_index_file_classes(self):
        index = SymbolIndex()
        entries = index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        classes = [e for e in entries if e.kind == SymbolKind.class_]
        assert len(classes) == 1
        assert classes[0].name == "AuthManager"

    def test_index_file_methods(self):
        index = SymbolIndex()
        entries = index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        # Methods include both 'method' and 'async_function' (for async methods)
        method_like = [e for e in entries if e.kind in (SymbolKind.method, SymbolKind.async_function) and e.parent_class]
        method_names = {m.name for m in method_like}
        assert "__init__" in method_names
        assert "authenticate" in method_names
        assert "async_refresh" in method_names

    def test_async_function(self):
        index = SymbolIndex()
        entries = index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        async_fns = [e for e in entries if e.kind == SymbolKind.async_function]
        assert len(async_fns) == 1
        assert async_fns[0].name == "async_refresh"

    def test_imports(self):
        index = SymbolIndex()
        entries = index.index_file("src/utils.py", SAMPLE_UTILS, "src.utils")

        imports = [e for e in entries if e.kind in (SymbolKind.import_, SymbolKind.import_from)]
        assert len(imports) >= 1  # from src.auth import validate_password
        assert any(e.name == "validate_password" for e in imports)

    def test_qualified_names(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        sym = index.find_by_qualified_name("src.auth.validate_password")
        assert sym is not None
        assert sym.name == "validate_password"

        method = index.find_by_qualified_name("src.auth.AuthManager.authenticate")
        assert method is not None
        assert method.parent_class == "AuthManager"

    def test_signatures(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        sym = index.find_by_qualified_name("src.auth.validate_password")
        assert "def validate_password(pw: str) -> bool" == sym.signature

    def test_spans(self):
        index = SymbolIndex()
        entries = index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        vp = [e for e in entries if e.name == "validate_password"][0]
        assert vp.start_line == 7
        assert vp.end_line >= 9

    def test_docstrings(self):
        index = SymbolIndex()
        entries = index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        vp = [e for e in entries if e.name == "validate_password"][0]
        assert "Validate a password" in vp.docstring

    def test_decorators(self):
        code = '''\
@staticmethod
def static_method():
    pass

@property
def prop(self):
    return self._x
'''
        index = SymbolIndex()
        entries = index.index_file("test.py", code, "test")
        sm = [e for e in entries if e.name == "static_method"][0]
        assert "staticmethod" in sm.decorators

    def test_find_by_name(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        results = index.find_by_name("login")
        assert len(results) == 1
        assert results[0].name == "login"

    def test_find_in_file(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        results = index.find_in_file("src/auth.py")
        assert len(results) >= 5  # functions + class + methods

    def test_fuzzy_search(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        results = index.fuzzy_search("auth")
        names = {r.name for r in results}
        assert "AuthManager" in names
        assert "authenticate" in names

    def test_resolve_symbol(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        sym = index.resolve_symbol("validate_password")
        assert sym is not None
        assert sym.name == "validate_password"

        sym = index.resolve_symbol("nonexistent")
        assert sym is None

    def test_resolve_symbol_prefers_same_file(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")
        index.index_file("src/auth2.py", SAMPLE_AUTH, "src.auth2")

        sym = index.resolve_symbol("validate_password", "src/auth2.py")
        assert sym is not None
        assert sym.file == "src/auth2.py"

    def test_index_directory(self):
        index = SymbolIndex()
        count = index.index_directory([
            ("src/auth.py", SAMPLE_AUTH, "src.auth"),
            ("src/utils.py", SAMPLE_UTILS, "src.utils"),
        ])
        assert count >= 10

    def test_syntax_error_handling(self):
        index = SymbolIndex()
        entries = index.index_file("bad.py", "def broken(:\n    pass\n", "bad")
        assert entries == []

    def test_find_functions(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        functions = index.find_functions()
        names = {f.name for f in functions}
        assert "validate_password" in names
        assert "authenticate" in names  # method is included
        assert "async_refresh" in names

    def test_find_classes(self):
        index = SymbolIndex()
        index.index_file("src/auth.py", SAMPLE_AUTH, "src.auth")

        classes = index.find_classes()
        assert len(classes) == 1
        assert classes[0].name == "AuthManager"
