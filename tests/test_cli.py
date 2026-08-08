"""Tests for the CLI commands (Phase 9)."""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vsrs.cli import app
from vsrs.core.schemas import (
    FinalDecision,
    FinalStatus,
    PatchCandidate,
    RepositorySnapshot,
    ReviewFinding,
    FindingSeverity,
    RiskLevel,
    Task,
    TaskRun,
    TaskState,
    TaskType,
)
from vsrs.core.store import Store
from vsrs.provenance import EvidenceGraph, ProvenanceStore


runner = CliRunner()


def _create_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "auth.py").write_text("def validate_password(pw):\n    return bool(pw)\n")
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_auth.py").write_text(
        "from src.auth import validate_password\n\ndef test_valid():\n    assert validate_password('x')\n"
    )
    (repo / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


def _seed_store(tmp_path: Path) -> tuple[Store, str, str]:
    """Seed a store with a task, run, patch, finding, and decision."""
    db_path = str(tmp_path / "test.db")
    store = Store(db_path)

    repo_snapshot = RepositorySnapshot(
        id="repo_001",
        root="/tmp/test",
        commit_hash="abc123def456",
    )
    task = Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=TaskType.bugfix,
        instruction="Fix the empty password bug in validate_password",
        acceptance_criteria=["reject empty password"],
        risk_level=RiskLevel.low,
    )
    run = TaskRun(
        id="run_001",
        task_id="task_001",
        repo_snapshot_id="repo_001",
        state=TaskState.verified,
        attempt_no=1,
        max_attempts=3,
    )
    patch = PatchCandidate(
        id="patch_001",
        task_id="task_001",
        attempt_no=1,
        base_commit="abc123",
        diff="--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,2 +1,3 @@\n def validate_password(pw):\n-    return bool(pw)\n+    if not pw:\n+        return False\n+    return bool(pw)\n",
        changed_files=["src/auth.py"],
        assumptions=["empty password should be rejected"],
    )
    finding = ReviewFinding(
        id="finding_001",
        patch_id="patch_001",
        severity=FindingSeverity.minor,
        category="test_gap",
        text="No new targeted test for empty password case",
    )
    decision = FinalDecision(
        task_id="task_001",
        status=FinalStatus.verified_candidate,
        blockers=[],
        waived_gates=[],
        summary="Patch verified with minor finding about test coverage.",
        provenance_id="",
    )

    store.save_repository(repo_snapshot)
    store.save_task(task)
    store.save_run(run)
    store.save_patch(patch)
    store.save_finding(finding)
    store.save_final_decision(decision)

    # Add provenance edges
    prov = ProvenanceStore(store)
    graph = EvidenceGraph(prov)
    graph.link_run_to_task("run_001", "task_001")
    graph.link_run_to_patch("run_001", "patch_001")
    graph.link_patch_to_file("patch_001", "src/auth.py")
    graph.link_run_to_decision("run_001", "decision_task_001")

    store.close()
    return Store(db_path), "run_001", "task_001"


