"""Tests for the verification runner (Phase 4.1, 4.6)."""

import subprocess
from pathlib import Path

import pytest

from vsrs.core.schemas import (
    CheckStatus,
    FinalStatus,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskType,
)
from vsrs.verify.runner import VerificationConfig, VerificationRunner


def _create_test_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with a passing test."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)

    (repo / "src").mkdir(parents=True)
    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "auth.py").write_text(
        "def validate_password(pw: str) -> bool:\n"
        "    return bool(pw)\n"
    )
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_auth.py").write_text(
        "from src.auth import validate_password\n\n"
        "def test_valid_password():\n"
        "    assert validate_password('secret')\n"
    )
    (repo / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        "pythonpath = [\".\"]\n"
    )
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)
    return repo


def _make_patch(patch_id: str = "patch_001", changed_files: list[str] | None = None) -> PatchCandidate:
    return PatchCandidate(
        id=patch_id,
        task_id="task_001",
        attempt_no=1,
        base_commit="abc123",
        diff="",
        changed_files=changed_files or ["src/auth.py"],
    )


def _make_task(
    task_type: TaskType = TaskType.bugfix,
    risk_level: RiskLevel = RiskLevel.low,
    required_gates: list[str] | None = None,
) -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=task_type,
        instruction="Fix the empty password bug",
        acceptance_criteria=["reject empty password"],
        risk_level=risk_level,
        required_gates=required_gates or ["syntax", "existing_tests"],
    )


class TestVerificationRunner:
    def test_verify_clean_repo(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch()
        task = _make_task()

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        assert report.patch_id == "patch_001"
        assert len(report.checks) >= 5  # syntax, existing_tests, new_targeted_tests, lint, type_check, security, dep
        # syntax should pass
        syntax = [c for c in report.checks if c.check_type == "syntax"][0]
        assert syntax.status == CheckStatus.pass_

    def test_syntax_check_detects_error(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        # Introduce a syntax error
        (repo / "src" / "auth.py").write_text(
            "def validate_password(pw: str) -> bool:\n"
            "    return bool(pw\n"  # missing closing paren
        )
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch()
        task = _make_task()

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        syntax = [c for c in report.checks if c.check_type == "syntax"][0]
        assert syntax.status == CheckStatus.fail
        assert "auth.py" in syntax.error_message

    def test_required_gates_evaluation(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch()
        task = _make_task(required_gates=["syntax", "existing_tests"])

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        # With a clean repo, required gates should pass
        assert report.required_passed
        assert len(report.blockers) == 0
        assert report.final_status == FinalStatus.verified_candidate

    def test_required_gates_failure(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        # Introduce syntax error so syntax gate fails
        (repo / "src" / "auth.py").write_text("def broken(:\n    pass\n")
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch()
        task = _make_task(required_gates=["syntax"])

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        assert not report.required_passed
        assert any("syntax" in b for b in report.blockers)
        assert report.final_status == FinalStatus.needs_review

    def test_missing_required_gate(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch()
        task = _make_task(required_gates=["nonexistent_gate"])

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        assert not report.required_passed
        assert any("nonexistent_gate" in b for b in report.blockers)

    def test_new_test_files_detected(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        # Add a new test file
        (repo / "tests" / "test_new.py").write_text(
            "def test_new():\n    assert True\n"
        )
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch(changed_files=["src/auth.py", "tests/test_new.py"])
        task = _make_task()

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py", "tests/test_new.py"])

        targeted = [c for c in report.checks if c.check_type == "new_targeted_tests"][0]
        assert targeted.status != CheckStatus.skip

    def test_no_new_tests_skipped(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch(changed_files=["src/auth.py"])
        task = _make_task()

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        targeted = [c for c in report.checks if c.check_type == "new_targeted_tests"][0]
        assert targeted.status == CheckStatus.skip

    def test_select_gates(self):
        runner = VerificationRunner()
        gates = runner.select_gates(
            task_type=TaskType.security,
            risk_level=RiskLevel.high,
        )

        assert "security_scan" in gates
        assert "static_analysis" in gates
        assert gates["security_scan"] == "mandatory"

    def test_select_gates_bugfix(self):
        runner = VerificationRunner()
        gates = runner.select_gates(
            task_type=TaskType.bugfix,
            risk_level=RiskLevel.low,
        )

        assert "syntax" in gates
        assert "existing_tests" in gates
        assert "new_targeted_tests" in gates

    def test_dependency_validation_pass(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch()
        task = _make_task()

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        dep = [c for c in report.checks if c.check_type == "dependency_validation"][0]
        assert dep.status == CheckStatus.pass_

    def test_all_check_types_present(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
            ),
        )
        patch = _make_patch()
        task = _make_task()

        report = runner.verify(patch, task, repo, changed_files=["src/auth.py"])

        check_types = {c.check_type for c in report.checks}
        assert "syntax" in check_types
        assert "existing_tests" in check_types
        assert "new_targeted_tests" in check_types
        assert "dependency_validation" in check_types
