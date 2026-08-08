"""Tests for multi-language support (Phase 17)."""

import pytest
from pathlib import Path

from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    FinalStatus,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskType,
    VerificationReport,
)
from vsrs.languages import (
    GoAdapter,
    JavaAdapter,
    LanguageAdapter,
    LanguageInfo,
    LanguageRegistry,
    PythonAdapter,
    RustAdapter,
    TypeScriptAdapter,
    detect_language,
    get_registry,
)
from vsrs.verify.multilang import MultiLanguageVerificationRunner


# --- Helpers ---

def _make_patch(changed_files: list[str], diff: str = "") -> PatchCandidate:
    return PatchCandidate(
        id="patch_001",
        task_id="task_001",
        attempt_no=1,
        base_commit="abc123",
        diff=diff,
        changed_files=changed_files,
        changed_symbols=[],
        assumptions=[],
        predicted_effects=[],
        falsification_checks=[],
    )


def _make_task(required_gates: list[str] | None = None) -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=TaskType.bugfix,
        instruction="Fix a bug",
        acceptance_criteria=["test passes"],
        risk_level=RiskLevel.low,
        required_gates=required_gates or ["syntax", "build", "existing_tests"],
    )


# --- Language Info Tests ---

class TestLanguageInfo:
    def test_creation(self):
        info = LanguageInfo(
            name="python",
            file_extensions=[".py"],
            display_name="Python",
        )
        assert info.name == "python"
        assert info.file_extensions == [".py"]
        assert info.display_name == "Python"

    def test_defaults(self):
        info = LanguageInfo(name="go", file_extensions=[".go"])
        assert info.build_tool == ""
        assert info.test_framework == ""
        assert info.linter == ""


# --- Adapter Info Tests ---

class TestAdapterInfo:
    def test_python_info(self):
        adapter = PythonAdapter()
        assert adapter.info.name == "python"
        assert ".py" in adapter.info.file_extensions
        assert adapter.info.test_framework == "pytest"

    def test_go_info(self):
        adapter = GoAdapter()
        assert adapter.info.name == "go"
        assert ".go" in adapter.info.file_extensions
        assert adapter.info.build_tool == "go build"

    def test_rust_info(self):
        adapter = RustAdapter()
        assert adapter.info.name == "rust"
        assert ".rs" in adapter.info.file_extensions
        assert adapter.info.build_tool == "cargo build"

    def test_typescript_info(self):
        adapter = TypeScriptAdapter()
        assert adapter.info.name == "typescript"
        assert ".ts" in adapter.info.file_extensions
        assert ".tsx" in adapter.info.file_extensions

    def test_java_info(self):
        adapter = JavaAdapter()
        assert adapter.info.name == "java"
        assert ".java" in adapter.info.file_extensions
        assert "mvn" in adapter.info.build_tool


# --- File Matching Tests ---

class TestFileMatching:
    def test_python_matches(self):
        adapter = PythonAdapter()
        assert adapter.matches_files(["main.py", "test.py"])
        assert not adapter.matches_files(["main.go"])

    def test_go_matches(self):
        adapter = GoAdapter()
        assert adapter.matches_files(["main.go"])
        assert not adapter.matches_files(["main.py"])

    def test_rust_matches(self):
        adapter = RustAdapter()
        assert adapter.matches_files(["main.rs"])
        assert not adapter.matches_files(["main.py"])

    def test_typescript_matches(self):
        adapter = TypeScriptAdapter()
        assert adapter.matches_files(["index.ts"])
        assert adapter.matches_files(["component.tsx"])
        assert not adapter.matches_files(["main.py"])

    def test_java_matches(self):
        adapter = JavaAdapter()
        assert adapter.matches_files(["Main.java"])
        assert not adapter.matches_files(["main.py"])

    def test_filter_files(self):
        adapter = PythonAdapter()
        files = ["main.py", "test.py", "main.go", "README.md"]
        filtered = adapter.filter_files(files)
        assert "main.py" in filtered
        assert "test.py" in filtered
        assert "main.go" not in filtered

    def test_filter_empty(self):
        adapter = GoAdapter()
        assert adapter.filter_files(["main.py", "test.py"]) == []


# --- Detection Tests ---

