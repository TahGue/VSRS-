"""Tests for training data export, filters, and datasets (Phase 12)."""

import json
from pathlib import Path
from typing import Any

import pytest

from vsrs.core.schemas import (
    FinalDecision,
    FinalStatus,
    PatchCandidate,
    RepositorySnapshot,
    Task,
    TaskRun,
    TaskState,
    TaskType,
    RiskLevel,
)
from vsrs.core.store import Store
from vsrs.provenance import EvidenceGraph, ProvenanceStore
from vsrs.training import DatasetBuilder, DatasetStats, TrajectoryExporter, TrajectoryFilter


def _seed_store(db_path: str) -> tuple[Store, str, str]:
    """Seed a store with task, run, patch, decision, and provenance."""
    store = Store(db_path)

    repo = RepositorySnapshot(id="repo_001", root="/tmp/test", commit_hash="abc123")
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
    decision = FinalDecision(
        task_id="task_001",
        status=FinalStatus.verified_candidate,
        blockers=[],
        waived_gates=[],
        summary="Patch verified.",
        provenance_id="",
    )

    store.save_repository(repo)
    store.save_task(task)
    store.save_run(run)
    store.save_patch(patch)
    store.save_final_decision(decision)

    prov = ProvenanceStore(store)
    graph = EvidenceGraph(prov)
    graph.link_run_to_task("run_001", "task_001")
    graph.link_run_to_patch("run_001", "patch_001")

    return store, "run_001", "task_001"


def _make_trajectory(
    final_status: str = "verified_candidate",
    patches: int = 1,
    evidence_count: int = 1,
    changed_files: list[str] | None = None,
    has_hypotheses: bool = True,
    has_verification: bool = True,
    repo_snapshot_id: str = "repo_001",
) -> dict[str, Any]:
    """Create a synthetic trajectory dict for testing."""
    if changed_files is None:
        changed_files = ["src/auth.py"]

    patch_attempts = []
    for i in range(patches):
        patch_attempts.append({
            "id": f"patch_{i:03d}",
            "attempt_no": i + 1,
            "diff": f"--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old{i}\n+new{i}\n",
            "changed_files": changed_files,
            "assumptions": ["assumption1"],
            "predicted_effects": [],
            "falsification_checks": [],
        })

    return {
        "run_id": "run_test",
        "task": {
            "id": "task_test",
            "instruction": "Fix a bug",
            "acceptance_criteria": ["test passes"],
            "type": "bugfix",
        },
        "repository_snapshot_id": repo_snapshot_id,
        "retrieved_evidence": [{"type": "structural", "locator": f"file.py:{i}", "content": f"evidence {i}"} for i in range(evidence_count)],
        "hypotheses": [{"statement": "hypothesis1"}] if has_hypotheses else [],
        "assumptions": ["assumption1"],
        "predicted_effects": [],
        "patch_attempts": patch_attempts,
        "verification_results": [{"checks": []}] if has_verification else [],
        "critic_findings": [],
        "repair_decisions": [],
        "provenance_edges": [{"from_id": "run_001", "relation": "executes"}] if patches > 0 else [],
        "event_timeline": [],
        "final_patch": patch_attempts[-1] if patch_attempts else None,
        "final_status": final_status,
        "final_decision": {"status": final_status} if final_status else None,
        "events": [],
    }