class TestCLIStatus:
    def test_status_existing_run(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["status", run_id])
        assert result.exit_code == 0
        assert run_id in result.stdout
        assert "verified" in result.stdout

    def test_status_nonexistent_run(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["status", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestCLIDiff:
    def test_diff_existing(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["diff", run_id])
        assert result.exit_code == 0
        assert "patch_001" in result.stdout
        assert "src/auth.py" in result.stdout

    def test_diff_no_patches(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test2.db")
        store = Store(db_path)
        run = TaskRun(id="run_002", task_id="task_002", repo_snapshot_id="repo_002")
        task = Task(id="task_002", repo_snapshot_id="repo_002", type=TaskType.bugfix, instruction="test")
        store.save_task(task)
        store.save_run(run)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", db_path)
        result = runner.invoke(app, ["diff", "run_002"])
        assert result.exit_code == 0
        assert "No patches" in result.stdout


class TestCLIAuditTrail:
    def test_audit_trail_with_edges(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["audit-trail", run_id])
        assert result.exit_code == 0
        assert "run:run_001" in result.stdout
        assert "task:task_001" in result.stdout

    def test_audit_trail_no_edges(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test2.db")
        store = Store(db_path)
        run = TaskRun(id="run_003", task_id="task_003", repo_snapshot_id="repo_003")
        task = Task(id="task_003", repo_snapshot_id="repo_003", type=TaskType.bugfix, instruction="test")
        store.save_task(task)
        store.save_run(run)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", db_path)
        result = runner.invoke(app, ["audit-trail", "run_003"])
        assert result.exit_code == 0
        assert "No provenance" in result.stdout

    def test_audit_trail_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["audit-trail", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestCLIHistory:
    def test_history_with_runs(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["history", task_id])
        assert result.exit_code == 0
        assert run_id in result.stdout
        assert "verified" in result.stdout

    def test_history_no_runs(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test2.db")
        store = Store(db_path)
        task = Task(id="task_004", repo_snapshot_id="repo_004", type=TaskType.bugfix, instruction="test")
        store.save_task(task)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", db_path)
        result = runner.invoke(app, ["history", "task_004"])
        assert result.exit_code == 0
        assert "No runs" in result.stdout

    def test_history_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["history", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestCLIReview:
    def test_review_with_findings(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["review", run_id])
        assert result.exit_code == 0
        assert "finding_001" in result.stdout
        assert "minor" in result.stdout
        assert "verified_candidate" in result.stdout

    def test_review_no_patches(self, tmp_path, monkeypatch):
        db_path = str(tmp_path / "test2.db")
        store = Store(db_path)
        run = TaskRun(id="run_005", task_id="task_005", repo_snapshot_id="repo_005")
        task = Task(id="task_005", repo_snapshot_id="repo_005", type=TaskType.bugfix, instruction="test")
        store.save_task(task)
        store.save_run(run)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", db_path)
        result = runner.invoke(app, ["review", "run_005"])
        assert result.exit_code == 0
        assert "No patches" in result.stdout

    def test_review_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["review", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestCLIReport:
    def test_report_to_stdout(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["report", run_id])
        assert result.exit_code == 0
        assert "VSRS Run Report" in result.stdout
        assert "task_001" in result.stdout
        assert "verified" in result.stdout
        assert "Provenance" in result.stdout

    def test_report_to_file(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        output_file = tmp_path / "report.md"
        result = runner.invoke(app, ["report", run_id, "--output", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "VSRS Run Report" in content
        assert run_id in content

    def test_report_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["report", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestCLIProvenance:
    def test_provenance_tree(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["provenance", run_id])
        assert result.exit_code == 0
        assert "run:run_001" in result.stdout

    def test_provenance_summary(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["provenance", run_id, "--format", "summary"])
        assert result.exit_code == 0
        assert "Edges:" in result.stdout
        assert "Nodes:" in result.stdout

    def test_provenance_json(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["provenance", run_id, "--format", "json"])
        assert result.exit_code == 0
        assert "executes" in result.stdout

    def test_provenance_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["provenance", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout


class TestCLIBenchmark:
    def test_benchmark_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["benchmark", "list"])
        assert result.exit_code == 0
        assert "Benchmark Tasks" in result.stdout

    def test_benchmark_save(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        output_dir = tmp_path / "benchmarks"
        result = runner.invoke(app, ["benchmark", "save", "--output", str(output_dir)])
        assert result.exit_code == 0
        assert "Saved" in result.stdout
        assert output_dir.exists()


class TestCLIExport:
    def test_export_json(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        result = runner.invoke(app, ["export", run_id, "--format", "json"])
        assert result.exit_code == 0
        assert run_id in result.stdout

    def test_export_jsonl_to_file(self, tmp_path, monkeypatch):
        store, run_id, task_id = _seed_store(tmp_path)
        store.close()

        monkeypatch.setenv("VSRS_DB_PATH", str(tmp_path / "test.db"))
        output_file = tmp_path / "export.jsonl"
        result = runner.invoke(app, ["export", run_id, "--output", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
        line = output_file.read_text().strip()
        data = json.loads(line)
        assert data["run_id"] == run_id
