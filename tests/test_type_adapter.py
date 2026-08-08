"""Tests for the type check adapter (Phase 4.4)."""

from vsrs.core.schemas import CheckStatus
from vsrs.verify.type_adapter import TypeCheckAdapter, TypeCheckResult, TypeError


class TestTypeCheckOutputParsing:
    def test_parse_clean(self):
        adapter = TypeCheckAdapter()
        output = "Success: no issues found in 5 source files\n"
        result = adapter._parse_output(output, exit_code=0, duration=0.5)

        assert result.exit_code == 0
        assert len(result.errors) == 0
        assert result.clean

    def test_parse_errors(self):
        adapter = TypeCheckAdapter()
        output = (
            "src/auth.py:10: error: Argument 1 to \"validate\" has incompatible type \"int\"; expected \"str\"  [arg-type]\n"
            "src/auth.py:20:5: error: Function \"login\" does not return a value  [return-value]\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.5)

        assert result.exit_code == 1
        assert len(result.errors) == 2
        assert result.errors[0].file == "src/auth.py"
        assert result.errors[0].line == 10
        assert "incompatible" in result.errors[0].message
        assert result.errors[0].code == "arg-type"
        assert result.errors[1].column == 5

    def test_parse_notes(self):
        adapter = TypeCheckAdapter()
        output = (
            "src/auth.py:10: note: This is a hint about the error above\n"
        )
        result = adapter._parse_output(output, exit_code=0, duration=0.5)

        assert len(result.errors) == 0
        assert len(result.notes) == 1
        assert result.notes[0].severity == "note"

    def test_parse_mixed(self):
        adapter = TypeCheckAdapter()
        output = (
            "src/auth.py:10: error: Incompatible types  [arg-type]\n"
            "src/auth.py:11: note: See documentation for details\n"
            "src/auth.py:20: error: Missing return statement  [empty-body]\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.5)

        assert len(result.errors) == 2
        assert len(result.notes) == 1
        assert result.error_count == 2


class TestTypeCheckCheckResult:
    def test_to_check_result_pass(self):
        adapter = TypeCheckAdapter()
        result = TypeCheckResult(exit_code=0)
        check = adapter.to_check_result(result)

        assert check.check_type == "type_check"
        assert check.status == CheckStatus.pass_

    def test_to_check_result_fail(self):
        adapter = TypeCheckAdapter()
        result = TypeCheckResult(
            exit_code=1,
            errors=[
                TypeError(file="src/auth.py", line=10, message="Incompatible types"),
            ],
        )
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.fail
        assert "src/auth.py" in check.error_message

    def test_to_check_result_error(self):
        adapter = TypeCheckAdapter()
        result = TypeCheckResult(exit_code=-1, error="mypy not found")
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.error
