"""Tests for the VSRS REST API (Phase 11)."""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vsrs.api.app import create_app
from vsrs.api.deps import get_config, get_store
from vsrs.core.config import VSRSConfig
from vsrs.core.schemas import (
    FinalDecision,
    FinalStatus,
    PatchCandidate,
    RepositorySnapshot,
    ReviewFinding,
    FindingSeverity,
    Task,
    TaskRun,
    TaskState,
    TaskType,
    RiskLevel,
)
from vsrs.core.store import Store
from vsrs.provenance import EvidenceGraph, ProvenanceStore


def _create_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    (repo / "README.md").write_text("# Test Repo\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
    return repo


def _seed_store(db_path: str) -> tuple[str, str]:
    """Seed a store and return (run_id, task_id)."""
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
        instruction="Fix the empty password bug",
        acceptance_criteria=["reject empty password"],
        risk_level=RiskLevel.low,
    )
    run = TaskRun(
        id="run_001",
        task_id="task_001",
        repo_snapshot_id="repo_001",
        state=TaskState.verified,
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
        summary="Patch verified with minor finding.",
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

    store.close()
    return "run_001", "task_001"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a test client with an isolated database."""
    db_path = str(tmp_path / "test_api.db")
    monkeypatch.setenv("VSRS_DB_PATH", db_path)

    # Clear cached config
    get_config.cache_clear()

    app = create_app()

    # Override get_store to use our test db
    def override_get_store():
        config = get_config()
        store = Store(config.database.url)
        try:
            yield store
        finally:
            store.close()

    from fastapi import Depends
    app.dependency_overrides[get_store] = override_get_store

    client = TestClient(app)
    client._db_path = db_path  # type: ignore
    yield client

    app.dependency_overrides.clear()
    get_config.cache_clear()


class TestHealth:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_docs(self, client):
        response = client.get("/docs")
        assert response.status_code == 200
        assert "VSRS API" in response.text


class TestRuns:
    def test_create_run(self, client, tmp_path):
        repo = _create_test_repo(tmp_path)
        response = client.post("/api/v1/runs", json={
            "repo_path": str(repo),
            "task_instruction": "Fix a bug",
            "task_type": "bugfix",
            "risk": "low",
            "acceptance_criteria": ["test passes"],
        })
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data
        assert "task_id" in data
        # Pipeline now executes synchronously — state should be past intake
        assert data["state"] in ("intake", "needs_review", "verified", "rejected", "failed")

    def test_create_run_nonexistent_repo(self, client):
        response = client.post("/api/v1/runs", json={
            "repo_path": "/nonexistent/path",
            "task_instruction": "Fix a bug",
        })
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    def test_get_run(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["state"] == "verified"

    def test_get_run_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent")
        assert response.status_code == 404

    def test_list_runs(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get("/api/v1/runs")
        assert response.status_code == 200
        data = response.json()
        assert "runs" in data
        assert "total" in data
        assert data["total"] >= 1
        assert any(r["run_id"] == run_id for r in data["runs"])

    def test_list_runs_pagination(self, client):
        _seed_store(client._db_path)
        response = client.get("/api/v1/runs?offset=0&limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["runs"]) <= 1
        assert data["limit"] == 1
        assert data["offset"] == 0

    def test_get_run_task(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/task")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "task_001"
        assert data["type"] == "bugfix"

    def test_get_run_task_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent/task")
        assert response.status_code == 404


class TestEvidence:
    def test_get_evidence(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/evidence")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_get_evidence_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent/evidence")
        assert response.status_code == 404


class TestDiff:
    def test_get_diff(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/diff")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "patch_001"
        assert "src/auth.py" in data["changed_files"]

    def test_get_diff_no_patches(self, client, tmp_path):
        db_path = str(tmp_path / "no_patch.db")
        store = Store(db_path)
        run = TaskRun(id="run_002", task_id="task_002", repo_snapshot_id="repo_002")
        task = Task(id="task_002", repo_snapshot_id="repo_002", type=TaskType.bugfix, instruction="test")
        store.save_task(task)
        store.save_run(run)
        store.close()

        # Use the client's db_path for this test
        # We need to save to the client's db
        store2 = Store(client._db_path)
        run2 = TaskRun(id="run_003", task_id="task_003", repo_snapshot_id="repo_003")
        task2 = Task(id="task_003", repo_snapshot_id="repo_003", type=TaskType.bugfix, instruction="test")
        store2.save_task(task2)
        store2.save_run(run2)
        store2.close()

        response = client.get("/api/v1/runs/run_003/diff")
        assert response.status_code == 404

    def test_get_diff_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent/diff")
        assert response.status_code == 404


class TestReview:
    def test_get_review(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/review")
        assert response.status_code == 200
        data = response.json()
        assert len(data["findings"]) == 1
        assert data["findings"][0]["id"] == "finding_001"
        assert data["final_decision"] is not None
        assert data["final_decision"]["status"] == "verified_candidate"

    def test_get_review_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent/review")
        assert response.status_code == 404


class TestProvenance:
    def test_get_provenance_tree(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/provenance")
        assert response.status_code == 200
        data = response.json()
        assert len(data["edges"]) > 0
        assert data["summary"] is None

    def test_get_provenance_summary(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/provenance?format=summary")
        assert response.status_code == 200
        data = response.json()
        assert data["summary"] is not None
        assert data["summary"]["total_edges"] > 0
        assert data["summary"]["total_nodes"] > 0

    def test_get_provenance_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent/provenance")
        assert response.status_code == 404


class TestReport:
    def test_get_report(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/report")
        assert response.status_code == 200
        text = response.text
        assert "VSRS Run Report" in text
        assert run_id in text
        assert "verified" in text

    def test_get_report_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent/report")
        assert response.status_code == 404


class TestExport:
    def test_export_run(self, client):
        run_id, _ = _seed_store(client._db_path)
        response = client.get(f"/api/v1/runs/{run_id}/export")
        assert response.status_code == 200
        data = response.json()
        assert "trajectory" in data
        assert data["trajectory"]["task"]["id"] == "task_001"

    def test_export_not_found(self, client):
        response = client.get("/api/v1/runs/nonexistent/export")
        assert response.status_code == 404


class TestHistory:
    def test_get_history(self, client):
        _, task_id = _seed_store(client._db_path)
        response = client.get(f"/api/v1/tasks/{task_id}/history")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == task_id
        assert len(data["runs"]) >= 1

    def test_get_history_not_found(self, client):
        response = client.get("/api/v1/tasks/nonexistent/history")
        assert response.status_code == 404


class TestConfig:
    def test_get_config(self, client):
        response = client.get("/api/v1/config")
        assert response.status_code == 200
        data = response.json()
        assert "config" in data
        assert "database" in data["config"]
        assert "model" in data["config"]

    def test_validate_config(self, client):
        response = client.post("/api/v1/config/validate")
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []


class TestBenchmarks:
    def test_list_benchmarks(self, client):
        response = client.get("/api/v1/benchmarks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert len(data["tasks"]) > 0
        assert "id" in data["tasks"][0]
        assert "name" in data["tasks"][0]
