"""Tests for the repair reasoner (Phase 5.3)."""

from vsrs.reasoning.protocol import (
    FailureSummary,
    PatchProposal,
    RepairInput,
    RepairOutput,
)
from vsrs.repair.repair_reasoner import RepairReasoner


def _make_failures() -> list[FailureSummary]:
    return [
        FailureSummary(
            check_type="existing_tests",
            status="fail",
            error_category="test_failure",
            error_message="test_valid: AssertionError: assert 1 == 2",
            failed_test_names=["test_valid"],
            relevant_file="tests/test_auth.py",
            relevant_line=5,
            suggested_fix="Review the failing assertion",
        ),
        FailureSummary(
            check_type="lint",
            status="fail",
            error_category="lint",
            error_message="src/auth.py:10:5: F401 unused import",
            relevant_file="src/auth.py",
            relevant_line=10,
            suggested_fix="Remove unused import",
        ),
    ]


class TestRepairReasoner:
    def test_repair_basic(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the empty password bug",
            prior_patch_diff="--- a/src/auth.py\n+++ b/src/auth.py\n",
            prior_attempt_no=1,
            failures=_make_failures(),
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert isinstance(output, RepairOutput)
        assert output.patch_proposal is not None
        assert output.failure_analysis

    def test_failure_analysis_mentions_categories(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=_make_failures(),
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert "test" in output.failure_analysis.lower()
        assert "lint" in output.failure_analysis.lower()

    def test_revised_assumptions(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="existing_tests",
                    status="fail",
                    error_category="test_failure",
                    error_message="test failed",
                ),
            ],
            prior_assumptions=["The fix is correct", "The behavior is right"],
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert len(output.revised_assumptions) > 0
        assert any("behavior" in a.lower() for a in output.revised_assumptions)

    def test_new_evidence_needed_for_import_error(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="dependency_validation",
                    status="fail",
                    error_category="import_error",
                    error_message="ImportError: No module named 'foo'",
                ),
            ],
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert any("module" in e.lower() or "import" in e.lower() for e in output.new_evidence_needed)

    def test_new_evidence_needed_for_type_error(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="type_check",
                    status="fail",
                    error_category="type_error",
                    error_message="incompatible type",
                ),
            ],
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert any("type" in e.lower() for e in output.new_evidence_needed)

    def test_no_failures(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=[],
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert "No failures" in output.failure_analysis

    def test_patch_proposal_has_files(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="syntax",
                    status="fail",
                    error_category="syntax",
                    error_message="src/auth.py:10: SyntaxError",
                    relevant_file="src/auth.py",
                    relevant_line=10,
                ),
            ],
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert "src/auth.py" in output.patch_proposal.changed_files

    def test_syntax_failure_analysis(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="syntax",
                    status="fail",
                    error_category="syntax",
                    error_message="src/auth.py:10: SyntaxError: invalid syntax",
                    relevant_file="src/auth.py",
                ),
            ],
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert "syntax" in output.failure_analysis.lower()

    def test_security_failure_analysis(self):
        reasoner = RepairReasoner()
        repair_input = RepairInput(
            task_instruction="Fix the bug",
            prior_patch_diff="diff",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="security_scan",
                    status="fail",
                    error_category="security",
                    error_message="B101 hardcoded password",
                ),
            ],
            remaining_attempts=2,
        )

        output = reasoner.repair(repair_input)

        assert "security" in output.failure_analysis.lower()
