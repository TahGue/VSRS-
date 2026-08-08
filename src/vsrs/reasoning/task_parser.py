"""Task parser: extract behavior, constraints, acceptance criteria, risk (Section 7.1).

Stage 1 of the reasoning protocol. Parses a natural language task description
into a structured ParsedTask with expected behavior, constraints, acceptance
criteria, risk level, and affected areas.
"""

from __future__ import annotations

import re

from vsrs.core.logging import get_logger
from vsrs.core.schemas import RiskLevel, TaskType
from vsrs.reasoning.protocol import ParsedTask

logger = get_logger("reasoning.task_parser")


# Keywords for risk assessment
_HIGH_RISK_KEYWORDS = {
    "security", "injection", "authentication", "authorization", "password",
    "credential", "encrypt", "decrypt", "sql", "xss", "csrf",
    "migration", "schema", "database", "deploy", "production",
    "api", "breaking", "deprecate", "remove", "delete",
}
_MEDIUM_RISK_KEYWORDS = {
    "refactor", "rename", "move", "restructure", "merge",
    "config", "settings", "environment", "dependency",
    "performance", "optimize", "cache", "concurrent", "thread",
    "async", "await", "lock", "mutex",
}

# Keywords for task type classification
_TASK_TYPE_KEYWORDS: dict[TaskType, set[str]] = {
    TaskType.security: {"security", "vulnerability", "injection", "cve", "sanitize", "escape"},
    TaskType.feature: {"add", "implement", "create", "new", "support", "enable", "introduce"},
    TaskType.refactor: {"refactor", "rename", "extract", "move", "restructure", "cleanup", "simplify"},
    TaskType.test: {"test", "coverage", "unit test", "integration test", "mock"},
    TaskType.migration: {"migrate", "migration", "upgrade", "port", "schema change"},
    TaskType.bugfix: {"fix", "bug", "error", "crash", "wrong", "incorrect", "broken", "fail"},
}


