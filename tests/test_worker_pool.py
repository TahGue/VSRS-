"""Tests for Phase 27: Worker pool with resource allocation and auto-scaling.

Tests ResourceSpec, WorkerInfo, WorkerPool, resource-aware scheduling,
auto-scaling, health checks, and graceful shutdown.
"""

import pytest
import time as _time
from datetime import datetime, timedelta, timezone

from vsrs.distributed.base import TaskJob, JobResult, JobStatus
from vsrs.distributed.memory import InMemoryQueue
from vsrs.distributed.pool import (
    InsufficientResourcesError,
    PoolConfig,
    ResourceSpec,
    WorkerInfo,
    WorkerPool,
    WorkerState,
)
from vsrs.distributed.worker import Worker


# --- ResourceSpec tests ---

class TestResourceSpec:
    def test_defaults(self):
        r = ResourceSpec()
        assert r.cpu == 1.0
        assert r.memory_mb == 512
        assert r.gpu == 0
        assert r.disk_mb == 0

    def test_custom(self):
        r = ResourceSpec(cpu=4.0, memory_mb=4096, gpu=2, disk_mb=10240)
        assert r.cpu == 4.0
        assert r.memory_mb == 4096
        assert r.gpu == 2
        assert r.disk_mb == 10240

    def test_can_fit_true(self):
        big = ResourceSpec(cpu=4.0, memory_mb=4096)
        small = ResourceSpec(cpu=1.0, memory_mb=512)
        assert big.can_fit(small)

    def test_can_fit_false(self):
        small = ResourceSpec(cpu=1.0, memory_mb=512)
        big = ResourceSpec(cpu=4.0, memory_mb=4096)
        assert not small.can_fit(big)

    def test_can_fit_exact(self):
        r1 = ResourceSpec(cpu=2.0, memory_mb=1024)
        r2 = ResourceSpec(cpu=2.0, memory_mb=1024)
        assert r1.can_fit(r2)

    def test_can_fit_gpu(self):
        with_gpu = ResourceSpec(cpu=1.0, memory_mb=512, gpu=1)
        no_gpu = ResourceSpec(cpu=1.0, memory_mb=512, gpu=0)
        assert not no_gpu.can_fit(with_gpu)
        assert with_gpu.can_fit(no_gpu)

    def test_subtract(self):
        capacity = ResourceSpec(cpu=4.0, memory_mb=4096)
        req = ResourceSpec(cpu=1.0, memory_mb=512)
        remaining = capacity.subtract(req)
        assert remaining.cpu == 3.0
        assert remaining.memory_mb == 3584

    def test_subtract_to_zero(self):
        capacity = ResourceSpec(cpu=1.0, memory_mb=512)
        req = ResourceSpec(cpu=2.0, memory_mb=1024)
        remaining = capacity.subtract(req)
        assert remaining.cpu == 0
        assert remaining.memory_mb == 0

    def test_add(self):
        base = ResourceSpec(cpu=2.0, memory_mb=1024)
        extra = ResourceSpec(cpu=1.0, memory_mb=512)
        total = base.add(extra)
        assert total.cpu == 3.0
        assert total.memory_mb == 1536

    def test_to_dict(self):
        r = ResourceSpec(cpu=2.0, memory_mb=2048, gpu=1)
        d = r.to_dict()
        assert d["cpu"] == 2.0
        assert d["memory_mb"] == 2048
        assert d["gpu"] == 1

    def test_from_dict(self):
        d = {"cpu": 3.0, "memory_mb": 8192, "gpu": 2, "disk_mb": 500}
        r = ResourceSpec.from_dict(d)
        assert r.cpu == 3.0
        assert r.memory_mb == 8192
        assert r.gpu == 2
        assert r.disk_mb == 500

    def test_roundtrip(self):
        r = ResourceSpec(cpu=3.5, memory_mb=2048, gpu=1, disk_mb=100)
        r2 = ResourceSpec.from_dict(r.to_dict())
        assert r2.cpu == 3.5
        assert r2.memory_mb == 2048
        assert r2.gpu == 1
        assert r2.disk_mb == 100


# --- WorkerState tests ---

