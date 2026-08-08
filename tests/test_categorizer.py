"""Tests for the failure categorizer (Phase 5.1)."""

from vsrs.core.schemas import CheckResult, CheckStatus, VerificationReport
from vsrs.repair.categorizer import (
    FailureCategorizer,
    categorize_error,
    extract_failed_test_names,
    extract_file_and_line,
    suggest_fix,
)


class TestCategorizeError:
    def test_syntax(self):
        assert categorize_error("syntax", "SyntaxError: invalid syntax") == "syntax"

    def test_test_failure(self):
        assert categorize_error("existing_tests", "AssertionError: assert 1 == 2") == "test_failure"

    def test_import_error_in_tests(self):
        assert categorize_error("existing_tests", "ModuleNotFoundError: No module named 'foo'") == "import_error"

    def test_type_error(self):
        assert categorize_error("type_check", "error: incompatible type") == "type_error"

    def test_lint(self):
        assert categorize_error("lint", "F401 unused import") == "lint"

    def test_security(self):
        assert categorize_error("security_scan", "B101 hardcoded password") == "security"

    def test_dependency_import(self):
        assert categorize_error("dependency_validation", "ImportError: cannot import") == "import_error"

    def test_other(self):
        assert categorize_error("unknown_check", "something weird happened") == "other"


class TestExtractFileAndLine:
    def test_extract_py_file(self):
        f, l = extract_file_and_line("src/auth.py:10: error")
        assert f == "src/auth.py"
        assert l == 10

    def test_extract_no_line(self):
        f, l = extract_file_and_line("no file reference here")
        assert f == ""
        assert l is None

    def test_extract_file_in_quotes(self):
        f, l = extract_file_and_line('File "src/auth.py", line 42')
        assert f == "src/auth.py"
        assert l == 42


class TestExtractFailedTestNames:
    def test_extract_from_assertion(self):
        names = extract_failed_test_names("test_valid: AssertionError: assert False")
        assert "test_valid" in names

    def test_extract_from_failed_line(self):
        names = extract_failed_test_names("tests/test_auth.py::test_valid FAILED")
        assert "test_valid" in names

    def test_no_names(self):
        names = extract_failed_test_names("no test names here")
        assert len(names) == 0


class TestSuggestFix:
    def test_syntax_suggestion(self):
        s = suggest_fix("syntax", "SyntaxError", "src/auth.py", 10)
        assert "syntax" in s.lower()
        assert "src/auth.py" in s

    def test_test_failure_suggestion(self):
        s = suggest_fix("test_failure", "AssertionError")
        assert "assertion" in s.lower() or "behavior" in s.lower()

    def test_import_error_suggestion(self):
        s = suggest_fix("import_error", "ModuleNotFoundError")
        assert "module" in s.lower() or "import" in s.lower()


class TestFailureCategorizer:
    def test_categorize_report_with_failures(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(
                    check_type="syntax",
                    command="ast.parse",
                    exit_code=0,
                    status=CheckStatus.pass_,
                ),
                CheckResult(
                    check_type="existing_tests",
                    command="pytest",
                    exit_code=1,
                    status=CheckStatus.fail,
                    error_message="test_valid: AssertionError: assert 1 == 2",
                ),
                CheckResult(
                    check_type="lint",
                    command="ruff",
                    exit_code=1,
                    status=CheckStatus.fail,
                    error_message="src/auth.py:10:5: F401 unused import",
                ),
            ],
        )
        categorizer = FailureCategorizer()
        summaries = categorizer.categorize(report)

        assert len(summaries) == 2  # only failed checks
        assert summaries[0].error_category == "test_failure"
        assert summaries[1].error_category == "lint"

    def test_categorize_report_all_passed(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(
                    check_type="syntax",
                    command="ast.parse",
                    exit_code=0,
                    status=CheckStatus.pass_,
                ),
            ],
        )
        categorizer = FailureCategorizer()
        summaries = categorizer.categorize(report)

        assert len(summaries) == 0

    def test_categorize_skips_skip_status(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(
                    check_type="type_check",
                    command="mypy",
                    status=CheckStatus.skip,
                ),
                CheckResult(
                    check_type="existing_tests",
                    command="pytest",
                    exit_code=1,
                    status=CheckStatus.fail,
                    error_message="test failed",
                ),
            ],
        )
        categorizer = FailureCategorizer()
        summaries = categorizer.categorize(report)

        assert len(summaries) == 1

    def test_has_blocking_failures_true(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(
                    check_type="syntax",
                    command="ast.parse",
                    exit_code=1,
                    status=CheckStatus.fail,
                    error_message="SyntaxError",
                ),
            ],
        )
        categorizer = FailureCategorizer()
        assert categorizer.has_blocking_failures(report)

    def test_has_blocking_failures_false(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(
                    check_type="syntax",
                    command="ast.parse",
                    exit_code=0,
                    status=CheckStatus.pass_,
                ),
            ],
        )
        categorizer = FailureCategorizer()
        assert not categorizer.has_blocking_failures(report)

    def test_failure_categories(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(
                    check_type="syntax",
                    command="ast.parse",
                    exit_code=1,
                    status=CheckStatus.fail,
                    error_message="SyntaxError",
                ),
                CheckResult(
                    check_type="lint",
                    command="ruff",
                    exit_code=1,
                    status=CheckStatus.fail,
                    error_message="F401",
                ),
            ],
        )
        categorizer = FailureCategorizer()
        categories = categorizer.failure_categories(report)

        assert "syntax" in categories
        assert "lint" in categories

    def test_categorize_single_check(self):
        check = CheckResult(
            check_type="existing_tests",
            command="pytest",
            exit_code=1,
            status=CheckStatus.fail,
            error_message="test_x: AssertionError",
        )
        categorizer = FailureCategorizer()
        summary = categorizer.categorize_check(check)

        assert summary.error_category == "test_failure"
        assert summary.check_type == "existing_tests"
        assert summary.status == "fail"
        assert "test_x" in summary.failed_test_names

    def test_suggested_fix_in_summary(self):
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(
                    check_type="syntax",
                    command="ast.parse",
                    exit_code=1,
                    status=CheckStatus.fail,
                    error_message="src/auth.py:10: SyntaxError: invalid syntax",
                ),
            ],
        )
        categorizer = FailureCategorizer()
        summaries = categorizer.categorize(report)

        assert summaries[0].suggested_fix
        assert "src/auth.py" in summaries[0].suggested_fix
        assert summaries[0].relevant_file == "src/auth.py"
        assert summaries[0].relevant_line == 10
