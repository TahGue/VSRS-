"""Tests for the security adapter (Phase 4.5)."""

from vsrs.core.schemas import CheckStatus
from vsrs.verify.security_adapter import SecurityAdapter, SecurityResult, SecurityFinding


class TestSecurityOutputParsing:
    def test_parse_clean(self):
        adapter = SecurityAdapter()
        output = "[main]\tINFO\tNo issues found.\n"
        result = adapter._parse_output(output, exit_code=0, duration=0.1)

        assert result.exit_code == 0
        assert len(result.findings) == 0
        assert result.clean

    def test_parse_findings(self):
        adapter = SecurityAdapter()
        output = (
            ">> Issue: [B101:hardcoded_password_string] Severity: High Confidence: High\n"
            "   Location: src/auth.py:15\n"
            "   More Info: https://bandit.readthedocs.io/en/latest/plugins/b101_hardcoded_password_string.html\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.1)

        assert result.exit_code == 1
        assert len(result.findings) == 1
        finding = result.findings[0]
        assert finding.test_id == "B101"
        assert finding.test_name == "hardcoded_password_string"
        assert finding.severity == "HIGH"
        assert finding.confidence == "HIGH"
        assert finding.file == "src/auth.py"
        assert finding.line == 15

    def test_parse_multiple_findings(self):
        adapter = SecurityAdapter()
        output = (
            ">> Issue: [B101:hardcoded_password_string] Severity: High Confidence: High\n"
            "   Location: src/auth.py:15\n"
            ">> Issue: [B602:subprocess_popen_with_shell_equals_true] Severity: Medium Confidence: High\n"
            "   Location: src/utils.py:30\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.1)

        assert len(result.findings) == 2
        assert result.findings[0].severity == "HIGH"
        assert result.findings[1].severity == "MEDIUM"
        assert result.high_severity_count == 1
        assert result.medium_severity_count == 1


class TestSecurityCheckResult:
    def test_to_check_result_pass(self):
        adapter = SecurityAdapter()
        result = SecurityResult(exit_code=0)
        check = adapter.to_check_result(result)

        assert check.check_type == "security_scan"
        assert check.status == CheckStatus.pass_

    def test_to_check_result_fail(self):
        adapter = SecurityAdapter()
        result = SecurityResult(
            exit_code=1,
            findings=[
                SecurityFinding(
                    file="src/auth.py", line=15, test_id="B101",
                    severity="HIGH", message="hardcoded password",
                ),
            ],
        )
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.fail
        assert "B101" in check.error_message
        assert "HIGH" in check.error_message

    def test_to_check_result_error(self):
        adapter = SecurityAdapter()
        result = SecurityResult(exit_code=-1, error="bandit not found")
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.error

    def test_to_check_result_custom_type(self):
        adapter = SecurityAdapter()
        result = SecurityResult(exit_code=0)
        check = adapter.to_check_result(result, check_type="static_analysis")

        assert check.check_type == "static_analysis"
