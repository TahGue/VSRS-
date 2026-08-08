"""Tests for the fine-tuning pipeline (Phase 19)."""

import json
import pytest
from pathlib import Path

from vsrs.finetuning import (
    ABComparison,
    ComparisonResult,
    DatasetVersion,
    DatasetVersionManager,
    FineTuningJob,
    FineTuningMethod,
    FineTuningStatus,
    JobOrchestrator,
    ModelComparisonHarness,
)
from vsrs.eval.scorer import ScoreResult
from vsrs.eval.tasks import BenchmarkSet


# --- Helpers ---

def _write_jsonl(path: Path, entries: list[dict]) -> None:
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _make_score(task_id: str, verified: bool = True, grounding: int = 0) -> ScoreResult:
    return ScoreResult(
        task_id=task_id,
        verified_success=verified,
        grounding_errors=grounding,
        test_adequacy=0.8 if verified else 0.3,
        patch_minimality=0.9,
    )


# --- FineTuningJob Tests ---

class TestFineTuningJob:
    def test_creation_defaults(self):
        job = FineTuningJob(model_name="gpt-4o")
        assert job.id.startswith("ftjob_")
        assert job.method == FineTuningMethod.lora
        assert job.status == FineTuningStatus.pending
        assert job.output_model_name.startswith("gpt-4o-finetuned-")

    def test_creation_with_method(self):
        job = FineTuningJob(model_name="llama-3", method=FineTuningMethod.qlora)
        assert job.method == FineTuningMethod.qlora

    def test_hyperparameters_defaults(self):
        job = FineTuningJob(model_name="gpt-4o")
        assert "learning_rate" in job.hyperparameters
        assert "num_epochs" in job.hyperparameters

    def test_to_dict_and_from_dict(self):
        job = FineTuningJob(
            model_name="gpt-4o",
            method=FineTuningMethod.dpo,
            dataset_path="/data/train.jsonl",
            output_model_name="gpt-4o-dpo",
        )
        d = job.to_dict()
        assert d["model_name"] == "gpt-4o"
        assert d["method"] == "dpo"
        restored = FineTuningJob.from_dict(d)
        assert restored.model_name == job.model_name
        assert restored.method == job.method
        assert restored.id == job.id

    def test_duration_seconds(self):
        from datetime import datetime, timezone, timedelta
        job = FineTuningJob(model_name="gpt-4o")
        job.started_at = datetime.now(timezone.utc)
        job.completed_at = job.started_at + timedelta(seconds=60)
        assert job.duration_seconds == pytest.approx(60.0, abs=1.0)

    def test_duration_seconds_not_started(self):
        job = FineTuningJob(model_name="gpt-4o")
        assert job.duration_seconds == 0.0


# --- FineTuningMethod Tests ---

class TestFineTuningMethod:
    def test_values(self):
        assert FineTuningMethod.full.value == "full"
        assert FineTuningMethod.lora.value == "lora"
        assert FineTuningMethod.qlora.value == "qlora"
        assert FineTuningMethod.dpo.value == "dpo"
        assert FineTuningMethod.ppo.value == "ppo"


# --- FineTuningStatus Tests ---

class TestFineTuningStatus:
    def test_values(self):
        assert FineTuningStatus.pending.value == "pending"
        assert FineTuningStatus.running.value == "running"
        assert FineTuningStatus.completed.value == "completed"
        assert FineTuningStatus.failed.value == "failed"
        assert FineTuningStatus.cancelled.value == "cancelled"


# --- JobOrchestrator Tests ---

