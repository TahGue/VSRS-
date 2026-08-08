"""Benchmark task definitions for VSRS evaluation.

Implements Phase 0: create representative tasks from controlled sample repos.
Tasks are immutable once frozen. Each task includes hidden acceptance tests
that the model cannot see or edit.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from vsrs.core.schemas import RiskLevel, TaskType


class HiddenTest(BaseModel):
    """A hidden acceptance test that the model cannot see or edit.

    Used for anti-gaming: the model's own tests cannot certify its own bugs.
    """

    name: str
    test_code: str
    expected_pass: bool = True


class BenchmarkTask(BaseModel):
    """A benchmark task definition with hidden tests.

    Frozen once created — do not modify after the evaluation set is frozen.
    """

    id: str
    name: str
    description: str
    task_type: TaskType
    risk_level: RiskLevel = RiskLevel.low
    instruction: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_gates: list[str] = Field(default_factory=list)
    repo_url: str = ""
    repo_commit: str = ""
    setup_commands: list[str] = Field(default_factory=list)
    hidden_tests: list[HiddenTest] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    difficulty: str = "easy"  # easy, medium, hard

    def to_task_dict(self, repo_snapshot_id: str) -> dict:
        """Convert to a Task-compatible dict (without hidden tests)."""
        return {
            "id": self.id,
            "repo_snapshot_id": repo_snapshot_id,
            "type": self.task_type.value,
            "instruction": self.instruction,
            "acceptance_criteria": self.acceptance_criteria,
            "risk_level": self.risk_level.value,
            "required_gates": self.required_gates,
        }


# --- Seed benchmark tasks ---


def _seed_tasks() -> list[BenchmarkTask]:
    """Create seed benchmark tasks for Phase 0."""
    return [
        BenchmarkTask(
            id="bench-001",
            name="empty-password-rejection",
            description="Fix login bug where an empty password is accepted",
            task_type=TaskType.bugfix,
            risk_level=RiskLevel.medium,
            instruction=(
                "Fix login bug where an empty password is accepted. "
                "The validate_password function in src/auth.py should reject "
                "empty strings. Add a regression test."
            ),
            acceptance_criteria=[
                "empty password must be rejected",
                "existing valid login behavior must remain unchanged",
                "add a regression test",
            ],
            required_gates=["syntax", "build", "existing_tests", "new_targeted_tests"],
            hidden_tests=[
                HiddenTest(
                    name="test_empty_password_rejected_hidden",
                    test_code=(
                        "def test_empty_password_rejected_hidden():\n"
                        "    from src.auth import validate_password\n"
                        "    assert validate_password('') == False\n"
                    ),
                ),
                HiddenTest(
                    name="test_valid_password_still_works_hidden",
                    test_code=(
                        "def test_valid_password_still_works_hidden():\n"
                        "    from src.auth import validate_password\n"
                        "    assert validate_password('securePass123') == True\n"
                    ),
                ),
            ],
            tags=["auth", "validation", "bugfix"],
            difficulty="easy",
        ),
        BenchmarkTask(
            id="bench-002",
            name="off-by-one-loop",
            description="Fix off-by-one error in range processing loop",
            task_type=TaskType.bugfix,
            risk_level=RiskLevel.low,
            instruction=(
                "The process_range function in src/range_utils.py has an "
                "off-by-one error. It should process items from index 0 to n-1 "
                "inclusive, but currently stops one element short. Fix the loop "
                "boundary and add a regression test."
            ),
            acceptance_criteria=[
                "all n elements are processed",
                "existing behavior for empty ranges is preserved",
                "add a regression test",
            ],
            required_gates=["syntax", "build", "existing_tests", "new_targeted_tests"],
            hidden_tests=[
                HiddenTest(
                    name="test_full_range_processed_hidden",
                    test_code=(
                        "def test_full_range_processed_hidden():\n"
                        "    from src.range_utils import process_range\n"
                        "    result = process_range(5)\n"
                        "    assert len(result) == 5\n"
                        "    assert result == [0, 1, 2, 3, 4]\n"
                    ),
                ),
            ],
            tags=["loop", "boundary", "bugfix"],
            difficulty="easy",
        ),
        BenchmarkTask(
            id="bench-003",
            name="null-check-missing",
            description="Add missing null check before attribute access",
            task_type=TaskType.bugfix,
            risk_level=RiskLevel.medium,
            instruction=(
                "The get_user_email function in src/user_service.py crashes "
                "with AttributeError when the user object is None. Add a null "
                "check and return None in that case. Add a regression test."
            ),
            acceptance_criteria=[
                "function returns None when user is None",
                "function returns email when user is valid",
                "add a regression test",
            ],
            required_gates=["syntax", "build", "existing_tests", "new_targeted_tests", "type_check"],
            hidden_tests=[
                HiddenTest(
                    name="test_none_user_returns_none_hidden",
                    test_code=(
                        "def test_none_user_returns_none_hidden():\n"
                        "    from src.user_service import get_user_email\n"
                        "    assert get_user_email(None) is None\n"
                    ),
                ),
            ],
            tags=["null-safety", "bugfix"],
            difficulty="easy",
        ),
        BenchmarkTask(
            id="bench-004",
            name="add-config-validation",
            description="Add validation for missing required config fields",
            task_type=TaskType.feature,
            risk_level=RiskLevel.medium,
            instruction=(
                "Add validation to the Config class in src/config.py that raises "
                "ValueError when required fields (host, port, database) are missing. "
                "Add tests for both valid and invalid configurations."
            ),
            acceptance_criteria=[
                "ValueError raised when any required field is missing",
                "valid config loads without error",
                "add tests for valid and invalid cases",
            ],
            required_gates=["syntax", "build", "existing_tests", "new_targeted_tests", "type_check"],
            hidden_tests=[
                HiddenTest(
                    name="test_missing_host_raises_hidden",
                    test_code=(
                        "import pytest\n"
                        "def test_missing_host_raises_hidden():\n"
                        "    from src.config import Config\n"
                        "    with pytest.raises(ValueError):\n"
                        "        Config(port=5432, database='test')\n"
                    ),
                ),
                HiddenTest(
                    name="test_valid_config_loads_hidden",
                    test_code=(
                        "def test_valid_config_loads_hidden():\n"
                        "    from src.config import Config\n"
                        "    c = Config(host='localhost', port=5432, database='test')\n"
                        "    assert c.host == 'localhost'\n"
                    ),
                ),
            ],
            tags=["config", "validation", "feature"],
            difficulty="medium",
        ),
        BenchmarkTask(
            id="bench-005",
            name="sql-injection-fix",
            description="Fix SQL injection vulnerability in query builder",
            task_type=TaskType.security,
            risk_level=RiskLevel.high,
            instruction=(
                "The search_users function in src/db.py constructs SQL queries "
                "using string formatting, which is vulnerable to SQL injection. "
                "Fix it to use parameterized queries. Add a test that verifies "
                "injection attempts are neutralized."
            ),
            acceptance_criteria=[
                "parameterized queries are used",
                "injection attempts do not alter query structure",
                "existing search functionality is preserved",
                "add a security regression test",
            ],
            required_gates=[
                "syntax", "build", "existing_tests", "new_targeted_tests",
                "security_scan", "static_analysis",
            ],
            hidden_tests=[
                HiddenTest(
                    name="test_injection_neutralized_hidden",
                    test_code=(
                        "def test_injection_neutralized_hidden():\n"
                        "    from src.db import search_users\n"
                        "    # This should not return all users or drop tables\n"
                        "    result = search_users(\"'; DROP TABLE users; --\")\n"
                        "    assert isinstance(result, list)\n"
                    ),
                ),
            ],
            tags=["security", "sql-injection", "parameterized"],
            difficulty="medium",
        ),
        BenchmarkTask(
            id="bench-006",
            name="extract-helper-function",
            description="Refactor duplicated validation logic into a shared helper",
            task_type=TaskType.refactor,
            risk_level=RiskLevel.low,
            instruction=(
                "The validate_email function is duplicated in src/user_service.py "
                "and src/notification_service.py. Extract it into a shared helper "
                "in src/validators.py and update both modules to use it. Ensure "
                "all existing tests still pass."
            ),
            acceptance_criteria=[
                "no duplicated validation logic",
                "all existing tests pass",
                "public API is unchanged",
            ],
            required_gates=["syntax", "build", "existing_tests", "api_compatibility"],
            tags=["refactor", "deduplication"],
            difficulty="medium",
            hidden_tests=[
                HiddenTest(
                    name="test_no_duplicate_validate_email_hidden",
                    test_code=(
                        "def test_no_duplicate_validate_email_hidden():\n"
                        "    import ast\n"
                        "    import pathlib\n"
                        "    # Check that validate_email is defined only in src/validators.py\n"
                        "    sources = ['src/user_service.py', 'src/notification_service.py']\n"
                        "    for src in sources:\n"
                        "        tree = ast.parse(pathlib.Path(src).read_text())\n"
                        "        for node in ast.walk(tree):\n"
                        "            if isinstance(node, ast.FunctionDef) and node.name == 'validate_email':\n"
                        "                assert False, f'validate_email still defined in {src}'\n"
                    ),
                ),
            ],
        ),
    ]


class BenchmarkSet:
    """A collection of benchmark tasks for evaluation.

    Implements Section 14.1: dev, validation, test, and adversarial sets.
    """

    def __init__(self, tasks: list[BenchmarkTask] | None = None) -> None:
        self._tasks: dict[str, BenchmarkTask] = {}
        if tasks:
            for task in tasks:
                self._tasks[task.id] = task

    @classmethod
    def seed(cls) -> BenchmarkSet:
        """Create a benchmark set with seed tasks."""
        return cls(_seed_tasks())

    @classmethod
    def from_directory(cls, dir_path: Path) -> BenchmarkSet:
        """Load benchmark tasks from a directory of JSON files."""
        tasks = []
        for json_file in sorted(dir_path.glob("*.json")):
            with open(json_file) as f:
                data = json.load(f)
            tasks.append(BenchmarkTask(**data))
        return cls(tasks)

    def add(self, task: BenchmarkTask) -> None:
        """Add a task to the set."""
        self._tasks[task.id] = task

    def get(self, task_id: str) -> BenchmarkTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def all(self) -> list[BenchmarkTask]:
        """Get all tasks."""
        return list(self._tasks.values())

    def by_type(self, task_type: TaskType) -> list[BenchmarkTask]:
        """Filter tasks by type."""
        return [t for t in self._tasks.values() if t.task_type == task_type]

    def by_difficulty(self, difficulty: str) -> list[BenchmarkTask]:
        """Filter tasks by difficulty."""
        return [t for t in self._tasks.values() if t.difficulty == difficulty]

    def by_tag(self, tag: str) -> list[BenchmarkTask]:
        """Filter tasks by tag."""
        return [t for t in self._tasks.values() if tag in t.tags]

    def save_to_directory(self, dir_path: Path) -> None:
        """Save all tasks to a directory as individual JSON files."""
        dir_path.mkdir(parents=True, exist_ok=True)
        for task in self._tasks.values():
            path = dir_path / f"{task.id}.json"
            with open(path, "w") as f:
                json.dump(task.model_dump(mode="json"), f, indent=2)

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, task_id: str) -> bool:
        return task_id in self._tasks
