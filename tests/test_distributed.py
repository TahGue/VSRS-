"""Tests for distributed execution (Phase 18)."""

import time
import pytest

from vsrs.distributed import (
    DistributedBenchmarkRunner,
    InMemoryQueue,
    JobResult,
    JobStatus,
    RedisQueue,
    TaskJob,
    TaskQueue,
    Worker,
)
from vsrs.distributed.base import JobStatus as JS
from vsrs.eval.scorer import ScoreResult
from vsrs.eval.tasks import BenchmarkSet, BenchmarkTask


# --- Helpers ---

def _make_job(job_id: str = "job_001", task_type: str = "benchmark") -> TaskJob:
    return TaskJob(
        id=job_id,
        task_type=task_type,
        payload={"key": "value"},
        priority=0,
    )


def _make_result(job_id: str = "job_001", success: bool = True) -> JobResult:
    return JobResult(
        job_id=job_id,
        success=success,
        output={"score": 0.95},
        duration_seconds=1.5,
        worker_id="worker-1",
    )


# --- TaskJob Tests ---

class TestTaskJob:
    def test_creation(self):
        job = _make_job()
        assert job.id == "job_001"
        assert job.task_type == "benchmark"
        assert job.status == JobStatus.pending

    def test_status_running(self):
        from datetime import datetime, timezone
        job = _make_job()
        job.started_at = datetime.now(timezone.utc)
        assert job.status == JobStatus.running

    def test_status_completed(self):
        from datetime import datetime, timezone
        job = _make_job()
        job.started_at = datetime.now(timezone.utc)
        job.completed_at = datetime.now(timezone.utc)
        assert job.status == JobStatus.completed

    def test_to_dict_and_from_dict(self):
        job = _make_job()
        job.tags = ["benchmark", "bugfix"]
        d = job.to_dict()
        assert d["id"] == "job_001"
        assert d["status"] == "pending"
        restored = TaskJob.from_dict(d)
        assert restored.id == job.id
        assert restored.task_type == job.task_type
        assert restored.tags == job.tags

    def test_to_dict_with_timestamps(self):
        from datetime import datetime, timezone
        job = _make_job()
        job.started_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        job.completed_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
        d = job.to_dict()
        assert d["started_at"] is not None
        assert d["completed_at"] is not None
        restored = TaskJob.from_dict(d)
        assert restored.started_at is not None
        assert restored.completed_at is not None


# --- JobResult Tests ---

class TestJobResult:
    def test_creation(self):
        result = _make_result()
        assert result.success is True
        assert result.output == {"score": 0.95}
        assert result.worker_id == "worker-1"

    def test_to_dict_and_from_dict(self):
        result = _make_result()
        d = result.to_dict()
        assert d["job_id"] == "job_001"
        assert d["success"] is True
        restored = JobResult.from_dict(d)
        assert restored.job_id == result.job_id
        assert restored.success == result.success

    def test_failed_result(self):
        result = JobResult(
            job_id="job_002",
            success=False,
            error="Something went wrong",
        )
        assert result.success is False
        assert "Something went wrong" in result.error


# --- JobStatus Tests ---

class TestJobStatus:
    def test_values(self):
        assert JobStatus.pending.value == "pending"
        assert JobStatus.queued.value == "queued"
        assert JobStatus.running.value == "running"
        assert JobStatus.completed.value == "completed"
        assert JobStatus.failed.value == "failed"
        assert JobStatus.cancelled.value == "cancelled"


# --- InMemoryQueue Tests ---