class TestJobOrchestrator:
    def test_submit_and_get(self):
        orch = JobOrchestrator()
        job = FineTuningJob(model_name="gpt-4o")
        job_id = orch.submit(job)
        assert job_id == job.id
        assert orch.get(job_id) is job
        assert orch.count() == 1

    def test_execute_success(self):
        orch = JobOrchestrator(
            executor=lambda j: {"train_loss": 0.3, "eval_loss": 0.4}
        )
        job = FineTuningJob(model_name="gpt-4o")
        orch.submit(job)
        result = orch.execute(job.id)
        assert result.status == FineTuningStatus.completed
        assert result.metrics["train_loss"] == 0.3
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_execute_failure(self):
        def failing_executor(j):
            raise RuntimeError("Training crashed")
        orch = JobOrchestrator(executor=failing_executor)
        job = FineTuningJob(model_name="gpt-4o")
        orch.submit(job)
        result = orch.execute(job.id)
        assert result.status == FineTuningStatus.failed
        assert "Training crashed" in result.error

    def test_execute_not_found(self):
        orch = JobOrchestrator()
        with pytest.raises(ValueError, match="not found"):
            orch.execute("nonexistent")

    def test_execute_no_executor(self):
        orch = JobOrchestrator()
        job = FineTuningJob(model_name="gpt-4o")
        orch.submit(job)
        with pytest.raises(ValueError, match="No executor"):
            orch.execute(job.id)

    def test_cancel_pending(self):
        orch = JobOrchestrator()
        job = FineTuningJob(model_name="gpt-4o")
        orch.submit(job)
        assert orch.cancel(job.id) is True
        assert orch.get(job.id).status == FineTuningStatus.cancelled

    def test_cancel_completed_fails(self):
        orch = JobOrchestrator(executor=lambda j: {"loss": 0.5})
        job = FineTuningJob(model_name="gpt-4o")
        orch.submit(job)
        orch.execute(job.id)
        assert orch.cancel(job.id) is False

    def test_cancel_not_found(self):
        orch = JobOrchestrator()
        assert orch.cancel("nonexistent") is False

    def test_get_status(self):
        orch = JobOrchestrator()
        job = FineTuningJob(model_name="gpt-4o")
        orch.submit(job)
        assert orch.get_status(job.id) == FineTuningStatus.pending

    def test_get_status_not_found(self):
        orch = JobOrchestrator()
        assert orch.get_status("nonexistent") is None

    def test_list_jobs_all(self):
        orch = JobOrchestrator()
        orch.submit(FineTuningJob(model_name="gpt-4o"))
        orch.submit(FineTuningJob(model_name="llama-3"))
        jobs = orch.list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_by_model(self):
        orch = JobOrchestrator()
        orch.submit(FineTuningJob(model_name="gpt-4o"))
        orch.submit(FineTuningJob(model_name="llama-3"))
        jobs = orch.list_jobs(model_name="gpt-4o")
        assert len(jobs) == 1
        assert jobs[0].model_name == "gpt-4o"

    def test_list_jobs_by_status(self):
        orch = JobOrchestrator(executor=lambda j: {"loss": 0.5})
        j1 = FineTuningJob(model_name="gpt-4o")
        orch.submit(j1)
        orch.execute(j1.id)
        orch.submit(FineTuningJob(model_name="llama-3"))
        completed = orch.list_jobs(status=FineTuningStatus.completed)
        pending = orch.list_jobs(status=FineTuningStatus.pending)
        assert len(completed) == 1
        assert len(pending) == 1

    def test_set_executor(self):
        orch = JobOrchestrator()
        orch.set_executor(lambda j: {"loss": 0.1})
        job = FineTuningJob(model_name="gpt-4o")
        orch.submit(job)
        result = orch.execute(job.id)
        assert result.metrics["loss"] == 0.1

    def test_clear(self):
        orch = JobOrchestrator()
        orch.submit(FineTuningJob(model_name="gpt-4o"))
        orch.clear()
        assert orch.count() == 0


# --- DatasetVersion Tests ---

class TestDatasetVersion:
    def test_creation(self):
        v = DatasetVersion(
            version_id="v1",
            dataset_path="/data/v1.jsonl",
            entry_count=100,
            unique_entries=95,
            duplicate_count=5,
        )
        assert v.version_id == "v1"
        assert v.entry_count == 100

    def test_to_dict_and_from_dict(self):
        v = DatasetVersion(
            version_id="v1",
            dataset_path="/data/v1.jsonl",
            entry_count=100,
            unique_entries=95,
            duplicate_count=5,
            content_hash="abc123",
        )
        d = v.to_dict()
        assert d["version_id"] == "v1"
        restored = DatasetVersion.from_dict(d)
        assert restored.version_id == v.version_id
        assert restored.content_hash == v.content_hash


# --- DatasetVersionManager Tests ---

