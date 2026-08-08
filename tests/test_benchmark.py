"""Tests for the benchmark task system (Phase 0)."""

import json

from vsrs.core.schemas import RiskLevel, TaskType
from vsrs.eval.tasks import BenchmarkSet, BenchmarkTask, HiddenTest


class TestBenchmarkTask:
    def test_creation(self):
        task = BenchmarkTask(
            id="bench-test-001",
            name="test-task",
            description="A test task",
            task_type=TaskType.bugfix,
            instruction="Fix a bug",
            acceptance_criteria=["criterion 1"],
            hidden_tests=[
                HiddenTest(name="test_1", test_code="def test_1(): assert True"),
            ],
            tags=["auth", "bugfix"],
            difficulty="easy",
        )
        assert task.id == "bench-test-001"
        assert task.task_type == TaskType.bugfix
        assert len(task.hidden_tests) == 1
        assert task.hidden_tests[0].name == "test_1"

    def test_to_task_dict(self):
        task = BenchmarkTask(
            id="bench-test-001",
            name="test-task",
            description="A test task",
            task_type=TaskType.feature,
            instruction="Add a feature",
        )
        d = task.to_task_dict("repo_001")
        assert d["repo_snapshot_id"] == "repo_001"
        assert d["type"] == "feature"
        assert "hidden_tests" not in d


class TestBenchmarkSet:
    def test_seed(self):
        bench = BenchmarkSet.seed()
        assert len(bench) >= 5

    def test_get(self):
        bench = BenchmarkSet.seed()
        task = bench.get("bench-001")
        assert task is not None
        assert task.name == "empty-password-rejection"

    def test_by_type(self):
        bench = BenchmarkSet.seed()
        bugfixes = bench.by_type(TaskType.bugfix)
        assert len(bugfixes) >= 3
        for t in bugfixes:
            assert t.task_type == TaskType.bugfix

    def test_by_difficulty(self):
        bench = BenchmarkSet.seed()
        easy = bench.by_difficulty("easy")
        assert len(easy) >= 2

    def test_by_tag(self):
        bench = BenchmarkSet.seed()
        auth_tasks = bench.by_tag("auth")
        assert len(auth_tasks) >= 1

    def test_contains(self):
        bench = BenchmarkSet.seed()
        assert "bench-001" in bench
        assert "nonexistent" not in bench

    def test_save_and_load(self, tmp_path):
        bench = BenchmarkSet.seed()
        bench.save_to_directory(tmp_path)

        # Check files were created
        files = list(tmp_path.glob("*.json"))
        assert len(files) >= 5

        # Load back
        loaded = BenchmarkSet.from_directory(tmp_path)
        assert len(loaded) == len(bench)
        assert loaded.get("bench-001") is not None
        assert loaded.get("bench-001").name == "empty-password-rejection"

    def test_all_tasks_have_hidden_tests(self):
        bench = BenchmarkSet.seed()
        for task in bench.all():
            assert len(task.hidden_tests) > 0, f"Task {task.id} has no hidden tests"

    def test_all_tasks_have_acceptance_criteria(self):
        bench = BenchmarkSet.seed()
        for task in bench.all():
            assert len(task.acceptance_criteria) > 0, f"Task {task.id} has no acceptance criteria"

    def test_security_task_has_security_gates(self):
        bench = BenchmarkSet.seed()
        security_task = bench.get("bench-005")
        assert security_task is not None
        assert "security_scan" in security_task.required_gates
        assert "static_analysis" in security_task.required_gates
        assert security_task.risk_level == RiskLevel.high
