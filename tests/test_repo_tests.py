"""Tests for the test index and config discovery (Phase 2.2)."""

from pathlib import Path

from vsrs.repo.tests import ProjectConfig, TestEntry, TestIndex


SAMPLE_TEST = '''\
"""Test auth module."""
import pytest
from src.auth import validate_password

def test_valid_password():
    assert validate_password("secret")

def test_empty_password():
    assert not validate_password("")

@pytest.mark.slow
def test_many_attempts():
    for i in range(100):
        assert validate_password("pass")

class TestAuthManager:
    def test_authenticate(self):
        pass

async def test_async_login():
    pass
'''

INTEGRATION_TEST = '''\
def test_integration_login():
    pass
'''


class TestTestIndex:
    def test_discover_tests(self, tmp_path):
        index = TestIndex(tmp_path)
        entries = index.discover_tests([
            ("tests/test_auth.py", SAMPLE_TEST),
        ])

        names = {e.name for e in entries}
        assert "test_valid_password" in names
        assert "test_empty_password" in names
        assert "test_many_attempts" in names
        assert "test_authenticate" in names
        assert "test_async_login" in names

    def test_test_count(self, tmp_path):
        index = TestIndex(tmp_path)
        index.discover_tests([("tests/test_auth.py", SAMPLE_TEST)])
        assert index.test_count == 5

    def test_target_module(self, tmp_path):
        index = TestIndex(tmp_path)
        entries = index.discover_tests([("tests/test_auth.py", SAMPLE_TEST)])

        for e in entries:
            assert e.target_module == "auth"

    def test_async_test(self, tmp_path):
        index = TestIndex(tmp_path)
        entries = index.discover_tests([("tests/test_auth.py", SAMPLE_TEST)])

        async_tests = [e for e in entries if e.is_async]
        assert len(async_tests) == 1
        assert async_tests[0].name == "test_async_login"

    def test_markers(self, tmp_path):
        index = TestIndex(tmp_path)
        entries = index.discover_tests([("tests/test_auth.py", SAMPLE_TEST)])

        marked = [e for e in entries if "slow" in e.markers]
        assert len(marked) == 1
        assert marked[0].name == "test_many_attempts"

    def test_test_classification(self, tmp_path):
        index = TestIndex(tmp_path)
        entries = index.discover_tests([
            ("tests/test_auth.py", SAMPLE_TEST),
            ("tests/integration/test_login.py", INTEGRATION_TEST),
        ])

        unit_tests = [e for e in entries if e.test_type == "unit"]
        integration_tests = [e for e in entries if e.test_type == "integration"]
        assert len(unit_tests) >= 5
        assert len(integration_tests) >= 1

    def tests_in_file(self, tmp_path):
        index = TestIndex(tmp_path)
        index.discover_tests([("tests/test_auth.py", SAMPLE_TEST)])
        tests = index.tests_in_file("tests/test_auth.py")
        assert len(tests) == 5

    def test_find_by_name(self, tmp_path):
        index = TestIndex(tmp_path)
        index.discover_tests([("tests/test_auth.py", SAMPLE_TEST)])
        test = index.find_by_name("test_empty_password")
        assert test is not None
        assert test.name == "test_empty_password"

    def test_tests_for_module(self, tmp_path):
        index = TestIndex(tmp_path)
        index.discover_tests([("tests/test_auth.py", SAMPLE_TEST)])
        tests = index.tests_for_module("auth")
        assert len(tests) == 5

    def test_tests_by_type(self, tmp_path):
        index = TestIndex(tmp_path)
        index.discover_tests([
            ("tests/test_auth.py", SAMPLE_TEST),
            ("tests/integration/test_login.py", INTEGRATION_TEST),
        ])
        unit = index.tests_by_type("unit")
        integration = index.tests_by_type("integration")
        assert len(unit) >= 5
        assert len(integration) >= 1

    def test_is_test_file(self, tmp_path):
        index = TestIndex(tmp_path)
        assert index._is_test_file("tests/test_auth.py")
        assert index._is_test_file("conftest.py")
        assert not index._is_test_file("src/auth.py")


class TestConfigDiscovery:
    def test_pyproject_config(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('''\
[project]
name = "test"
requires-python = ">=3.12"

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["slow: slow tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
strict = true
''')
        index = TestIndex(tmp_path)
        config = index.discover_config()

        assert config.has_pytest
        assert config.test_dir == "tests"
        assert config.has_ruff
        assert config.has_mypy
        assert config.python_version == ">=3.12"
        assert config.config_source == "pyproject.toml"

    def test_pytest_ini(self, tmp_path):
        (tmp_path / "pytest.ini").write_text('''\
[pytest]
testpaths = tests
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests
''')
        index = TestIndex(tmp_path)
        config = index.discover_config()

        assert config.has_pytest
        assert config.test_dir == "tests"
        assert "slow" in config.pytest_markers
        assert "integration" in config.pytest_markers

    def test_makefile(self, tmp_path):
        (tmp_path / "Makefile").write_text('''\
test:
\tpytest -v

lint:
\truff check src/

build:
\tpip install -e .
''')
        index = TestIndex(tmp_path)
        config = index.discover_config()

        assert config.test_command == "pytest -v"
        assert config.lint_command == "ruff check src/"
        assert config.build_command == "pip install -e ."

    def test_defaults(self, tmp_path):
        index = TestIndex(tmp_path)
        config = index.discover_config()

        assert config.test_command == "pytest"  # default

    def test_requirements_detection(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("pytest\nruff\nmypy\n")
        index = TestIndex(tmp_path)
        config = index.discover_config()

        assert config.has_pytest
        assert config.has_ruff
        assert config.has_mypy