class TestDatasetVersionManager:
    def test_create_version(self, tmp_path):
        # Create a dataset
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [
            {"task_id": "t1", "instruction": "fix bug"},
            {"task_id": "t2", "instruction": "add feature"},
        ])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        v = mgr.create_version(dataset)
        assert v.entry_count == 2
        assert v.unique_entries == 2
        assert v.duplicate_count == 0
        assert v.content_hash != ""
        assert mgr.count() == 1

    def test_create_version_with_duplicates(self, tmp_path):
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [
            {"task_id": "t1", "instruction": "fix bug"},
            {"task_id": "t1", "instruction": "fix bug"},  # duplicate
            {"task_id": "t2", "instruction": "add feature"},
        ])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        v = mgr.create_version(dataset)
        assert v.entry_count == 3
        assert v.unique_entries == 2
        assert v.duplicate_count == 1

    def test_create_version_with_metadata(self, tmp_path):
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [{"task_id": "t1"}])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        v = mgr.create_version(dataset, metadata={"source": "sft", "split": "train"})
        assert v.metadata["source"] == "sft"

    def test_create_version_with_custom_id(self, tmp_path):
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [{"task_id": "t1"}])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        v = mgr.create_version(dataset, version_id="v2.0")
        assert v.version_id == "v2.0"

    def test_create_version_file_not_found(self, tmp_path):
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        with pytest.raises(FileNotFoundError):
            mgr.create_version(tmp_path / "nonexistent.jsonl")

    def test_get_version(self, tmp_path):
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [{"task_id": "t1"}])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        v = mgr.create_version(dataset, version_id="v1")
        assert mgr.get_version("v1") is v
        assert mgr.get_version("nonexistent") is None

    def test_list_versions(self, tmp_path):
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [{"task_id": "t1"}])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        mgr.create_version(dataset, version_id="v1")
        mgr.create_version(dataset, version_id="v2")
        versions = mgr.list_versions()
        assert len(versions) == 2

    def test_compare_versions_identical(self, tmp_path):
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [{"task_id": "t1"}, {"task_id": "t2"}])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        v1 = mgr.create_version(dataset, version_id="v1")
        v2 = mgr.create_version(dataset, version_id="v2")
        diff = mgr.compare_versions("v1", "v2")
        assert diff["identical"] is True
        assert diff["added"] == 0
        assert diff["removed"] == 0

    def test_compare_versions_different(self, tmp_path):
        ds1 = tmp_path / "train1.jsonl"
        ds2 = tmp_path / "train2.jsonl"
        _write_jsonl(ds1, [{"task_id": "t1"}, {"task_id": "t2"}])
        _write_jsonl(ds2, [{"task_id": "t2"}, {"task_id": "t3"}])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        mgr.create_version(ds1, version_id="v1")
        mgr.create_version(ds2, version_id="v2")
        diff = mgr.compare_versions("v1", "v2")
        assert diff["identical"] is False
        assert diff["added"] == 1   # t3
        assert diff["removed"] == 1  # t1
        assert diff["common"] == 1   # t2

    def test_compare_versions_not_found(self, tmp_path):
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        with pytest.raises(ValueError, match="not found"):
            mgr.compare_versions("v1", "v2")

    def test_deduplicate(self, tmp_path):
        inp = tmp_path / "input.jsonl"
        out = tmp_path / "output.jsonl"
        _write_jsonl(inp, [
            {"task_id": "t1"},
            {"task_id": "t1"},  # dup
            {"task_id": "t2"},
            {"task_id": "t2"},  # dup
            {"task_id": "t3"},
        ])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        original, unique = mgr.deduplicate(inp, out)
        assert original == 5
        assert unique == 3
        assert out.exists()

    def test_clear(self, tmp_path):
        dataset = tmp_path / "train.jsonl"
        _write_jsonl(dataset, [{"task_id": "t1"}])
        mgr = DatasetVersionManager(storage_dir=tmp_path / "versions")
        mgr.create_version(dataset, version_id="v1")
        mgr.clear()
        assert mgr.count() == 0


# --- ABComparison and ModelComparisonHarness Tests ---

