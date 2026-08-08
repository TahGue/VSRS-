"""Tests for evaluation: scorer, reports, ablations, runner (Phase 13)."""

import json
from pathlib import Path
from typing import Any

import pytest

from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    FinalStatus,
    PatchCandidate,
    VerificationReport,
)
from vsrs.eval.ablations import (
    ABLATION_EXPERIMENTS,
    AblationConfig,
    AblationHarness,
    AblationResult,
)
from vsrs.eval.reports import CategoryBreakdown, EvaluationReport
from vsrs.eval.runner import BenchmarkRunner
from vsrs.eval.scorer import ScoreResult, detect_grounding_errors, score_task
from vsrs.eval.tasks import BenchmarkSet, BenchmarkTask, HiddenTest


def _make_patch(
    task_id: str = "task_001",
    attempt: int = 1,
    changed_files: list[str] | None = None,
    diff: str = "",
) -> PatchCandidate:
    if changed_files is None:
        changed_files = ["src/auth.py"]
    if not diff:
        diff = "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,2 +1,3 @@\n-old\n+new\n"
    return PatchCandidate(
        id=f"patch_{attempt:03d}",
        task_id=task_id,
        attempt_no=attempt,
        base_commit="abc123",
        diff=diff,
        changed_files=changed_files,
        assumptions=["assumption1"],
    )


def _make_report(
    required_passed: bool = True,
    unresolved: list[str] | None = None,
    checks: list[CheckResult] | None = None,
) -> VerificationReport:
    if checks is None:
        checks = [CheckResult(check_type="syntax", command="python -c 'pass'", status=CheckStatus.pass_)]
    return VerificationReport(
        id="report_001",
        patch_id="patch_001",
        checks=checks,
        required_passed=required_passed,
        final_status=FinalStatus.verified_candidate,
        blockers=[],
        unresolved_unknowns=unresolved or [],
    )


class TestScorer:
    def test_verified_success(self):
        patch = _make_patch()
        report = _make_report()
        result = score_task(
            patches=[patch],
            reports=[report],
            final_status=FinalStatus.verified_candidate,
            hidden_tests_passed=True,
            regression_tests_passed=True,
        )
        assert result.verified_success is True
        assert result.pass_at_1 is True
        assert result.repair_success is False
        assert result.regression is False

    def test_repair_success(self):
        p1 = _make_patch(attempt=1)
        p2 = _make_patch(attempt=2)
        report = _make_report()
        result = score_task(
            patches=[p1, p2],
            reports=[report, report],
            final_status=FinalStatus.verified_candidate,
            hidden_tests_passed=True,
        )
        assert result.verified_success is True
        assert result.pass_at_1 is False
        assert result.repair_success is True

    def test_regression(self):
        patch = _make_patch()
        report = _make_report()
        result = score_task(
            patches=[patch],
            reports=[report],
            final_status=FinalStatus.verified_candidate,
            hidden_tests_passed=True,
            regression_tests_passed=False,
        )
        assert result.regression is True
        assert result.verified_success is False

    def test_escalated(self):
        patch = _make_patch()
        report = _make_report()
        result = score_task(
            patches=[patch],
            reports=[report],
            final_status=FinalStatus.needs_review,
        )
        assert result.escalated is True
        assert result.verified_success is False

    def test_grounding_errors(self):
        patch = _make_patch()
        report = _make_report()
        result = score_task(
            patches=[patch],
            reports=[report],
            final_status=FinalStatus.verified_candidate,
            invented_symbols=3,
        )
        assert result.grounding_errors == 3

    def test_evidence_complete(self):
        patch = _make_patch()
        report = _make_report(required_passed=True, unresolved=[])
        result = score_task(
            patches=[patch],
            reports=[report],
            final_status=FinalStatus.verified_candidate,
            hidden_tests_passed=True,
        )
        assert result.evidence_complete is True

    def test_evidence_incomplete(self):
        patch = _make_patch()
        report = _make_report(required_passed=False, unresolved=["unknown1"])
        result = score_task(
            patches=[patch],
            reports=[report],
            final_status=FinalStatus.verified_candidate,
        )
        assert result.evidence_complete is False

    def test_patch_minimality(self):
        patch = _make_patch(changed_files=["a.py"])
        report = _make_report()
        result = score_task([patch], [report], FinalStatus.verified_candidate)
        assert result.patch_minimality == 0.9

    def test_test_adequacy_with_hidden_tests(self):
        patch = _make_patch()
        report = _make_report()
        result = score_task(
            [patch], [report], FinalStatus.verified_candidate,
            hidden_tests_total=3, new_tests_written=2,
        )
        assert 0.6 < result.test_adequacy < 0.7

    def test_test_adequacy_no_hidden_tests(self):
        patch = _make_patch()
        report = _make_report()
        result = score_task(
            [patch], [report], FinalStatus.verified_candidate,
            new_tests_written=1,
        )
        assert result.test_adequacy == 0.5

    def test_to_dict(self):
        patch = _make_patch()
        report = _make_report()
        result = score_task([patch], [report], FinalStatus.verified_candidate, hidden_tests_passed=True)
        d = result.to_dict()
        assert d["task_id"] == "task_001"
        assert d["verified_success"] is True
        assert "hidden_tests_passed" in d
        assert "new_tests_written" in d

    def test_detect_grounding_errors_none(self):
        patch = _make_patch(diff="--- a/f.py\n+++ b/f.py\n@@ -1 +1 @@\n-old\n+new\n")
        known = {"foo", "bar"}
        assert detect_grounding_errors(patch, known) == 0

    def test_detect_grounding_errors_with_imports(self):
        patch = _make_patch(
            diff="--- a/f.py\n+++ b/f.py\n@@ -0,0 +1 @@\n+from nonexistent_module import FakeClass\n"
        )
        known = {"foo", "bar"}
        errors = detect_grounding_errors(patch, known)
        assert errors >= 1

    def test_detect_grounding_errors_no_known_symbols(self):
        patch = _make_patch()
        assert detect_grounding_errors(patch, None) == 0