class TestWorkerState:
    def test_values(self):
        assert WorkerState.idle == "idle"
        assert WorkerState.busy == "busy"
        assert WorkerState.draining == "draining"
        assert WorkerState.stopped == "stopped"
        assert WorkerState.unhealthy == "unhealthy"


# --- PoolConfig tests ---

class TestPoolConfig:
    def test_defaults(self):
        c = PoolConfig()
        assert c.min_workers == 1
        assert c.max_workers == 10
        assert c.scale_up_threshold == 5
        assert c.scale_down_threshold == 0
        assert c.health_check_interval == 10.0
        assert c.heartbeat_timeout == 60.0

    def test_custom(self):
        c = PoolConfig(min_workers=2, max_workers=20, scale_up_threshold=3)
        assert c.min_workers == 2
        assert c.max_workers == 20
        assert c.scale_up_threshold == 3

    def test_to_dict(self):
        c = PoolConfig(min_workers=3, max_workers=15)
        d = c.to_dict()
        assert d["min_workers"] == 3
        assert d["max_workers"] == 15
        assert "default_worker_capacity" in d


# --- WorkerInfo tests ---

class TestWorkerInfo:
    def test_create(self):
        worker = Worker(InMemoryQueue(), worker_id="w1")
        info = WorkerInfo(
            worker_id="w1",
            worker=worker,
            capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
            available=ResourceSpec(cpu=4.0, memory_mb=4096),
        )
        assert info.worker_id == "w1"
        assert info.state == WorkerState.idle
        assert info.is_available
        assert info.is_healthy

    def test_busy_not_available(self):
        worker = Worker(InMemoryQueue(), worker_id="w1")
        info = WorkerInfo(
            worker_id="w1", worker=worker,
            capacity=ResourceSpec(), available=ResourceSpec(),
            state=WorkerState.busy,
        )
        assert not info.is_available
        assert info.is_healthy  # busy is still healthy

    def test_unhealthy_not_healthy(self):
        worker = Worker(InMemoryQueue(), worker_id="w1")
        info = WorkerInfo(
            worker_id="w1", worker=worker,
            capacity=ResourceSpec(), available=ResourceSpec(),
            state=WorkerState.unhealthy,
        )
        assert not info.is_healthy

    def test_stopped_not_healthy(self):
        worker = Worker(InMemoryQueue(), worker_id="w1")
        info = WorkerInfo(
            worker_id="w1", worker=worker,
            capacity=ResourceSpec(), available=ResourceSpec(),
            state=WorkerState.stopped,
        )
        assert not info.is_healthy

    def test_update_heartbeat(self):
        worker = Worker(InMemoryQueue(), worker_id="w1")
        info = WorkerInfo(
            worker_id="w1", worker=worker,
            capacity=ResourceSpec(), available=ResourceSpec(),
        )
        old_hb = info.last_heartbeat
        _time.sleep(0.01)
        info.update_heartbeat()
        assert info.last_heartbeat > old_hb

    def test_to_dict(self):
        worker = Worker(InMemoryQueue(), worker_id="w1")
        info = WorkerInfo(
            worker_id="w1", worker=worker,
            capacity=ResourceSpec(cpu=2.0), available=ResourceSpec(cpu=1.0),
        )
        d = info.to_dict()
        assert d["worker_id"] == "w1"
        assert d["state"] == "idle"
        assert d["capacity"]["cpu"] == 2.0
        assert d["available"]["cpu"] == 1.0
        assert d["is_healthy"] is True


# --- WorkerPool: Worker management ---

