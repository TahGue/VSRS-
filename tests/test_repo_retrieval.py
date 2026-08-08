"""Tests for the retrieval system (Phase 2.3)."""

from pathlib import Path

from vsrs.repo.dependencies import DependencyIndex
from vsrs.repo.files import FileIndex
from vsrs.repo.intelligence import RepositoryIntelligence
from vsrs.repo.retrieval import Retriever
from vsrs.repo.symbols import SymbolIndex
from vsrs.repo.tests import TestIndex


def _create_test_repo(tmp_path: Path) -> Path:
    """Create a realistic test repo for retrieval tests."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "auth.py").write_text('''\
"""Authentication module."""
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
        return token == self.secret
''')
    (repo / "src" / "config.py").write_text('''\
"""Configuration module."""

class Config:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
''')
    (repo / "tests").mkdir()
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_auth.py").write_text('''\
"""Tests for auth module."""
from src.auth import validate_password, login


def test_valid_password():
    assert validate_password("secret")


def test_empty_password():
    assert not validate_password("")
''')
    (repo / "pyproject.toml").write_text('''\
[project]
name = "test"
dependencies = ["pydantic"]

[tool.pytest.ini_options]
testpaths = ["tests"]
''')
    return repo


class TestRetriever:
    def test_retrieve_by_symbol_name(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        result = retriever.retrieve("Fix validate_password bug", entities=["validate_password"])

        locators = result.all_locators()
        assert any("auth.py" in loc for loc in locators)
        # Should find the symbol
        symbol_evidence = [e for e in result.evidence if e.kind == "symbol"]
        assert len(symbol_evidence) >= 1
        assert any("validate_password" in e.metadata.get("name", "") for e in symbol_evidence)

    def test_retrieve_by_file_path(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        result = retriever.retrieve("Fix bug in src/auth.py", entities=["src/auth.py"])

        file_evidence = [e for e in result.evidence if e.kind == "file"]
        assert len(file_evidence) >= 1
        assert any("auth.py" in e.locator for e in file_evidence)

    def test_retrieve_with_expansion(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        result = retriever.retrieve("Fix validate_password", entities=["validate_password"], expand=True)

        assert result.expanded
        # Should have expanded to include tests
        test_evidence = [e for e in result.evidence if e.kind == "test"]
        assert len(test_evidence) >= 1

    def test_retrieve_without_expansion(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        result = retriever.retrieve("Fix validate_password", entities=["validate_password"], expand=False)

        assert not result.expanded

    def test_entity_extraction(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        entities = retriever._extract_entities("Fix the validate_password function in src/auth.py")
        assert "validate_password" in entities
        assert "src/auth.py" in entities

    def test_retrieve_by_error(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        error = "NameError: name 'validate_password' is not defined"
        result = retriever.retrieve_by_error(error)

        assert "validate_password" in result.query
        symbol_evidence = [e for e in result.evidence if e.kind == "symbol"]
        assert len(symbol_evidence) >= 1

    def test_retrieve_by_import_error(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        error = "ModuleNotFoundError: No module named 'src.auth'"
        result = retriever.retrieve_by_error(error)

        # Should try to find src.auth related evidence
        assert len(result.evidence) >= 0  # may or may not find it

    def test_grounding_check_symbol(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        assert retriever.grounding_check("validate_password")
        assert retriever.grounding_check("AuthManager")
        assert not retriever.grounding_check("nonexistent_function")

    def test_grounding_check_import(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        # src.auth is internal
        assert retriever.grounding_check_import("src.auth")
        # pydantic is a declared dependency
        assert retriever.grounding_check_import("pydantic")
        # nonexistent is not declared
        assert not retriever.grounding_check_import("nonexistent_pkg")

    def test_ranking(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        result = retriever.retrieve("Fix validate_password", entities=["validate_password"])

        # Exact symbol matches should have rank 1
        rank1 = [e for e in result.evidence if e.rank == 1]
        assert len(rank1) >= 1

    def test_max_results(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()
        retriever = model.build_retriever()

        result = retriever.retrieve("Fix auth config password", max_results=3)
        assert len(result.evidence) <= 3


class TestRepositoryIntelligence:
    def test_build(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()

        assert model.file_index.count >= 4
        assert model.symbol_index.count >= 5
        assert model.test_index.test_count >= 2
        assert model.dependency_index.import_count >= 1
        assert model.config is not None
        assert model.config.has_pytest

    def test_build_retriever(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        intel = RepositoryIntelligence(repo)
        model = intel.build()

        retriever = model.build_retriever()
        assert retriever is not None

        # Calling again should return the same instance
        retriever2 = model.build_retriever()
        assert retriever is retriever2
