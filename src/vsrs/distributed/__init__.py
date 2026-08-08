"""Distributed execution for VSRS.

Provides a task queue abstraction for parallel benchmark runs and
verification workers. Supports in-memory (testing) and Redis (production)
backends.
"""

from __future__ import annotations

from vsrs.distributed.base import (
    JobResult,
    JobStatus,
    TaskJob,
    TaskQueue,
)
from vsrs.distributed.benchmark import DistributedBenchmarkRunner
from vsrs.distributed.memory import InMemoryQueue
from vsrs.distributed.redis_queue import RedisQueue
from vsrs.distributed.worker import Worker

__all__ = [
    "DistributedBenchmarkRunner",
    "InMemoryQueue",
    "JobResult",
    "JobStatus",
    "RedisQueue",
    "TaskJob",
    "TaskQueue",
    "Worker",
]