class TestModelComparisonHarness:
    def test_run_comparison(self):
        bench_set = BenchmarkSet.seed()

        def base_runner(task):
            return _make_score(task.id, verified=False)

        def ft_runner(task):
            return _make_score(task.id, verified=True)

        comp = ABComparison(
            base_model_name="gpt-4o",
            finetuned_model_name="gpt-4o-finetuned",
            base_runner=base_runner,
            finetuned_runner=ft_runner,
            benchmark_set=bench_set,
        )
        harness = ModelComparisonHarness(comp)
        result = harness.run()

        assert isinstance(result, ComparisonResult)
        assert result.base_model == "gpt-4o"
        assert result.finetuned_model == "gpt-4o-finetuned"
        assert result.base_report is not None
        assert result.finetuned_report is not None
        assert result.finetuned_report.verified_success_rate > result.base_report.verified_success_rate
        assert result.improvement is True

    def test_aggregate_deltas(self):
        bench_set = BenchmarkSet.seed()

        def base_runner(task):
            return _make_score(task.id, verified=False, grounding=2)

        def ft_runner(task):
            return _make_score(task.id, verified=True, grounding=0)

        comp = ABComparison(
            base_model_name="base",
            finetuned_model_name="ft",
            base_runner=base_runner,
            finetuned_runner=ft_runner,
            benchmark_set=bench_set,
        )
        harness = ModelComparisonHarness(comp)
        result = harness.run()

        assert result.aggregate_deltas["verified_success_rate"] > 0
        assert result.aggregate_deltas["grounding_error_rate"] < 0  # improved (fewer errors)

    def test_per_task_deltas(self):
        bench_set = BenchmarkSet.seed()

        def base_runner(task):
            return _make_score(task.id, verified=False)

        def ft_runner(task):
            return _make_score(task.id, verified=True)

        comp = ABComparison(
            base_model_name="base",
            finetuned_model_name="ft",
            base_runner=base_runner,
            finetuned_runner=ft_runner,
            benchmark_set=bench_set,
        )
        harness = ModelComparisonHarness(comp)
        result = harness.run()

        assert len(result.per_task_deltas) > 0
        for task_id, deltas in result.per_task_deltas.items():
            assert deltas["verified_success"] == 1.0  # False -> True

    def test_summarize(self):
        bench_set = BenchmarkSet.seed()

        comp = ABComparison(
            base_model_name="base",
            finetuned_model_name="ft",
            base_runner=lambda t: _make_score(t.id, verified=False),
            finetuned_runner=lambda t: _make_score(t.id, verified=True),
            benchmark_set=bench_set,
        )
        harness = ModelComparisonHarness(comp)
        result = harness.run()
        summary = harness.summarize(result)

        assert "base vs ft" in summary
        assert "verified_success_rate" in summary
        assert "Improvement: YES" in summary

    def test_no_improvement(self):
        bench_set = BenchmarkSet.seed()

        comp = ABComparison(
            base_model_name="base",
            finetuned_model_name="ft",
            base_runner=lambda t: _make_score(t.id, verified=True),
            finetuned_runner=lambda t: _make_score(t.id, verified=False),
            benchmark_set=bench_set,
        )
        harness = ModelComparisonHarness(comp)
        result = harness.run()
        assert result.improvement is False

    def test_runner_error_handling(self):
        bench_set = BenchmarkSet.seed()

        def error_runner(task):
            raise RuntimeError("Model error")

        def good_runner(task):
            return _make_score(task.id, verified=True)

        comp = ABComparison(
            base_model_name="base",
            finetuned_model_name="ft",
            base_runner=error_runner,
            finetuned_runner=good_runner,
            benchmark_set=bench_set,
        )
        harness = ModelComparisonHarness(comp)
        result = harness.run()
        # Base model should have all failures
        assert result.base_report.verified_success_rate == 0.0
        assert result.finetuned_report.verified_success_rate > 0.0

    def test_comparison_result_to_dict(self):
        bench_set = BenchmarkSet.seed()

        comp = ABComparison(
            base_model_name="base",
            finetuned_model_name="ft",
            base_runner=lambda t: _make_score(t.id, verified=False),
            finetuned_runner=lambda t: _make_score(t.id, verified=True),
            benchmark_set=bench_set,
        )
        harness = ModelComparisonHarness(comp)
        result = harness.run()
        d = result.to_dict()
        assert d["base_model"] == "base"
        assert d["finetuned_model"] == "ft"
        assert d["improvement"] is True
        assert "aggregate_deltas" in d