class TestTrajectoryExporter:
    def test_export_run(self, tmp_path):
        store, run_id, _ = _seed_store(str(tmp_path / "test.db"))
        exporter = TrajectoryExporter(store)
        traj = exporter.export_run(run_id)
        assert traj is not None
        assert traj["run_id"] == run_id
        assert traj["task"]["id"] == "task_001"
        assert traj["final_status"] == "verified_candidate"
        assert "provenance_edges" in traj
        assert len(traj["provenance_edges"]) > 0
        assert "event_timeline" in traj
        assert "repair_decisions" in traj
        assert "final_decision" in traj
        store.close()

    def test_export_nonexistent_run(self, tmp_path):
        store = Store(str(tmp_path / "test.db"))
        exporter = TrajectoryExporter(store)
        traj = exporter.export_run("nonexistent")
        assert traj is None
        store.close()

    def test_export_to_jsonl(self, tmp_path):
        store, run_id, _ = _seed_store(str(tmp_path / "test.db"))
        exporter = TrajectoryExporter(store)
        output = tmp_path / "export.jsonl"
        count = exporter.export_to_jsonl([run_id], output)
        assert count == 1
        assert output.exists()
        data = json.loads(output.read_text().strip())
        assert data["run_id"] == run_id
        store.close()

    def test_export_all(self, tmp_path):
        store, run_id, _ = _seed_store(str(tmp_path / "test.db"))
        exporter = TrajectoryExporter(store)
        output = tmp_path / "all.jsonl"
        count = exporter.export_all(output)
        assert count >= 1
        assert output.exists()
        store.close()

    def test_export_filtered(self, tmp_path):
        store, run_id, _ = _seed_store(str(tmp_path / "test.db"))
        exporter = TrajectoryExporter(store)
        output = tmp_path / "filtered.jsonl"
        count = exporter.export_filtered(output, statuses=["verified_candidate"])
        assert count == 1
        store.close()

    def test_export_filtered_no_match(self, tmp_path):
        store, run_id, _ = _seed_store(str(tmp_path / "test.db"))
        exporter = TrajectoryExporter(store)
        output = tmp_path / "filtered_empty.jsonl"
        count = exporter.export_filtered(output, statuses=["rejected"])
        assert count == 0
        store.close()