class TestInMemoryQueue:
    def test_submit_and_size(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        q.submit(_make_job("job2"))
        assert q.size() == 2

    def test_fetch(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        job = q.fetch("worker-1")
        assert job is not None
        assert job.id == "job1"
        assert q.size() == 0

    def test_fetch_empty(self):
        q = InMemoryQueue()
        assert q.fetch("worker-1") is None

    def test_complete_and_get_result(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        q.fetch("worker-1")
        q.complete("job1", _make_result("job1"))
        result = q.get_result("job1")
        assert result is not None
        assert result.success is True

    def test_get_result_not_completed(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        assert q.get_result("job1") is None

    def test_get_status(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        assert q.get_status("job1") == JobStatus.pending
        q.fetch("worker-1")
        assert q.get_status("job1") == JobStatus.running
        q.complete("job1", _make_result("job1"))
        assert q.get_status("job1") == JobStatus.completed

    def test_get_status_not_found(self):
        q = InMemoryQueue()
        assert q.get_status("nonexistent") is None

    def test_cancel_pending(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        assert q.cancel("job1") is True
        assert q.size() == 0
        result = q.get_result("job1")
        assert result is not None
        assert result.success is False

    def test_cancel_completed_fails(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        q.fetch("worker-1")
        q.complete("job1", _make_result("job1"))
        assert q.cancel("job1") is False

    def test_cancel_not_found(self):
        q = InMemoryQueue()
        assert q.cancel("nonexistent") is False

    def test_clear(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        q.clear()
        assert q.size() == 0
        assert q.get_status("job1") is None

    def test_list_jobs_all(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1", "benchmark"))
        q.submit(_make_job("job2", "verify"))
        jobs = q.list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_by_type(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1", "benchmark"))
        q.submit(_make_job("job2", "verify"))
        jobs = q.list_jobs(task_type="benchmark")
        assert len(jobs) == 1
        assert jobs[0].task_type == "benchmark"

    def test_list_jobs_by_status(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1"))
        q.fetch("worker-1")
        q.submit(_make_job("job2"))
        running = q.list_jobs(status=JobStatus.running)
        pending = q.list_jobs(status=JobStatus.pending)
        assert len(running) == 1
        assert len(pending) == 1

    def test_priority_ordering(self):
        q = InMemoryQueue()
        q.submit(TaskJob(id="low", task_type="t", priority=10))
        q.submit(TaskJob(id="high", task_type="t", priority=1))
        q.submit(TaskJob(id="mid", task_type="t", priority=5))
        first = q.fetch("w")
        second = q.fetch("w")
        third = q.fetch("w")
        assert first.id == "high"
        assert second.id == "mid"
        assert third.id == "low"


# --- Worker Tests ---

class TestWorker:
    def test_process_one_success(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1", "echo"))
        worker = Worker(
            queue=q,
            worker_id="w1",
            handlers={"echo": lambda job: {"echoed": job.id}},
        )
        result = worker.process_one()
        assert result is not None
        assert result.success is True
        assert result.output == {"echoed": "job1"}
        assert worker.jobs_processed == 1
        assert worker.jobs_succeeded == 1

    def test_process_one_empty_queue(self):
        q = InMemoryQueue()
        worker = Worker(queue=q, worker_id="w1")
        result = worker.process_one()
        assert result is None

    def test_process_one_no_handler(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1", "unknown_type"))
        worker = Worker(queue=q, worker_id="w1")
        result = worker.process_one()
        assert result is not None
        assert result.success is False
        assert "No handler" in result.error
        assert worker.jobs_failed == 1

    def test_process_one_handler_error(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1", "fail"))
        worker = Worker(
            queue=q,
            worker_id="w1",
            handlers={"fail": lambda job: (_ for _ in ()).throw(ValueError("boom"))},
        )
        result = worker.process_one()
        assert result is not None
        assert result.success is False
        assert "boom" in result.error

    def test_register_handler(self):
        q = InMemoryQueue()
        worker = Worker(queue=q, worker_id="w1")
        worker.register_handler("echo", lambda job: {"ok": True})
        assert "echo" in worker.handlers

    def test_start_and_stop(self):
        q = InMemoryQueue()
        worker = Worker(
            queue=q,
            worker_id="w1",
            handlers={"echo": lambda job: {"ok": True}},
            poll_interval=0.05,
        )
        worker.start()
        assert worker.is_running is True
        time.sleep(0.1)
        worker.stop()
        assert worker.is_running is False

    def test_max_jobs(self):
        q = InMemoryQueue()
        q.submit(_make_job("job1", "echo"))
        q.submit(_make_job("job2", "echo"))
        worker = Worker(
            queue=q,
            worker_id="w1",
            handlers={"echo": lambda job: {"ok": True}},
            poll_interval=0.05,
            max_jobs=1,
        )
        worker.start()
        time.sleep(0.3)
        worker.stop()
        assert worker.jobs_processed == 1

    def test_stats(self):
        q = InMemoryQueue()
        worker = Worker(
            queue=q,
            worker_id="w1",
            handlers={"echo": lambda job: {"ok": True}},
        )
        stats = worker.stats()
        assert stats["worker_id"] == "w1"
        assert stats["jobs_processed"] == 0
        assert "echo" in stats["handlers"]


# --- RedisQueue Tests (graceful when Redis unavailable) ---

class TestRedisQueue:
    def test_creation_without_redis(self):
        q = RedisQueue(redis_url="redis://localhost:9999/0")
        # Should not raise, just log warning
        assert q.available is False

    def test_submit_without_redis_raises(self):
        q = RedisQueue(redis_url="redis://localhost:9999/0")
        with pytest.raises(RuntimeError, match="not available"):
            q.submit(_make_job())

    def test_size_without_redis(self):
        q = RedisQueue(redis_url="redis://localhost:9999/0")
        assert q.size() == 0

    def test_list_jobs_without_redis(self):
        q = RedisQueue(redis_url="redis://localhost:9999/0")
        assert q.list_jobs() == []


# --- DistributedBenchmarkRunner Tests ---

class TestDistributedBenchmarkRunner:
    def test_submit_all(self):
        bench_set = BenchmarkSet.seed()
        runner = DistributedBenchmarkRunner(
            benchmark_set=bench_set,
            task_handler=lambda task: {"verified": True, "task_id": task.id},
            num_workers=2,
        )
        job_ids = runner.submit_all()
        assert len(job_ids) > 0
        assert runner.queue.size() == len(job_ids)

    def test_run_parallel(self):
        bench_set = BenchmarkSet.seed()
        runner = DistributedBenchmarkRunner(
            benchmark_set=bench_set,
            task_handler=lambda task: ScoreResult(
                task_id=task.id,
                verified_success=True,
                hidden_tests_passed=True,
                hidden_tests_total=5,
                grounding_errors=0,
                test_adequacy=1.0,
            ).to_dict(),
            num_workers=2,
        )
        report = runner.run()
        assert report is not None
        assert report.total_tasks > 0

    def test_get_job_status(self):
        bench_set = BenchmarkSet.seed()
        runner = DistributedBenchmarkRunner(
            benchmark_set=bench_set,
            task_handler=lambda task: {"verified": True},
            num_workers=1,
        )
        runner.submit_all()
        statuses = runner.get_job_status()
        assert len(statuses) > 0
        # All should be pending initially
        assert all(s == "pending" for s in statuses.values())

    def test_get_worker_stats(self):
        bench_set = BenchmarkSet.seed()
        runner = DistributedBenchmarkRunner(
            benchmark_set=bench_set,
            task_handler=lambda task: ScoreResult(
                task_id=task.id,
                verified_success=True,
            ).to_dict(),
            num_workers=2,
        )
        runner.submit_all()
        runner.run()
        stats = runner.get_worker_stats()
        assert len(stats) == 2
        assert all("jobs_processed" in s for s in stats)