class TestWorkerPoolManagement:
    def test_init(self):
        pool = WorkerPool(InMemoryQueue())
        assert pool.worker_count == 0
        assert not pool.is_running

    def test_add_worker(self):
        pool = WorkerPool(InMemoryQueue())
        info = pool.add_worker(capacity=ResourceSpec(cpu=4.0, memory_mb=4096))
        assert info.worker_id.startswith("pool_worker_")
        assert info.capacity.cpu == 4.0
        assert pool.worker_count == 1

    def test_add_worker_custom_id(self):
        pool = WorkerPool(InMemoryQueue())
        info = pool.add_worker(worker_id="custom_w1")
        assert info.worker_id == "custom_w1"

    def test_add_worker_default_capacity(self):
        pool = WorkerPool(InMemoryQueue(), config=PoolConfig(
            default_worker_capacity=ResourceSpec(cpu=2.0, memory_mb=1024),
        ))
        info = pool.add_worker()
        assert info.capacity.cpu == 2.0
        assert info.capacity.memory_mb == 1024

    def test_remove_worker(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        assert pool.remove_worker("w1") is True
        assert pool.worker_count == 0

    def test_remove_worker_not_found(self):
        pool = WorkerPool(InMemoryQueue())
        assert pool.remove_worker("nonexistent") is False

    def test_get_worker(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        info = pool.get_worker("w1")
        assert info is not None
        assert info.worker_id == "w1"

    def test_get_worker_not_found(self):
        pool = WorkerPool(InMemoryQueue())
        assert pool.get_worker("nonexistent") is None

    def test_list_workers(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        pool.add_worker(worker_id="w2")
        workers = pool.list_workers()
        assert len(workers) == 2


# --- WorkerPool: Resource-aware scheduling ---

class TestResourceScheduling:
    def test_find_capable_worker(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=4.0, memory_mb=4096))
        pool.add_worker(worker_id="w2", capacity=ResourceSpec(cpu=1.0, memory_mb=512))
        info = pool.find_capable_worker(ResourceSpec(cpu=2.0, memory_mb=2048))
        assert info is not None
        assert info.worker_id == "w1"

    def test_find_capable_worker_none_available(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=1.0, memory_mb=512))
        info = pool.find_capable_worker(ResourceSpec(cpu=4.0, memory_mb=4096))
        assert info is None

    def test_find_capable_worker_no_workers(self):
        pool = WorkerPool(InMemoryQueue())
        info = pool.find_capable_worker(ResourceSpec())
        assert info is None

    def test_assign_job(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=4.0, memory_mb=4096))
        info = pool.get_worker("w1")
        job = TaskJob(id="j1", task_type="test")
        req = ResourceSpec(cpu=1.0, memory_mb=512)
        pool.assign_job(info, job, req)
        assert info.state == WorkerState.busy
        assert info.current_job_id == "j1"
        assert info.available.cpu == 3.0
        assert info.available.memory_mb == 3584

    def test_release_worker(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=4.0, memory_mb=4096))
        info = pool.get_worker("w1")
        job = TaskJob(id="j1", task_type="test")
        req = ResourceSpec(cpu=1.0, memory_mb=512)
        pool.assign_job(info, job, req)
        pool.release_worker("w1", "j1", req)
        assert info.state == WorkerState.idle
        assert info.current_job_id is None
        assert info.available.cpu == 4.0
        assert info.available.memory_mb == 4096
        assert info.jobs_processed == 1

    def test_mark_job_result_success(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        pool.mark_job_result("w1", True)
        info = pool.get_worker("w1")
        assert info.jobs_succeeded == 1

    def test_mark_job_result_failure(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        pool.mark_job_result("w1", False)
        info = pool.get_worker("w1")
        assert info.jobs_failed == 1

    def test_submit_job(self):
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        job = TaskJob(id="j1", task_type="test")
        req = ResourceSpec(cpu=2.0, memory_mb=1024)
        job_id = pool.submit_job(job, resources=req)
        assert job_id == "j1"
        assert queue.size() == 1

    def test_process_job_on_worker(self):
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(
            worker_id="w1",
            capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
            handlers={"test": lambda j: {"result": "ok"}},
        )
        job = TaskJob(id="j1", task_type="test")
        req = ResourceSpec(cpu=1.0, memory_mb=512)
        result = pool.process_job_on_worker(job, req)
        assert result.success
        assert result.output == {"result": "ok"}
        info = pool.get_worker("w1")
        assert info.state == WorkerState.idle
        assert info.available.cpu == 4.0  # Resources released

    def test_process_job_insufficient_resources(self):
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=1.0, memory_mb=512))
        job = TaskJob(id="j1", task_type="test")
        req = ResourceSpec(cpu=4.0, memory_mb=4096)
        with pytest.raises(InsufficientResourcesError):
            pool.process_job_on_worker(job, req)

    def test_multiple_workers_resource_isolation(self):
        """Two workers with different capacities serve different job sizes."""
        queue = InMemoryQueue()
        pool = WorkerPool(queue)
        pool.add_worker(worker_id="small", capacity=ResourceSpec(cpu=1.0, memory_mb=512))
        pool.add_worker(worker_id="large", capacity=ResourceSpec(cpu=8.0, memory_mb=16384))

        # Large job should go to large worker
        info = pool.find_capable_worker(ResourceSpec(cpu=4.0, memory_mb=8192))
        assert info.worker_id == "large"

        # Small job can go to either (first match)
        info = pool.find_capable_worker(ResourceSpec(cpu=0.5, memory_mb=256))
        assert info is not None


