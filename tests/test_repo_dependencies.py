"""Tests for the dependency index (Phase 2)."""

from pathlib import Path

from vsrs.repo.dependencies import DependencyIndex, ImportEdge, PackageDependency


SAMPLE_CODE = '''\
"""Test module."""

import os
import sys
from typing import Optional
from src.auth import validate_password
from src.utils.helpers import format_date

def do_something():
    validate_password("test")
    format_date()
'''


class TestDependencyIndex:
    def test_index_file_imports(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.auth", "src/auth.py")
        index.register_module("src.utils.helpers", "src/utils/helpers.py")

        edges = index.index_file_imports("src/main.py", SAMPLE_CODE)

        # Should have: os, sys, typing.Optional, src.auth, src.utils.helpers
        modules = {e.target_module for e in edges}
        assert "os" in modules
        assert "sys" in modules
        assert "typing" in modules
        assert "src.auth" in modules
        assert "src.utils.helpers" in modules

    def test_internal_vs_external(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.auth", "src/auth.py")

        edges = index.index_file_imports("src/main.py", SAMPLE_CODE)

        internal = [e for e in edges if not e.is_external]
        external = [e for e in edges if e.is_external]

        internal_modules = {e.target_module for e in internal}
        assert "src.auth" in internal_modules

        external_modules = {e.target_module for e in external}
        assert "os" in external_modules
        assert "sys" in external_modules

    def test_imports_of(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.auth", "src/auth.py")
        index.index_file_imports("src/main.py", SAMPLE_CODE)

        imports = index.imports_of("src/main.py")
        assert len(imports) >= 4

    def test_importers_of(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.auth", "src/auth.py")
        index.index_file_imports("src/main.py", SAMPLE_CODE)

        importers = index.importers_of("src.auth")
        assert len(importers) == 1
        assert importers[0].source_file == "src/main.py"

    def test_parse_pyproject_toml(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('''\
[project]
name = "test"
dependencies = ["pydantic>=2.0", "requests"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff"]
''')
        index = DependencyIndex(tmp_path)
        deps = index.parse_pyproject_toml(pyproject)

        names = {d.name for d in deps}
        assert "pydantic" in names
        assert "requests" in names
        assert "pytest" in names
        assert "ruff" in names

    def test_parse_requirements_txt(self, tmp_path):
        req = tmp_path / "requirements.txt"
        req.write_text("pydantic>=2.0\nrequests==2.31.0\n# comment\n-r other.txt\n")
        index = DependencyIndex(tmp_path)
        deps = index.parse_requirements_txt(req)

        assert len(deps) == 2
        assert deps[0].name == "pydantic"
        assert deps[1].name == "requests"

    def test_is_known_dependency(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "test"\ndependencies = ["pydantic"]\n')
        index = DependencyIndex(tmp_path)
        index.parse_pyproject_toml(pyproject)

        assert index.is_known_dependency("pydantic")
        assert not index.is_known_dependency("nonexistent")

    def test_impact_analysis(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.auth", "src/auth.py")
        index.register_module("src.main", "src/main.py")
        index.register_module("src.api", "src/api.py")

        # main imports auth, api imports main
        index.index_file_imports("src/main.py", "from src.auth import validate_password")
        index.index_file_imports("src/api.py", "from src.main import do_something")

        impacted = index.impact_analysis("src/auth.py")
        assert "src/main.py" in impacted
        assert "src/api.py" in impacted

    def test_relative_import(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.utils", "src/utils/__init__.py")
        index.register_module("src.utils.helpers", "src/utils/helpers.py")

        code = "from .helpers import format_date\n"
        edges = index.index_file_imports("src/utils/main.py", code)
        assert len(edges) == 1
        assert "src.utils.helpers" in edges[0].target_module

    def test_external_imports(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.auth", "src/auth.py")
        index.index_file_imports("src/main.py", SAMPLE_CODE)

        ext = index.external_imports()
        ext_modules = {e.target_module for e in ext}
        assert "os" in ext_modules
        assert "typing" in ext_modules

    def test_internal_imports(self, tmp_path):
        index = DependencyIndex(tmp_path)
        index.register_module("src.auth", "src/auth.py")
        index.index_file_imports("src/main.py", SAMPLE_CODE)

        internal = index.internal_imports()
        int_modules = {e.target_module for e in internal}
        assert "src.auth" in int_modules
