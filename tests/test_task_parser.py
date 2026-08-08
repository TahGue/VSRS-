"""Tests for the task parser (Phase 3.2)."""

from vsrs.core.schemas import RiskLevel, TaskType
from vsrs.reasoning.task_parser import TaskParser


class TestTaskParser:
    def test_basic_parse(self):
        parser = TaskParser()
        result = parser.parse("Fix the empty password bug in src/auth.py")

        assert result.expected_behavior
        assert result.task_type == "bugfix"
        assert "src/auth.py" in result.affected_areas

    def test_bugfix_classification(self):
        parser = TaskParser()
        result = parser.parse("Fix the crash in the login function")
        assert result.task_type == "bugfix"

    def test_feature_classification(self):
        parser = TaskParser()
        result = parser.parse("Add a new config validation feature")
        assert result.task_type == "feature"

    def test_refactor_classification(self):
        parser = TaskParser()
        result = parser.parse("Refactor the authentication module to simplify it")
        assert result.task_type == "refactor"

    def test_security_classification(self):
        parser = TaskParser()
        result = parser.parse("Fix SQL injection vulnerability in the query builder")
        assert result.task_type == "security"
        assert result.risk_level == "high"

    def test_risk_assessment_low(self):
        parser = TaskParser()
        result = parser.parse("Fix a simple typo in the error message")
        assert result.risk_level == "low"

    def test_risk_assessment_medium(self):
        parser = TaskParser()
        result = parser.parse("Refactor the config module to use new settings")
        assert result.risk_level in ("medium", "high")

    def test_risk_assessment_high(self):
        parser = TaskParser()
        result = parser.parse("Fix SQL injection in authentication password handling")
        assert result.risk_level == "high"

    def test_constraint_extraction(self):
        parser = TaskParser()
        result = parser.parse(
            "Fix the password validation without breaking existing logins. "
            "Must not change the API."
        )
        assert any("breaking" in c or "change the API" in c for c in result.constraints)

    def test_acceptance_criteria_from_list(self):
        parser = TaskParser()
        result = parser.parse(
            "Fix the password bug.\n"
            "1. Empty passwords must be rejected\n"
            "2. Valid logins must still work\n"
        )
        assert len(result.acceptance_criteria) >= 2

    def test_acceptance_criteria_from_bullets(self):
        parser = TaskParser()
        result = parser.parse(
            "Fix the password bug.\n"
            "- Empty passwords rejected\n"
            "- Valid logins preserved\n"
        )
        assert len(result.acceptance_criteria) >= 2

    def test_acceptance_criteria_provided(self):
        parser = TaskParser()
        result = parser.parse(
            "Fix the bug",
            acceptance_criteria=["criterion 1", "criterion 2"],
        )
        assert result.acceptance_criteria == ["criterion 1", "criterion 2"]

    def test_affected_areas_file_paths(self):
        parser = TaskParser()
        result = parser.parse("Fix the bug in src/auth.py and tests/test_auth.py")
        assert "src/auth.py" in result.affected_areas
        assert "tests/test_auth.py" in result.affected_areas

    def test_affected_areas_dotted_modules(self):
        parser = TaskParser()
        result = parser.parse("Fix src.auth.validate_password function")
        assert any("auth" in a for a in result.affected_areas)

    def test_expected_behavior_extraction(self):
        parser = TaskParser()
        result = parser.parse("The password validation should reject empty passwords.")
        assert "reject empty passwords" in result.expected_behavior.lower()

    def test_risk_factors(self):
        parser = TaskParser()
        result = parser.parse("Fix SQL injection in authentication")
        assert len(result.risk_factors) > 0
        assert any("injection" in f or "authentication" in f for f in result.risk_factors)

    def test_predefined_task_type(self):
        parser = TaskParser()
        result = parser.parse("Fix the bug", task_type=TaskType.feature)
        assert result.task_type == "feature"

    def test_predefined_risk_level(self):
        parser = TaskParser()
        result = parser.parse("Fix the bug", risk_level=RiskLevel.high)
        assert result.risk_level == "high"
