"""Tests for the lint adapter (Phase 4.3)."""

from vsrs.core.schemas import CheckStatus
from vsrs.verify.lint_adapter import LintAdapter, LintResult, LintFinding


class TestLintOutputParsing:
    def test_parse_clean(self):
        adapter = LintAdapter()
        output = "All checks passed!\n"
        result = adapter._parse_output(output, exit_code=0, duration=0.1)

        assert result.exit_code == 0
        assert len(result.findings) == 0
        assert result.clean

    def test_parse_findings(self):
        adapter = LintAdapter()
        output = (
            "src/auth.py:10:5: E101 indentation contains mixed spaces and tabs\n"
            "src/auth.py:20:1: F401 'os' imported but unused\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.1)

        assert result.exit_code == 1
        assert len(result.findings) == 2
        assert result.findings[0].file == "src/auth.py"
        assert result.findings[0].line == 10
        assert result.findings[0].column == 5
        assert result.findings[0].rule_code == "E101"
        assert "indentation" in result.findings[0].message
        assert result.findings[1].rule_code == "F401"

    def test_parse_no_findings_in_clean_output(self):
        adapter = LintAdapter()
        output = "No issues found.\n"
        result = adapter._parse_output(output, exit_code=0, duration=0.1)

        assert len(result.findings) == 0


class TestLintCheckResult:
    def test_to_check_result_pass(self):
        adapter = LintAdapter()
        result = LintResult(exit_code=0)
        check = adapter.to_check_result(result)

        assert check.check_type == "lint"
        assert check.status == CheckStatus.pass_

    def test_to_check_result_fail(self):
        adapter = LintAdapter()
        result = LintResult(
            exit_code=1,
            findings=[
                LintFinding(file="src/auth.py", line=10, rule_code="F401", message="unused import"),
            ],
        )
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.fail
        assert "F401" in check.error_message
        assert "src/auth.py" in check.error_message

    def test_to_check_result_error(self):
        adapter = LintAdapter()
        result = LintResult(exit_code=-1, error="ruff not found")
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.error
        assert "ruff not found" in check.error_message