class TestReports:
    def test_add_result(self):
        report = EvaluationReport()
        result = ScoreResult(task_id="t1", verified_success=True, pass_at_1=True)
        report.add_result(result)
        assert report.total_tasks == 1
        assert report.verified_success_count == 1
        assert report.pass_at_1_count == 1

    def test_rates(self):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True, pass_at_1=True))
        report.add_result(ScoreResult(task_id="t2", verified_success=False, regression=True))
        assert report.verified_success_rate == 0.5
        assert report.regression_rate == 0.5

    def test_empty_report_rates(self):
        report = EvaluationReport()
        assert report.verified_success_rate == 0.0
        assert report.avg_tool_calls == 0.0

    def test_summary(self):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True, pass_at_1=True))
        text = report.summary()
        assert "Tasks: 1" in text
        assert "Verified success: 1" in text

    def test_to_dict(self):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True))
        d = report.to_dict()
        assert d["total_tasks"] == 1
        assert d["verified_success_count"] == 1
        assert "per_task" in d
        assert len(d["per_task"]) == 1

    def test_to_json(self, tmp_path):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True))
        output = tmp_path / "report.json"
        text = report.to_json(output)
        assert output.exists()
        data = json.loads(text)
        assert data["total_tasks"] == 1

    def test_to_csv(self, tmp_path):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True, tool_calls=3))
        output = tmp_path / "report.csv"
        text = report.to_csv(output)
        assert output.exists()
        lines = text.strip().split("\n")
        assert "task_id" in lines[0]
        assert "t1" in lines[1]

    def test_breakdown_by_category(self):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True), category="bugfix")
        report.add_result(ScoreResult(task_id="t2", verified_success=False), category="feature")
        report.add_result(ScoreResult(task_id="t3", verified_success=True), category="bugfix")
        breakdowns = report.breakdown_by_category()
        assert len(breakdowns) == 2
        bugfix = [b for b in breakdowns if b.category == "bugfix"][0]
        assert bugfix.total_tasks == 2
        assert bugfix.verified_success_count == 2
        feature = [b for b in breakdowns if b.category == "feature"][0]
        assert feature.verified_success_count == 0

    def test_breakdown_with_external_categories(self):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True))
        report.add_result(ScoreResult(task_id="t2", verified_success=False))
        breakdowns = report.breakdown_by_category(categories={"t1": "easy", "t2": "hard"})
        assert len(breakdowns) == 2

    def test_compare(self):
        baseline = EvaluationReport()
        baseline.add_result(ScoreResult(task_id="t1", verified_success=True))
        baseline.add_result(ScoreResult(task_id="t2", verified_success=False))

        experimental = EvaluationReport()
        experimental.add_result(ScoreResult(task_id="t1", verified_success=True))
        experimental.add_result(ScoreResult(task_id="t2", verified_success=True))

        delta = EvaluationReport.compare(baseline, experimental)
        assert delta["verified_success_rate_delta"] == 0.5

    def test_category_breakdown_to_dict(self):
        cb = CategoryBreakdown(category="bugfix", total_tasks=5, verified_success_count=3)
        d = cb.to_dict()
        assert d["category"] == "bugfix"
        assert d["total_tasks"] == 5
        assert d["verified_success_rate"] == 0.6


