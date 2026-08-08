"""Tests for the pytest adapter (Phase 4.2)."""

from vsrs.core.schemas import CheckStatus
from vsrs.verify.pytest_adapter import PytestAdapter, PytestResult, TestFailure


class TestPytestOutputParsing:
    def test_parse_all_passed(self):
        adapter = PytestAdapter()
        output = (
            "collected 5 items\n\n"
            "tests/test_a.py::test_one PASSED [ 20%]\n"
            "tests/test_a.py::test_two PASSED [ 40%]\n"
            "tests/test_b.py::test_three PASSED [ 60%]\n"
            "tests/test_b.py::test_four PASSED [ 80%]\n"
            "tests/test_b.py::test_five PASSED [100%]\n\n"
            "============================== 5 passed in 0.15s ===============================\n"
        )
        result = adapter._parse_output(output, exit_code=0, duration=0.15)

        assert result.exit_code == 0
        assert result.passed == 5
        assert result.failed == 0
        assert result.errors == 0
        assert result.collected == 5
        assert result.all_passed

    def test_parse_with_failures(self):
        adapter = PytestAdapter()
        output = (
            "collected 3 items\n\n"
            "tests/test_a.py::test_one PASSED [ 33%]\n"
            "tests/test_a.py::test_two FAILED [ 66%]\n"
            "tests/test_a.py::test_three PASSED [100%]\n\n"
            "============================== 1 failed, 2 passed in 0.15s ===============================\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.15)

        assert result.exit_code == 1
        assert result.passed == 2
        assert result.failed == 1
        assert not result.all_passed

    def test_parse_with_errors(self):
        adapter = PytestAdapter()
        output = (
            "collected 2 items\n\n"
            "tests/test_a.py::test_one PASSED [ 50%]\n"
            "tests/test_b.py ERROR [100%]\n\n"
            "============================== 1 passed, 1 error in 0.15s ===============================\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.15)

        assert result.passed == 1
        assert result.errors == 1

    def test_parse_with_skipped(self):
        adapter = PytestAdapter()
        output = (
            "collected 3 items\n\n"
            "tests/test_a.py::test_one PASSED [ 33%]\n"
            "tests/test_a.py::test_two SKIPPED [ 66%]\n"
            "tests/test_a.py::test_three PASSED [100%]\n\n"
            "============================== 2 passed, 1 skipped in 0.15s ===============================\n"
        )
        result = adapter._parse_output(output, exit_code=0, duration=0.15)

        assert result.passed == 2
        assert result.skipped == 1

    def test_parse_failures_detail(self):
        adapter = PytestAdapter()
        output = (
            "tests/test_a.py::test_two FAILED [ 50%]\n"
            "tests/test_a.py::test_two - AssertionError: assert 1 == 2\n"
        )
        result = adapter._parse_output(output, exit_code=1, duration=0.0)

        assert len(result.failures) >= 1
        failure = result.failures[0]
        assert failure.test_name == "test_two"
        assert "test_a.py" in failure.file

    def test_total_property(self):
        result = PytestResult(exit_code=0, passed=3, failed=1, errors=0, skipped=2)
        assert result.total == 6


class TestPytestCheckResult:
    def test_to_check_result_pass(self):
        adapter = PytestAdapter()
        result = PytestResult(exit_code=0, passed=5)
        check = adapter.to_check_result(result)

        assert check.check_type == "existing_tests"
        assert check.status == CheckStatus.pass_
        assert check.exit_code == 0

    def test_to_check_result_fail(self):
        adapter = PytestAdapter()
        result = PytestResult(
            exit_code=1,
            passed=3,
            failed=2,
            failures=[TestFailure(test_name="test_x", error_type="AssertionError")],
        )
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.fail
        assert check.exit_code == 1
        assert "test_x" in check.error_message

    def test_to_check_result_error(self):
        adapter = PytestAdapter()
        result = PytestResult(exit_code=-1)
        check = adapter.to_check_result(result)

        assert check.status == CheckStatus.error

    def test_to_check_result_custom_type(self):
        adapter = PytestAdapter()
        result = PytestResult(exit_code=0, passed=1)
        check = adapter.to_check_result(result, check_type="new_targeted_tests")

        assert check.check_type == "new_targeted_tests"