class TestTrajectoryFilter:
    def test_is_reproducible(self):
        assert TrajectoryFilter.is_reproducible(_make_trajectory())
        assert not TrajectoryFilter.is_reproducible(_make_trajectory(repo_snapshot_id=""))

    def test_is_verified_positive(self):
        assert TrajectoryFilter.is_verified_positive(_make_trajectory(final_status="verified_candidate"))
        assert not TrajectoryFilter.is_verified_positive(_make_trajectory(final_status="rejected"))

    def test_is_verified_negative(self):
        assert TrajectoryFilter.is_verified_negative(_make_trajectory(final_status="rejected"))
        assert TrajectoryFilter.is_verified_negative(_make_trajectory(final_status="failed"))
        assert not TrajectoryFilter.is_verified_negative(_make_trajectory(final_status="verified_candidate"))

    def test_is_unresolved(self):
        assert TrajectoryFilter.is_unresolved(_make_trajectory(final_status="needs_review"))
        assert not TrajectoryFilter.is_unresolved(_make_trajectory(final_status="verified_candidate"))

    def test_has_patch(self):
        assert TrajectoryFilter.has_patch(_make_trajectory())
        assert not TrajectoryFilter.has_patch(_make_trajectory(patches=0))

    def test_has_evidence(self):
        assert TrajectoryFilter.has_evidence(_make_trajectory(evidence_count=1))
        assert not TrajectoryFilter.has_evidence(_make_trajectory(evidence_count=0))

    def test_has_verification_results(self):
        assert TrajectoryFilter.has_verification_results(_make_trajectory())
        assert not TrajectoryFilter.has_verification_results(_make_trajectory(has_verification=False))

    def test_has_provenance(self):
        assert TrajectoryFilter.has_provenance(_make_trajectory())
        assert not TrajectoryFilter.has_provenance(_make_trajectory(patches=0))

    def test_minimality_score(self):
        score = TrajectoryFilter.minimality_score(_make_trajectory(changed_files=["a.py"]))
        assert score == 0.9
        score = TrajectoryFilter.minimality_score(_make_trajectory(changed_files=["a.py", "b.py", "c.py"]))
        assert 0.6 < score < 0.8
        score = TrajectoryFilter.minimality_score(_make_trajectory(patches=0))
        assert score == 0.0

    def test_evidence_quality_score(self):
        score = TrajectoryFilter.evidence_quality_score(_make_trajectory())
        assert score == 1.0
        score = TrajectoryFilter.evidence_quality_score(_make_trajectory(evidence_count=0, has_hypotheses=False, has_verification=False))
        assert score == 0.0

    def test_repair_efficiency(self):
        score = TrajectoryFilter.repair_efficiency(_make_trajectory(patches=1))
        assert score == 1.0
        score = TrajectoryFilter.repair_efficiency(_make_trajectory(patches=2))
        assert 0.7 < score < 0.8
        score = TrajectoryFilter.repair_efficiency(_make_trajectory(final_status="rejected"))
        assert score == 0.0

    def test_filter_basic(self):
        trajs = [_make_trajectory(), _make_trajectory(final_status="rejected", evidence_count=0)]
        f = TrajectoryFilter()
        result = f.filter(trajs)
        assert len(result) == 1
        assert result[0]["final_status"] == "verified_candidate"

    def test_filter_with_minimality(self):
        trajs = [
            _make_trajectory(changed_files=["a.py"]),
            _make_trajectory(changed_files=["a.py", "b.py", "c.py", "d.py", "e.py"]),
        ]
        f = TrajectoryFilter()
        result = f.filter(trajs, min_minimality=0.8)
        assert len(result) == 1
        assert result[0]["final_patch"]["changed_files"] == ["a.py"]

    def test_filter_with_evidence_quality(self):
        trajs = [
            _make_trajectory(evidence_count=1, has_verification=True, has_hypotheses=True),
            _make_trajectory(evidence_count=0, has_verification=False, has_hypotheses=False),
        ]
        f = TrajectoryFilter()
        result = f.filter(trajs, min_evidence_quality=0.5)
        assert len(result) == 1

    def test_filter_with_repair_efficiency(self):
        trajs = [
            _make_trajectory(patches=1),
            _make_trajectory(patches=4),
        ]
        f = TrajectoryFilter()
        result = f.filter(trajs, min_repair_efficiency=0.8)
        assert len(result) == 1
        assert len(result[0]["patch_attempts"]) == 1

    def test_categorize(self):
        assert TrajectoryFilter().categorize(_make_trajectory(final_status="verified_candidate")) == "verified_positive"
        assert TrajectoryFilter().categorize(_make_trajectory(final_status="rejected")) == "verified_negative"
        assert TrajectoryFilter().categorize(_make_trajectory(final_status="needs_review")) == "unresolved"

    def test_score(self):
        scores = TrajectoryFilter().score(_make_trajectory())
        assert "minimality" in scores
        assert "evidence_quality" in scores
        assert "repair_efficiency" in scores
        assert all(0.0 <= v <= 1.0 for v in scores.values())


