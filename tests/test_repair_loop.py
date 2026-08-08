"""Tests for the repair loop (Phase 5.2)."""

import subprocess
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
from vsrs.repair.loop import AttemptRecord, RepairLoop, RepairResult
from vsrs.verify.runner import VerificationConfig, VerificationRunner


def _create_test_repo(tmp_path: Path) -> Path:
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
        "def test_valid():\n    assert validate_password('secret')\n"
    )
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\n'
    )
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)
    return repo


def _make_task() -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=TaskType.bugfix,
        instruction="Fix the empty password bug",
        acceptance_criteria=["reject empty password"],
        risk_level=RiskLevel.low,
        required_gates=["syntax", "existing_tests"],
    )


def _make_patch(attempt: int = 1) -> PatchCandidate:
    return PatchCandidate(
        id=f"patch_{attempt:03d}",
        task_id="task_001",
        attempt_no=attempt,
        base_commit="abc123",
        diff="",
        changed_files=["src/auth.py"],
        assumptions=["The fix is correct"],
    )


def _make_failed_report(patch_id: str) -> VerificationReport:
    return VerificationReport(
        patch_id=patch_id,
        checks=[
            CheckResult(
                check_type="syntax",
                command="ast.parse",
                exit_code=0,
                status=CheckStatus.pass_,
            ),
            CheckResult(
                check_type="existing_tests",
                command="pytest",
                exit_code=1,
                status=CheckStatus.fail,
                error_message="test_valid: AssertionError: assert False",
            ),
        ],
        required_passed=False,
        blockers=["Required gate 'existing_tests' failed"],
        final_status=FinalStatus.needs_review,
    )


def _make_passed_report(patch_id: str) -> VerificationReport:
    return VerificationReport(
        patch_id=patch_id,
        checks=[
            CheckResult(
                check_type="syntax",
                command="ast.parse",
                exit_code=0,
                status=CheckStatus.pass_,
            ),
            CheckResult(
                check_type="existing_tests",
                command="pytest",
                exit_code=0,
                status=CheckStatus.pass_,
            ),
        ],
        required_passed=True,
        blockers=[],
        final_status=FinalStatus.verified_candidate,
    )


class TestRepairLoop:
    def test_initial_pass_no_repair_needed(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        task = _make_task()
        patch = _make_patch()
        report = _make_passed_report(patch.id)

        result = loop.run(task, patch, report, repo)

        assert result.succeeded
        assert result.total_attempts == 1
        assert result.final_status == FinalStatus.verified_candidate
        assert len(result.attempts) == 1
        assert result.attempts[0].passed

    def test_repair_loop_with_failures(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        task = _make_task()
        patch = _make_patch()
        report = _make_failed_report(patch.id)

        result = loop.run(task, patch, report, repo)

        # Should have made multiple attempts
        assert result.total_attempts > 1
        assert len(result.attempts) > 1
        # Each attempt should have a patch_id
        for attempt in result.attempts:
            assert attempt.patch_id

    def test_max_attempts_enforced(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        # Make the test fail so repair attempts won't pass
        (repo / "tests" / "test_auth.py").write_text(
            "from src.auth import validate_password\n\n"
            "def test_valid():\n    assert False  # always fails\n"
        )
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=2)

        task = _make_task()
        patch = _make_patch()
        report = _make_failed_report(patch.id)

        result = loop.run(task, patch, report, repo)

        assert result.total_attempts <= 2
        assert not result.succeeded
        assert result.final_status == FinalStatus.needs_review

    def test_attempt_records_track_failures(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        task = _make_task()
        patch = _make_patch()
        report = _make_failed_report(patch.id)

        result = loop.run(task, patch, report, repo)

        for attempt in result.attempts:
            assert isinstance(attempt, AttemptRecord)
            assert attempt.verification_report is not None
            if not attempt.passed:
                assert len(attempt.failures) > 0

    def test_build_repair_input(self):
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        task = _make_task()
        patch = _make_patch()

        from vsrs.reasoning.protocol import FailureSummary
        failures = [
            FailureSummary(
                check_type="existing_tests",
                status="fail",
                error_category="test_failure",
                error_message="test failed",
            ),
        ]

        repair_input = loop.build_repair_input(task, patch, failures, attempt_no=1)

        assert repair_input.task_instruction == task.instruction
        assert repair_input.prior_patch_diff == patch.diff
        assert repair_input.prior_attempt_no == 1
        assert len(repair_input.failures) == 1
        assert repair_input.remaining_attempts == 2

    def test_should_continue_true(self):
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        result = RepairResult(task_id="task_001", run_id="run_001", total_attempts=1)
        result.set_max_attempts(3)

        assert loop.should_continue(result)

    def test_should_continue_false_when_succeeded(self):
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        result = RepairResult(task_id="task_001", run_id="run_001", total_attempts=1, succeeded=True)
        result.set_max_attempts(3)

        assert not loop.should_continue(result)

    def test_should_continue_false_when_max_reached(self):
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        result = RepairResult(task_id="task_001", run_id="run_001", total_attempts=3)
        result.set_max_attempts(3)

        assert not loop.should_continue(result)

    def test_repair_output_in_attempt_record(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        task = _make_task()
        patch = _make_patch()
        report = _make_failed_report(patch.id)

        result = loop.run(task, patch, report, repo)

        # Repair attempts (attempt 2+) should have repair_output
        repair_attempts = [a for a in result.attempts if a.attempt_no > 1]
        for attempt in repair_attempts:
            assert attempt.repair_output is not None
            assert attempt.repair_output.failure_analysis

    def test_final_report_set(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        runner = VerificationRunner(
            config=VerificationConfig(run_lint=False, run_type_check=False, run_security=False),
        )
        loop = RepairLoop(verification_runner=runner, max_attempts=3)

        task = _make_task()
        patch = _make_patch()
        report = _make_failed_report(patch.id)

        result = loop.run(task, patch, report, repo)

        assert result.final_report is not None