class TaskParser:
    """Parse natural language task descriptions into structured form.

    Implements Stage 1 of the reasoning protocol (Section 7.1).
    """

    def parse(
        self,
        instruction: str,
        acceptance_criteria: list[str] | None = None,
        task_type: TaskType | None = None,
        risk_level: RiskLevel | None = None,
    ) -> ParsedTask:
        """Parse a task instruction into a ParsedTask.

        Args:
            instruction: Natural language task description.
            acceptance_criteria: Pre-defined acceptance criteria (if any).
            task_type: Pre-defined task type (if any).
            risk_level: Pre-defined risk level (if any).

        Returns:
            ParsedTask with extracted fields.
        """
        instruction_lower = instruction.lower()

        # Determine task type
        if task_type is None:
            task_type = self._classify_task_type(instruction_lower)

        # Determine risk level
        if risk_level is None:
            risk_level = self._assess_risk(instruction_lower, task_type)

        # Extract expected behavior
        expected_behavior = self._extract_expected_behavior(instruction)

        # Extract constraints
        constraints = self._extract_constraints(instruction)

        # Use provided acceptance criteria or extract from instruction
        if acceptance_criteria is None:
            acceptance_criteria = self._extract_acceptance_criteria(instruction)

        # Identify affected areas
        affected_areas = self._extract_affected_areas(instruction)

        return ParsedTask(
            expected_behavior=expected_behavior,
            constraints=constraints,
            acceptance_criteria=acceptance_criteria,
            risk_level=risk_level.value,
            risk_factors=self._extract_risk_factors(instruction_lower, task_type),
            task_type=task_type.value,
            affected_areas=affected_areas,
        )

    def _classify_task_type(self, text: str) -> TaskType:
        """Classify the task type from the instruction text."""
        scores: dict[TaskType, int] = {t: 0 for t in TaskType}

        for task_type, keywords in _TASK_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[task_type] += 1

        # Default to bugfix if no clear winner
        best = max(scores, key=lambda t: scores[t])
        if scores[best] == 0:
            return TaskType.bugfix
        return best

    def _assess_risk(self, text: str, task_type: TaskType) -> RiskLevel:
        """Assess risk level from keywords and task type."""
        # Security tasks are always at least medium risk
        if task_type == TaskType.security:
            return RiskLevel.high

        high_count = sum(1 for kw in _HIGH_RISK_KEYWORDS if kw in text)
        medium_count = sum(1 for kw in _MEDIUM_RISK_KEYWORDS if kw in text)

        if high_count >= 2:
            return RiskLevel.high
        if high_count >= 1 or medium_count >= 2:
            return RiskLevel.medium
        return RiskLevel.low

    def _extract_expected_behavior(self, instruction: str) -> str:
        """Extract the expected behavior from the instruction.

        Looks for patterns like "should", "must", "need to", "expected to".
        Falls back to the full instruction if no clear pattern is found.
        """
        # Try to find behavior statements
        patterns = [
            r"(?:should|must|needs? to|expected to|is supposed to)\s+(.+?)(?:\.|$)",
            r"(?:ensure|make sure|guarantee)\s+(?:that\s+)?(.+?)(?:\.|$)",
            r"(?:fix|resolve|address)\s+(.+?)(?:\.|$)",
        ]

        behaviors: list[str] = []
        for pattern in patterns:
            matches = re.findall(pattern, instruction, re.IGNORECASE)
            behaviors.extend(matches)

        if behaviors:
            return "; ".join(behaviors[:3])
        return instruction.strip()

    def _extract_constraints(self, instruction: str) -> list[str]:
        """Extract constraints from the instruction.

        Looks for patterns indicating constraints: "without", "while preserving",
        "must not", "should not", "only", "no more than".
        """
        constraints: list[str] = []

        patterns = [
            (r"without\s+(.+?)(?:\.|;|,|$)", "without"),
            (r"while preserving\s+(.+?)(?:\.|;|,|$)", "preserve"),
            (r"must not\s+(.+?)(?:\.|;|,|$)", "must not"),
            (r"should not\s+(.+?)(?:\.|;|,|$)", "should not"),
            (r"no more than\s+(.+?)(?:\.|;|,|$)", "limit"),
            (r"only\s+(?:if|when)\s+(.+?)(?:\.|;|,|$)", "conditional"),
            (r"do not\s+(.+?)(?:\.|;|,|$)", "do not"),
        ]

        for pattern, _label in patterns:
            matches = re.findall(pattern, instruction, re.IGNORECASE)
            for m in matches:
                constraints.append(m.strip())

        return constraints

    def _extract_acceptance_criteria(self, instruction: str) -> list[str]:
        """Extract acceptance criteria from the instruction.

        Looks for numbered lists, bullet points, or "acceptance criteria" sections.
        """
        criteria: list[str] = []

        # Numbered list: 1. ... 2. ...
        numbered = re.findall(r"^\d+\.\s+(.+)$", instruction, re.MULTILINE)
        criteria.extend(numbered)

        # Bullet points: - ... or * ...
        bulleted = re.findall(r"^[-*]\s+(.+)$", instruction, re.MULTILINE)
        criteria.extend(bulleted)

        # "acceptance criteria:" section
        ac_match = re.search(
            r"acceptance criteria:?\s*\n((?:.*\n?)*?)(?:\n\n|\Z)",
            instruction, re.IGNORECASE,
        )
        if ac_match:
            for line in ac_match.group(1).strip().splitlines():
                line = line.strip()
                if line and line not in criteria:
                    criteria.append(line)

        # If no criteria found, generate from expected behavior
        if not criteria:
            # Look for "should" statements as implicit criteria
            should_matches = re.findall(
                r"(?:should|must)\s+(.+?)(?:\.|;|,|$)", instruction, re.IGNORECASE,
            )
            criteria.extend(should_matches)

        return criteria

    def _extract_affected_areas(self, instruction: str) -> list[str]:
        """Extract likely affected files, modules, or symbols from the instruction.

        Looks for file paths, module names, function names, class names.
        """
        areas: list[str] = []

        # File paths: src/auth.py, tests/test_auth.py
        file_paths = re.findall(r'[\w/]+\.\w+', instruction)
        areas.extend(file_paths)

        # Dotted module paths: src.auth.validate_password
        dotted = re.findall(r'\b[a-z_][\w]*(?:\.[a-z_][\w]*)+\b', instruction)
        areas.extend(dotted)

        # Function/method names after keywords: "fix validate_password", "update login"
        func_patterns = [
            r"(?:fix|update|modify|change|implement|add|remove|refactor)\s+(?:the\s+)?(\w+)\s+(?:function|method|class)",
            r"(?:in|of|for)\s+(?:the\s+)?(\w+)\s+(?:function|method|class)",
        ]
        for pattern in func_patterns:
            matches = re.findall(pattern, instruction, re.IGNORECASE)
            areas.extend(matches)

        # Deduplicate
        seen: set[str] = set()
        unique: list[str] = []
        for a in areas:
            if a.lower() not in seen:
                seen.add(a.lower())
                unique.append(a)

        return unique

    def _extract_risk_factors(self, text: str, task_type: TaskType) -> list[str]:
        """Extract specific risk factors from the instruction."""
        factors: list[str] = []

        for kw in _HIGH_RISK_KEYWORDS:
            if kw in text:
                factors.append(f"mentions {kw}")

        for kw in _MEDIUM_RISK_KEYWORDS:
            if kw in text:
                factors.append(f"involves {kw}")

        if task_type == TaskType.security:
            factors.append("security-sensitive task")
        if task_type == TaskType.migration:
            factors.append("migration may affect existing data")

        return factors
