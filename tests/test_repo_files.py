"""Tests for the file index (Phase 2.0)."""

from pathlib import Path

from vsrs.repo.files import FileEntry, FileIndex, Language


def _create_repo(tmp_path: Path) -> Path:
    """Create a small test repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "auth.py").write_text("def validate_password(pw: str) -> bool:\n    return bool(pw)\n")
    (repo / "src" / "utils").mkdir()
    (repo / "src" / "utils" / "__init__.py").write_text("")
    (repo / "src" / "utils" / "helpers.py").write_text("def helper():\n    pass\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_auth.py").write_text("def test_auth():\n    pass\n")
    (repo / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    # Non-source files should be ignored
    (repo / "README.md").write_text("# Test")
    return repo


class TestFileIndex:
    def test_index(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        entries = index.index()

        paths = {e.path for e in entries}
        assert "src/auth.py" in paths
        assert "src/utils/helpers.py" in paths
        assert "tests/test_auth.py" in paths
        assert "src/__init__.py" in paths
        # Non-Python files should be excluded
        assert "README.md" not in paths
        assert "pyproject.toml" not in paths

    def test_count(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        assert index.count == 5  # auth, helpers, test_auth, __init__ x2

    def test_get(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        entry = index.get("src/auth.py")
        assert entry is not None
        assert entry.language == Language.python
        assert entry.size > 0
        assert len(entry.hash) == 64

    def test_by_language(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        py_files = index.by_language(Language.python)
        assert len(py_files) == 5

    def test_by_module(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        auth_files = index.by_module("src.auth")
        assert len(auth_files) == 1
        assert auth_files[0].path == "src/auth.py"

    def test_find_by_name(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        matches = index.find_by_name("auth")
        paths = {m.path for m in matches}
        assert "src/auth.py" in paths
        assert "tests/test_auth.py" in paths

    def test_has_changed(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        entry = index.get("src/auth.py")
        assert not index.has_changed("src/auth.py", entry.hash)
        assert index.has_changed("src/auth.py", "different_hash")
        assert index.has_changed("nonexistent.py", "any_hash")

    def test_module_path_conversion(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        entry = index.get("src/utils/helpers.py")
        assert entry.module == "src.utils.helpers"

    def test_init_module(self, tmp_path):
        repo = _create_repo(tmp_path)
        index = FileIndex(repo)
        index.index()
        entry = index.get("src/__init__.py")
        assert entry.module == "src"

    def test_skip_dirs(self, tmp_path):
        repo = _create_repo(tmp_path)
        # Create a __pycache__ dir with a .pyc file
        pycache = repo / "src" / "__pycache__"
        pycache.mkdir()
        (pycache / "auth.cpython-312.pyc").write_text("binary")
        index = FileIndex(repo)
        entries = index.index()
        paths = {e.path for e in entries}
        assert not any("__pycache__" in p for p in paths)
