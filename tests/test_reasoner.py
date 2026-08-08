"""Tests for the reasoner (Phase 3.3)."""

from vsrs.core.schemas import RiskLevel, Task, TaskType
from vsrs.reasoning.reasoner import Reasoner
from vsrs.reasoning.task_parser import TaskParser
from vsrs.repo.retrieval import RetrievedEvidence, RetrievalResult


def _make_task(
    instruction: str = "Fix the empty password bug in validate_password",
    task_type: TaskType = TaskType.bugfix,
    risk_level: RiskLevel = RiskLevel.medium,
) -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=task_type,
        instruction=instruction,
        acceptance_criteria=["reject empty password", "preserve valid login"],
        risk_level=risk_level,
        required_gates=["syntax", "build", "existing_tests"],
    )


def _make_evidence() -> RetrievalResult:
    return RetrievalResult(
        query="Fix validate_password",
        evidence=[
            RetrievedEvidence(
                kind="symbol",
                locator="src/auth.py:7",
                content="def validate_password(pw: str) -> bool:\n    return bool(pw)",
                source="symbol_index",
                rank=1,
                metadata={
                    "name": "validate_password",
                    "kind": "function",
                    "qualified_name": "src.auth.validate_password",
                    "signature": "def validate_password(pw: str) -> bool",
                },
            ),
            RetrievedEvidence(
                kind="test",
                locator="tests/test_auth.py:5",
                content="def test_valid_password():\n    assert validate_password('secret')",
                source="test_index",
                rank=2,
                metadata={"name": "test_valid_password", "target_module": "auth"},
            ),
            RetrievedEvidence(
                kind="file",
                locator="src/auth.py",
                content="def validate_password(pw: str) -> bool:\n    return bool(pw)",
                source="file_index",
                rank=2,
                metadata={"module": "src.auth"},
            ),
        ],
    )


class TestReasoner:
    def test_reason_basic(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert output.parsed_task is not None
        assert output.evidence_summary is not None
        assert output.hypothesis is not None
        assert output.predicted_effects is not None
        assert output.falsification_plan is not None
        assert output.patch_proposal is not None

    def test_evidence_summary(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert "src.auth.validate_password" in output.evidence_summary.relevant_symbols
        assert "src/auth.py" in output.evidence_summary.relevant_files
        assert "test_valid_password" in output.evidence_summary.relevant_tests
        assert len(output.evidence_summary.evidence_locators) == 3

    def test_hypothesis_bugfix(self):
        reasoner = Reasoner()
        task = _make_task(instruction="Fix the empty password bug in validate_password")
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert "bug" in output.hypothesis.statement.lower() or "validate_password" in output.hypothesis.statement
        assert len(output.hypothesis.supporting_evidence) > 0
        assert output.hypothesis.confidence == "inferred_supported"

    def test_hypothesis_feature(self):
        reasoner = Reasoner()
        task = _make_task(
            instruction="Add a new config validation feature",
            task_type=TaskType.feature,
        )
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert "new functionality" in output.hypothesis.statement.lower()

    def test_hypothesis_security(self):
        reasoner = Reasoner()
        task = _make_task(
            instruction="Fix SQL injection vulnerability in query builder",
            task_type=TaskType.security,
            risk_level=RiskLevel.high,
        )
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert "security" in output.hypothesis.statement.lower()

    def test_predicted_effects(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert "src/auth.py" in output.predicted_effects.files_to_change
        assert "src.auth.validate_password" in output.predicted_effects.symbols_to_change
        assert len(output.predicted_effects.behavior_preserved) >= 2

    def test_falsification_plan(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert len(output.falsification_plan.checks) > 0
        assert len(output.falsification_plan.new_tests_needed) > 0
        assert "Empty input" in output.falsification_plan.edge_cases

    def test_patch_proposal(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert output.patch_proposal.changed_files
        assert output.patch_proposal.rationale

    def test_unknowns_when_no_evidence(self):
        reasoner = Reasoner()
        task = _make_task()
        empty_evidence = RetrievalResult(query="test", evidence=[])

        output = reasoner.reason(task, empty_evidence)

        assert len(output.hypothesis.unknowns) > 0
        assert output.hypothesis.confidence == "unknown"

    def test_to_hypothesis_model(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)
        model = reasoner.to_hypothesis_model("task_001", output.hypothesis)

        assert model.task_id == "task_001"
        assert model.statement == output.hypothesis.statement
        assert model.id.startswith("hyp_")

    def test_to_patch_model(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)
        model = reasoner.to_patch_model("task_001", output.patch_proposal, attempt_no=1)

        assert model.task_id == "task_001"
        assert model.attempt_no == 1
        assert model.id.startswith("patch_")

    def test_evidence_contract_refs(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()

        output = reasoner.reason(task, evidence)

        assert len(output.evidence_contract_refs) == 3

    def test_with_pre_parsed_task(self):
        reasoner = Reasoner()
        task = _make_task()
        evidence = _make_evidence()
        parser = TaskParser()
        parsed = parser.parse(task.instruction, task.acceptance_criteria, task.type, task.risk_level)

        output = reasoner.reason(task, evidence, parsed_task=parsed)

        assert output.parsed_task is parsed
