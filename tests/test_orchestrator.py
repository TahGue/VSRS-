"""Tests for the orchestrator (Phase 7)."""

import subprocess
from pathlib import Path

import pytest

from vsrs.core.schemas import (
    FinalStatus,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskState,
    TaskType,
)
from vsrs.orchestrator import Orchestrator, OrchestratorConfig, PipelineResult


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
        instruction="Fix the empty password bug in auth validate_password",
        acceptance_criteria=["reject empty password"],
        risk_level=RiskLevel.low,
        required_gates=["syntax", "existing_tests"],
    )


class TestOrchestrator:
    def test_full_pipeline_clean_repo(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
                max_repair_attempts=2,
            ),
        )

        result = orchestrator.run(task, repo)

        assert isinstance(result, PipelineResult)
        assert len(result.stages) >= 6  # intake, retrieve, reason, patch, verify, review
        assert result.run.state in (TaskState.verified, TaskState.needs_review, TaskState.rejected)

    def test_intake_stage(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        intake_stage = [s for s in result.stages if s.stage == "intake"][0]
        assert intake_stage.success
        assert intake_stage.state == TaskState.retrieving

    def test_retrieve_stage(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        retrieve_stage = [s for s in result.stages if s.stage == "retrieve"][0]
        assert retrieve_stage.success
        assert retrieve_stage.data.get("evidence_count", 0) > 0

    def test_reason_stage(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        reason_stage = [s for s in result.stages if s.stage == "reason"][0]
        assert reason_stage.success
        assert result.reasoning_output is not None
        assert result.reasoning_output.patch_proposal is not None

    def test_patch_stage(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        patch_stage = [s for s in result.stages if s.stage == "patch"][0]
        assert patch_stage.success
        assert result.patch is not None
        assert result.patch.task_id == task.id

    def test_verify_stage(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        verify_stage = [s for s in result.stages if s.stage == "verify"][0]
        assert verify_stage.success
        assert result.verification_report is not None
        assert len(result.verification_report.checks) > 0

    def test_review_stage(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        review_stage = [s for s in result.stages if s.stage == "review"][0]
        assert review_stage.success
        assert result.critic_report is not None
        assert result.final_decision is not None

    def test_final_decision_set(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        assert result.final_decision is not None
        assert result.run.final_decision is not None
        assert result.final_decision.task_id == task.id

    def test_pipeline_result_tracks_stages(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        stage_names = [s.stage for s in result.stages]
        assert "intake" in stage_names
        assert "retrieve" in stage_names
        assert "reason" in stage_names
        assert "patch" in stage_names
        assert "verify" in stage_names
        assert "review" in stage_names

    def test_total_duration(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        assert result.total_duration > 0

    def test_nonexistent_repo_fails(self, tmp_path):
        task = _make_task()
        orchestrator = Orchestrator()

        result = orchestrator.run(task, tmp_path / "nonexistent")

        assert not result.succeeded
        assert result.run.state == TaskState.failed
        intake_stage = result.stages[0]
        assert not intake_stage.success
        assert "does not exist" in intake_stage.error

    def test_repair_stage_appears_when_verification_fails(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        # Make existing tests fail
        (repo / "tests" / "test_auth.py").write_text(
            "from src.auth import validate_password\n\n"
            "def test_valid():\n    assert False  # always fails\n"
        )
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(
                run_lint=False,
                run_type_check=False,
                run_security=False,
                max_repair_attempts=2,
            ),
        )

        result = orchestrator.run(task, repo)

        stage_names = [s.stage for s in result.stages]
        assert "repair" in stage_names
        assert result.repair_result is not None

    def test_run_state_transitions_correctly(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        # Final state should be a terminal/result state
        assert result.run.state in (
            TaskState.verified,
            TaskState.rejected,
            TaskState.needs_review,
            TaskState.failed,
        )

    def test_finished_at_set(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        assert result.run.finished_at is not None