class TestDetection:
    def test_python_detect_with_py_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        adapter = PythonAdapter()
        assert adapter.detect(tmp_path) is True

    def test_python_detect_no_py_files(self, tmp_path):
        (tmp_path / "main.go").write_text("package main")
        adapter = PythonAdapter()
        assert adapter.detect(tmp_path) is False

    def test_python_detect_empty_dir(self, tmp_path):
        adapter = PythonAdapter()
        assert adapter.detect(tmp_path) is False

    def test_go_detect_with_mod(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test")
        adapter = GoAdapter()
        assert adapter.detect(tmp_path) is True

    def test_go_detect_with_go_files(self, tmp_path):
        (tmp_path / "main.go").write_text("package main")
        adapter = GoAdapter()
        assert adapter.detect(tmp_path) is True

    def test_go_detect_no_go_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        adapter = GoAdapter()
        assert adapter.detect(tmp_path) is False

    def test_rust_detect_with_cargo(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]")
        adapter = RustAdapter()
        assert adapter.detect(tmp_path) is True

    def test_rust_detect_with_rs_files(self, tmp_path):
        (tmp_path / "main.rs").write_text("fn main() {}")
        adapter = RustAdapter()
        assert adapter.detect(tmp_path) is True

    def test_typescript_detect_with_tsconfig(self, tmp_path):
        (tmp_path / "tsconfig.json").write_text("{}")
        adapter = TypeScriptAdapter()
        assert adapter.detect(tmp_path) is True

    def test_typescript_detect_with_ts_files(self, tmp_path):
        (tmp_path / "index.ts").write_text("console.log('hello')")
        adapter = TypeScriptAdapter()
        assert adapter.detect(tmp_path) is True

    def test_java_detect_with_pom(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project></project>")
        adapter = JavaAdapter()
        assert adapter.detect(tmp_path) is True

    def test_java_detect_with_gradle(self, tmp_path):
        (tmp_path / "build.gradle").write_text("plugins {}")
        adapter = JavaAdapter()
        assert adapter.detect(tmp_path) is True

    def test_java_detect_with_java_files(self, tmp_path):
        (tmp_path / "Main.java").write_text("class Main {}")
        adapter = JavaAdapter()
        assert adapter.detect(tmp_path) is True


# --- Registry Tests ---

class TestLanguageRegistry:
    def test_register_and_get(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        assert reg.count() == 1
        assert reg.get("python") is not None
        assert reg.get("go") is None

    def test_register_duplicate_raises(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(PythonAdapter())

    def test_unregister(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        removed = reg.unregister("python")
        assert removed is not None
        assert reg.count() == 0

    def test_unregister_not_found(self):
        reg = LanguageRegistry()
        assert reg.unregister("nonexistent") is None

    def test_all(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        reg.register(GoAdapter())
        all_adapters = reg.all()
        assert "python" in all_adapters
        assert "go" in all_adapters

    def test_names(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        reg.register(GoAdapter())
        names = reg.names()
        assert "python" in names
        assert "go" in names

    def test_clear(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        reg.clear()
        assert reg.count() == 0

    def test_detect_for_files(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        reg.register(GoAdapter())
        adapters = reg.detect_for_files(["main.py", "test.py"])
        assert len(adapters) == 1
        assert adapters[0].info.name == "python"

    def test_detect_for_files_multiple_languages(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        reg.register(GoAdapter())
        adapters = reg.detect_for_files(["main.py", "main.go"])
        assert len(adapters) == 2

    def test_detect_for_files_no_match(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        adapters = reg.detect_for_files(["main.go"])
        assert len(adapters) == 0

    def test_detect_for_repo(self, tmp_path):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        reg.register(GoAdapter())
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "main.go").write_text("package main")
        adapters = reg.detect_for_repo(tmp_path)
        names = [a.info.name for a in adapters]
        assert "python" in names
        assert "go" in names

    def test_get_adapter_for_file(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        reg.register(GoAdapter())
        adapter = reg.get_adapter_for_file("main.py")
        assert adapter is not None
        assert adapter.info.name == "python"

    def test_get_adapter_for_file_no_match(self):
        reg = LanguageRegistry()
        reg.register(PythonAdapter())
        assert reg.get_adapter_for_file("main.go") is None


# --- Global Registry Tests ---

class TestGlobalRegistry:
    def test_get_registry_returns_same_instance(self):
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2

    def test_global_registry_has_all_languages(self):
        reg = get_registry()
        assert "python" in reg.names()
        assert "go" in reg.names()
        assert "rust" in reg.names()
        assert "typescript" in reg.names()
        assert "java" in reg.names()

    def test_detect_language(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hello')")
        adapters = detect_language(tmp_path)
        assert len(adapters) >= 1
        assert any(a.info.name == "python" for a in adapters)


# --- Python Adapter Functional Tests ---

class TestPythonAdapter:
    def test_syntax_check_valid(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        adapter = PythonAdapter()
        result = adapter.syntax_check(tmp_path, ["main.py"])
        assert result.check_type == "syntax"
        assert result.status == CheckStatus.pass_

    def test_syntax_check_invalid(self, tmp_path):
        (tmp_path / "main.py").write_text("def foo(:\n")
        adapter = PythonAdapter()
        result = adapter.syntax_check(tmp_path, ["main.py"])
        assert result.status == CheckStatus.fail
        assert "main.py" in result.error_message

    def test_syntax_check_file_not_found(self, tmp_path):
        adapter = PythonAdapter()
        result = adapter.syntax_check(tmp_path, ["nonexistent.py"])
        assert result.status == CheckStatus.fail
        assert "not found" in result.error_message.lower()

    def test_syntax_check_no_py_files(self, tmp_path):
        adapter = PythonAdapter()
        result = adapter.syntax_check(tmp_path, ["main.go"])
        assert result.status == CheckStatus.pass_  # no .py files to check

    def test_build_valid(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        adapter = PythonAdapter()
        result = adapter.build(tmp_path)
        assert result.check_type == "build"
        assert result.status == CheckStatus.pass_

    def test_build_invalid(self, tmp_path):
        (tmp_path / "main.py").write_text("def foo(:\n")
        adapter = PythonAdapter()
        result = adapter.build(tmp_path)
        assert result.status == CheckStatus.fail

    def test_lint_no_py_files(self, tmp_path):
        adapter = PythonAdapter()
        result = adapter.lint(tmp_path, ["main.go"])
        assert result.status == CheckStatus.skip

    def test_type_check_no_py_files(self, tmp_path):
        adapter = PythonAdapter()
        result = adapter.type_check(tmp_path, ["main.go"])
        assert result.status == CheckStatus.skip


# --- Multi-Language Verification Runner Tests ---

class TestMultiLanguageVerificationRunner:
    def test_detect_languages(self):
        runner = MultiLanguageVerificationRunner()
        langs = runner.detect_languages(["main.py", "test.py"])
        assert "python" in langs

    def test_detect_languages_multiple(self):
        runner = MultiLanguageVerificationRunner()
        langs = runner.detect_languages(["main.py", "main.go"])
        assert "python" in langs
        assert "go" in langs

    def test_detect_languages_none(self):
        runner = MultiLanguageVerificationRunner()
        langs = runner.detect_languages(["README.md", "config.yaml"])
        assert len(langs) == 0

    def test_verify_python_syntax_pass(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        runner = MultiLanguageVerificationRunner()
        patch = _make_patch(["main.py"])
        task = _make_task()
        report = runner.verify(patch, task, tmp_path, ["main.py"])
        assert isinstance(report, VerificationReport)
        # Should have syntax, build, tests, lint, type_check for python
        check_types = [c.check_type for c in report.checks]
        assert "syntax" in check_types
        assert "build" in check_types

    def test_verify_python_syntax_fail(self, tmp_path):
        (tmp_path / "main.py").write_text("def foo(:\n")
        runner = MultiLanguageVerificationRunner()
        patch = _make_patch(["main.py"])
        task = _make_task()
        report = runner.verify(patch, task, tmp_path, ["main.py"])
        syntax_check = next(
            c for c in report.checks if c.check_type == "syntax"
        )
        assert syntax_check.status == CheckStatus.fail

    def test_verify_no_language_detected(self, tmp_path):
        (tmp_path / "README.md").write_text("# Project")
        runner = MultiLanguageVerificationRunner()
        patch = _make_patch(["README.md"])
        task = _make_task()
        report = runner.verify(patch, task, tmp_path, ["README.md"])
        assert isinstance(report, VerificationReport)
        # Should have a skip result
        assert any(c.status == CheckStatus.skip for c in report.checks)

    def test_verify_multiple_languages(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        (tmp_path / "main.go").write_text("package main\n")
        runner = MultiLanguageVerificationRunner()
        patch = _make_patch(["main.py", "main.go"])
        task = _make_task()
        report = runner.verify(patch, task, tmp_path, ["main.py", "main.go"])
        # Should have checks from both python and go adapters
        assert len(report.checks) >= 10  # 5 checks x 2 languages

    def test_verify_empty_changed_files(self, tmp_path):
        (tmp_path / "main.py").write_text("x = 1\n")
        runner = MultiLanguageVerificationRunner()
        patch = _make_patch([])
        task = _make_task()
        report = runner.verify(patch, task, tmp_path, [])
        assert isinstance(report, VerificationReport)
