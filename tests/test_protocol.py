"""Tests for the reasoning protocol schemas (Phase 3.1)."""

from vsrs.reasoning.protocol import (
    EvidenceSummary,
    FalsificationPlan,
    FailureSummary,
    ParsedTask,
    PatchProposal,
    PredictedEffects,
    ReasoningHypothesis,
    ReasoningOutput,
    RepairInput,
    RepairOutput,
)


class TestParsedTask:
    def test_creation(self):
        pt = ParsedTask(
            expected_behavior="Reject empty passwords",
            constraints=["must not break existing logins"],
            acceptance_criteria=["empty password rejected", "valid login preserved"],
            risk_level="medium",
            task_type="bugfix",
        )
        assert pt.expected_behavior == "Reject empty passwords"
        assert len(pt.constraints) == 1
        assert len(pt.acceptance_criteria) == 2
        assert pt.risk_level == "medium"

    def test_defaults(self):
        pt = ParsedTask(expected_behavior="Do something")
        assert pt.constraints == []
        assert pt.risk_level == "low"
        assert pt.task_type == "bugfix"


class TestEvidenceSummary:
    def test_creation(self):
        es = EvidenceSummary(
            relevant_symbols=["src.auth.validate_password"],
            relevant_files=["src/auth.py"],
            relevant_tests=["test_empty_password"],
        )
        assert len(es.relevant_symbols) == 1
        assert len(es.relevant_files) == 1


class TestReasoningHypothesis:
    def test_creation(self):
        h = ReasoningHypothesis(
            statement="Empty string treated as valid",
            supporting_evidence=["src/auth.py:7"],
            unknowns=["whether another layer rejects it"],
            confidence="inferred_supported",
        )
        assert "Empty string" in h.statement
        assert h.confidence == "inferred_supported"


class TestPredictedEffects:
    def test_creation(self):
        pe = PredictedEffects(
            files_to_change=["src/auth.py"],
            symbols_to_change=["validate_password"],
            behavior_changes=["empty password rejected"],
            behavior_preserved=["valid logins still work"],
        )
        assert len(pe.files_to_change) == 1
        assert len(pe.behavior_preserved) == 1


class TestFalsificationPlan:
    def test_creation(self):
        fp = FalsificationPlan(
            checks=["test_empty_password_rejected"],
            new_tests_needed=["test_empty_password"],
            edge_cases=["empty string", "whitespace only"],
        )
        assert len(fp.checks) == 1
        assert len(fp.edge_cases) == 2


class TestPatchProposal:
    def test_creation(self):
        pp = PatchProposal(
            diff="--- a/src/auth.py\n+++ b/src/auth.py\n",
            changed_files=["src/auth.py"],
            changed_symbols=["validate_password"],
            rationale="Add empty password check",
        )
        assert "auth.py" in pp.diff
        assert len(pp.changed_files) == 1

    def test_empty_diff(self):
        pp = PatchProposal(diff="", rationale="No changes needed")
        assert pp.diff == ""


class TestReasoningOutput:
    def test_full_output(self):
        output = ReasoningOutput(
            parsed_task=ParsedTask(expected_behavior="Fix bug"),
            evidence_summary=EvidenceSummary(),
            hypothesis=ReasoningHypothesis(statement="Bug in validation"),
            predicted_effects=PredictedEffects(),
            falsification_plan=FalsificationPlan(),
            patch_proposal=PatchProposal(diff="", rationale="fix"),
        )
        assert output.parsed_task.expected_behavior == "Fix bug"
        assert output.hypothesis.statement == "Bug in validation"
        assert output.timestamp is not None

    def test_json_serialization(self):
        output = ReasoningOutput(
            parsed_task=ParsedTask(expected_behavior="Fix bug"),
            evidence_summary=EvidenceSummary(),
            hypothesis=ReasoningHypothesis(statement="Bug"),
            predicted_effects=PredictedEffects(),
            falsification_plan=FalsificationPlan(),
            patch_proposal=PatchProposal(diff="", rationale="fix"),
        )
        d = output.model_dump(mode="json")
        assert "parsed_task" in d
        assert "hypothesis" in d
        assert "patch_proposal" in d


class TestRepairInput:
    def test_creation(self):
        ri = RepairInput(
            task_instruction="Fix empty password",
            prior_patch_diff="--- a/file.py\n+++ b/file.py\n",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="pytest",
                    status="fail",
                    error_category="test_failure",
                    error_message="test_empty_password failed",
                ),
            ],
            remaining_attempts=2,
        )
        assert ri.prior_attempt_no == 1
        assert len(ri.failures) == 1
        assert ri.failures[0].error_category == "test_failure"


class TestRepairOutput:
    def test_creation(self):
        ro = RepairOutput(
            patch_proposal=PatchProposal(diff="new diff", rationale="fixed"),
            failure_analysis="Prior patch didn't handle empty string",
            revised_assumptions=["empty string is the edge case"],
        )
        assert ro.patch_proposal.diff == "new diff"
        assert "empty string" in ro.failure_analysis