class TestAblations:
    def test_ablation_config(self):
        config = AblationConfig(name="test", description="test ablation", disable_components=["critic"])
        assert config.name == "test"
        assert config.disable_components == ["critic"]

    def test_ablation_result_from_report(self):
        report = EvaluationReport()
        report.add_result(ScoreResult(task_id="t1", verified_success=True, pass_at_1=True))
        report.add_result(ScoreResult(task_id="t2", verified_success=False))
        config = AblationConfig(name="test", description="test")
        result = AblationResult.from_report(config, report)
        assert result.verified_success_rate == 0.5
        assert result.total_tasks == 2

    def test_ablation_result_to_dict(self):
        config = AblationConfig(name="test", description="test", disable_components=["critic"])
        result = AblationResult(config=config, verified_success_rate=0.5, total_tasks=4)
        d = result.to_dict()
        assert d["config"]["name"] == "test"
        assert d["verified_success_rate"] == 0.5
        assert d["total_tasks"] == 4

    def test_ablation_experiments_include_baseline(self):
        names = [c.name for c in ABLATION_EXPERIMENTS]
        assert "baseline" in names
        assert "no_critic" in names
        assert "no_repair_loop" in names

    def test_ablation_harness_run_all(self):
        def mock_runner(config: AblationConfig) -> EvaluationReport:
            report = EvaluationReport()
            report.add_result(ScoreResult(task_id="t1", verified_success=True))
            return report

        harness = AblationHarness(
            runner=mock_runner,
            configs=[AblationConfig(name="baseline", description="base")],
        )
        results = harness.run_all()
        assert len(results) == 1
        assert results[0].config.name == "baseline"
        assert results[0].verified_success_rate == 1.0

    def test_ablation_harness_comparison_table(self):
        def mock_runner(config: AblationConfig) -> EvaluationReport:
            report = EvaluationReport()
            report.add_result(ScoreResult(task_id="t1", verified_success=True))
            return report

        harness = AblationHarness(
            runner=mock_runner,
            configs=[
                AblationConfig(name="baseline", description="base"),
                AblationConfig(name="no_critic", description="no critic", disable_components=["critic"]),
            ],
        )
        harness.run_all()
        table = harness.comparison_table()
        assert "baseline" in table
        assert "no_critic" in table
        assert "Verified%" in table

    def test_ablation_harness_empty_table(self):
        def mock_runner(config: AblationConfig) -> EvaluationReport:
            return EvaluationReport()

        harness = AblationHarness(runner=mock_runner)
        table = harness.comparison_table()
        assert "No ablation results" in table

    def test_ablation_harness_to_dict(self):
        def mock_runner(config: AblationConfig) -> EvaluationReport:
            report = EvaluationReport()
            report.add_result(ScoreResult(task_id="t1", verified_success=True))
            return report

        harness = AblationHarness(
            runner=mock_runner,
            configs=[AblationConfig(name="baseline", description="base")],
        )
        harness.run_all()
        data = harness.to_dict()
        assert len(data) == 1
        assert data[0]["config"]["name"] == "baseline"


class TestBenchmarkRunner:
    def _mock_task_runner(self, task: BenchmarkTask):
        patch = _make_patch(task_id=task.id)
        report = _make_report()
        extra = {
            "hidden_tests_passed": True,
            "hidden_tests_total": len(task.hidden_tests),
            "regression_tests_passed": True,
            "new_tests_written": 1,
        }
        return [patch], [report], FinalStatus.verified_candidate, extra

    def test_run_all(self):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        report = runner.run_all()
        assert report.total_tasks == len(bench)
        assert report.verified_success_count > 0

    def test_run_single(self):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        task = bench.all()[0]
        result = runner.run_single(task)
        assert result.task_id == task.id
        assert result.verified_success is True

    def test_get_result(self):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        runner.run_all()
        task = bench.all()[0]
        result = runner.get_result(task.id)
        assert result is not None
        assert result.task_id == task.id

    def test_get_result_not_found(self):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        assert runner.get_result("nonexistent") is None

    def test_export_json(self, tmp_path):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        runner.run_all()
        output = str(tmp_path / "results.json")
        runner.export_json(output)
        assert Path(output).exists()
        data = json.loads(Path(output).read_text())
        assert data["total_tasks"] > 0

    def test_export_csv(self, tmp_path):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        runner.run_all()
        output = str(tmp_path / "results.csv")
        runner.export_csv(output)
        assert Path(output).exists()
        lines = Path(output).read_text().strip().split("\n")
        assert "task_id" in lines[0]

    def test_summary(self):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        runner.run_all()
        text = runner.summary()
        assert "Tasks:" in text
        assert "Verified success:" in text

    def test_breakdown_after_run(self):
        bench = BenchmarkSet.seed()
        runner = BenchmarkRunner(bench, self._mock_task_runner)
        report = runner.run_all()
        breakdowns = report.breakdown_by_category()
        assert len(breakdowns) > 0
        categories = [b.category for b in breakdowns]
        assert "bugfix" in categories