class TestDatasetBuilder:
    def test_build_sft_dataset(self, tmp_path):
        trajs = [_make_trajectory(), _make_trajectory(final_status="rejected")]
        builder = DatasetBuilder()
        output = tmp_path / "sft.jsonl"
        count = builder.build_sft_dataset(trajs, output)
        assert count == 1
        assert output.exists()
        entry = json.loads(output.read_text().strip())
        assert "input" in entry
        assert "output" in entry
        assert entry["input"]["instruction"] == "Fix a bug"

    def test_build_repair_dataset(self, tmp_path):
        trajs = [_make_trajectory(patches=2), _make_trajectory(patches=1)]
        builder = DatasetBuilder()
        output = tmp_path / "repair.jsonl"
        count = builder.build_repair_dataset(trajs, output)
        assert count == 1
        entry = json.loads(output.read_text().strip())
        assert "failure" in entry
        assert "corrected_action" in entry

    def test_build_preference_dataset(self, tmp_path):
        trajs = [
            _make_trajectory(final_status="verified_candidate"),
            _make_trajectory(final_status="rejected"),
        ]
        builder = DatasetBuilder()
        output = tmp_path / "pref.jsonl"
        count = builder.build_preference_dataset(trajs, output)
        assert count == 1
        entry = json.loads(output.read_text().strip())
        assert "chosen" in entry
        assert "rejected" in entry

    def test_build_tool_use_dataset(self, tmp_path):
        trajs = [_make_trajectory(evidence_count=2)]
        builder = DatasetBuilder()
        output = tmp_path / "tooluse.jsonl"
        count = builder.build_tool_use_dataset(trajs, output)
        assert count == 2
        lines = output.read_text().strip().split("\n")
        entry = json.loads(lines[0])
        assert "context" in entry
        assert "tool_call" in entry
        assert "result" in entry

    def test_build_tool_use_no_evidence(self, tmp_path):
        trajs = [_make_trajectory(evidence_count=0)]
        builder = DatasetBuilder()
        output = tmp_path / "tooluse_empty.jsonl"
        count = builder.build_tool_use_dataset(trajs, output)
        assert count == 0

    def test_train_val_split(self):
        trajs = [_make_trajectory() for _ in range(10)]
        builder = DatasetBuilder()
        train, val = builder.train_val_split(trajs, val_ratio=0.2, seed=42)
        assert len(train) == 8
        assert len(val) == 2

    def test_train_val_split_reproducible(self):
        trajs = [_make_trajectory() for _ in range(10)]
        builder = DatasetBuilder()
        train1, val1 = builder.train_val_split(trajs, val_ratio=0.2, seed=42)
        train2, val2 = builder.train_val_split(trajs, val_ratio=0.2, seed=42)
        assert [t["run_id"] for t in train1] == [t["run_id"] for t in train2]
        assert [t["run_id"] for t in val1] == [t["run_id"] for t in val2]

    def test_build_with_stats_sft(self, tmp_path):
        trajs = [_make_trajectory(), _make_trajectory(final_status="rejected")]
        builder = DatasetBuilder()
        output = tmp_path / "sft_stats.jsonl"
        count, stats = builder.build_with_stats(trajs, output, dataset_type="sft")
        assert count == 1
        assert stats.entry_count == 1
        assert stats.total_tokens > 0
        assert stats.avg_tokens > 0

    def test_build_with_stats_tool_use(self, tmp_path):
        trajs = [_make_trajectory(evidence_count=3)]
        builder = DatasetBuilder()
        output = tmp_path / "tu_stats.jsonl"
        count, stats = builder.build_with_stats(trajs, output, dataset_type="tool_use")
        assert count == 3
        assert stats.entry_count == 3

    def test_build_with_stats_invalid_type(self, tmp_path):
        builder = DatasetBuilder()
        with pytest.raises(ValueError, match="Unknown dataset type"):
            builder.build_with_stats([], tmp_path / "bad.jsonl", dataset_type="invalid")


class TestDatasetStats:
    def test_stats_basic(self):
        stats = DatasetStats()
        stats.add_entry(100, "verified_candidate")
        stats.add_entry(200, "verified_candidate")
        stats.finalize()
        assert stats.entry_count == 2
        assert stats.total_tokens == 300
        assert stats.min_tokens == 100
        assert stats.max_tokens == 200
        assert stats.avg_tokens == 150.0
        assert stats.status_distribution == {"verified_candidate": 2}

    def test_stats_empty(self):
        stats = DatasetStats()
        stats.finalize()
        assert stats.entry_count == 0
        assert stats.avg_tokens == 0.0

    def test_stats_to_dict(self):
        stats = DatasetStats()
        stats.add_entry(50, "verified_candidate")
        stats.finalize()
        d = stats.to_dict()
        assert d["entry_count"] == 1
        assert d["total_tokens"] == 50
        assert d["avg_tokens"] == 50.0
        assert "status_distribution" in d