# --- WorkerPool: Pool stats ---

class TestPoolStats:
    def test_worker_count(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        pool.add_worker(worker_id="w2")
        assert pool.worker_count == 2

    def test_idle_count(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        pool.add_worker(worker_id="w2")
        assert pool.idle_count == 2

    def test_busy_count(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=4.0, memory_mb=4096))
        info = pool.get_worker("w1")
        pool.assign_job(info, TaskJob(id="j1", task_type="test"), ResourceSpec(cpu=1.0))
        assert pool.busy_count == 1
        assert pool.idle_count == 0

    def test_pool_stats(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1", capacity=ResourceSpec(cpu=4.0, memory_mb=4096))
        pool.add_worker(worker_id="w2", capacity=ResourceSpec(cpu=2.0, memory_mb=2048))
        stats = pool.pool_stats()
        assert stats["worker_count"] == 2
        assert stats["idle_count"] == 2
        assert stats["busy_count"] == 0
        assert stats["total_capacity"]["cpu"] == 6.0  # 4.0 + 2.0
        assert stats["total_capacity"]["memory_mb"] == 6144  # 4096 + 2048
        assert "workers" in stats
        assert len(stats["workers"]) == 2


# --- WorkerPool: Heartbeat and health ---

class TestHealthChecks:
    def test_heartbeat(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        assert pool.heartbeat("w1") is True
        info = pool.get_worker("w1")
        assert info.state == WorkerState.idle  # Still healthy

    def test_heartbeat_not_found(self):
        pool = WorkerPool(InMemoryQueue())
        assert pool.heartbeat("nonexistent") is False

    def test_heartbeat_recovers_unhealthy(self):
        pool = WorkerPool(InMemoryQueue())
        pool.add_worker(worker_id="w1")
        info = pool.get_worker("w1")
        info.state = WorkerState.unhealthy
        pool.heartbeat("w1")
        assert info.state == WorkerState.idle


# --- WorkerPool: Start/Stop ---

class TestPoolStartStop:
    def test_start_creates_min_workers(self):
        queue = InMemoryQueue()
        pool = WorkerPool(queue, config=PoolConfig(min_workers=3, max_workers=10))
        pool.start()
        assert pool.worker_count == 3
        assert pool.is_running
        pool.stop()

    def test_stop_clears_workers(self):
        queue = InMemoryQueue()
        pool = WorkerPool(queue, config=PoolConfig(min_workers=2))
        pool.start()
        assert pool.worker_count == 2
        pool.stop()
        assert pool.worker_count == 0
        assert not pool.is_running

    def test_start_idempotent(self):
        queue = InMemoryQueue()
        pool = WorkerPool(queue, config=PoolConfig(min_workers=1))
        pool.start()
        pool.start()  # Should not double-start
        assert pool.worker_count == 1
        pool.stop()


# --- Module structure tests ---

class TestModuleStructure:
    def test_imports_from_distributed(self):
        from vsrs.distributed import (
            WorkerPool,
            ResourceSpec,
            PoolConfig,
            WorkerInfo,
            WorkerState,
            InsufficientResourcesError,
        )
        assert WorkerPool is not None
        assert ResourceSpec is not None

    def test_insufficient_resources_error(self):
        req = ResourceSpec(cpu=4.0, memory_mb=4096, gpu=1)
        err = InsufficientResourcesError("job1", req)
        assert err.job_id == "job1"
        assert err.required.cpu == 4.0
        assert "job1" in str(err)

    def test_logger_exists(self):
        from vsrs.distributed.pool import logger
        assert logger is not None
