"""Tests for core schemas (Appendix A)."""

from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    EvidenceContract,
    EvidenceItem,
    EvidenceState,
    EvidenceType,
    FinalDecision,
    FinalStatus,
    FindingSeverity,
    GatePolicy,
    Hypothesis,
    PatchCandidate,
    ProvenanceEdge,
    ReviewFinding,
    RunEvent,
    Task,
    TaskRun,
    TaskState,
    TaskType,
    RiskLevel,
    RepositorySnapshot,
    VerificationReport,
)


def test_task_creation():
    task = Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=TaskType.bugfix,
        instruction="Fix empty password bug",
        acceptance_criteria=["reject empty password", "preserve valid login"],
        risk_level=RiskLevel.medium,
        required_gates=["syntax", "build", "existing_tests"],
    )
    assert task.type == TaskType.bugfix
    assert task.risk_level == RiskLevel.medium
    assert task.state == TaskState.intake
    assert len(task.acceptance_criteria) == 2
    assert len(task.required_gates) == 3


def test_evidence_item_creation():
    ev = EvidenceItem(
        id="ev_001",
        type=EvidenceType.structural,
        source="ast",
        locator="src/auth.py:42",
        content="def validate_password(pw: str) -> bool",
        state=EvidenceState.observed_true,
    )
    assert ev.type == EvidenceType.structural
    assert ev.state == EvidenceState.observed_true
    assert ev.locator == "src/auth.py:42"


def test_patch_candidate_creation():
    patch = PatchCandidate(
        id="patch_001",
        task_id="task_001",
        attempt_no=1,
        base_commit="abc123",
        diff="--- a/src/auth.py\n+++ b/src/auth.py\n",
        changed_files=["src/auth.py"],
        changed_symbols=["validate_password"],
        assumptions=["empty string is the only edge case"],
        predicted_effects=["empty password will be rejected"],
        falsification_checks=["test_empty_password_rejected"],
    )
    assert patch.attempt_no == 1
    assert len(patch.changed_files) == 1
    assert "validate_password" in patch.changed_symbols


def test_verification_report_creation():
    report = VerificationReport(
        patch_id="patch_001",
        checks=[
            CheckResult(
                check_type="pytest",
                command="pytest tests/test_auth.py",
                exit_code=0,
                status=CheckStatus.pass_,
            ),
            CheckResult(
                check_type="ruff",
                command="ruff check src/auth.py",
                exit_code=0,
                status=CheckStatus.pass_,
            ),
        ],
        required_passed=True,
        final_status=FinalStatus.verified_candidate,
    )
    assert len(report.checks) == 2
    assert report.required_passed is True
    assert report.final_status == FinalStatus.verified_candidate


def test_evidence_contract():
    contract = EvidenceContract(
        change_id="change_001",
        requirement_ids=["req_001"],
        affected_symbols=["validate_password"],
        supporting_evidence=["ev_001", "ev_002"],
        assumptions=["empty string is the only edge case"],
        expected_behavior_changes=["empty password rejected"],
        falsification_checks=["test_empty_password_rejected"],
        verification_results=["verify_001"],
        unresolved_questions=[],
        final_status=FinalStatus.verified_candidate,
        complete=True,
    )
    assert contract.complete is True
    assert len(contract.supporting_evidence) == 2


def test_hypothesis_creation():
    hyp = Hypothesis(
        id="hyp_001",
        task_id="task_001",
        statement="Validation path treats empty string as valid non-null value",
        unknowns=["whether another layer rejects it"],
        supporting_evidence_ids=["ev_001"],
    )
    assert "empty string" in hyp.statement
    assert len(hyp.unknowns) == 1


def test_review_finding_creation():
    finding = ReviewFinding(
        id="finding_001",
        patch_id="patch_001",
        severity=FindingSeverity.major,
        category="missing_edge_case",
        evidence_refs=["ev_001"],
        text="Whitespace-only password not handled",
    )
    assert finding.severity == FindingSeverity.major


def test_provenance_edge():
    edge = ProvenanceEdge(
        from_type="requirement",
        from_id="req_001",
        relation="motivates",
        to_type="patch",
        to_id="patch_001",
    )
    assert edge.relation == "motivates"


def test_run_event():
    event = RunEvent(
        id="evt_001",
        run_id="run_001",
        task_id="task_001",
        state=TaskState.verifying,
        event_type="tool_call",
        payload={"tool": "pytest", "exit_code": 0},
    )
    assert event.event_type == "tool_call"
    assert event.payload["tool"] == "pytest"


def test_task_run():
    run = TaskRun(
        id="run_001",
        task_id="task_001",
        repo_snapshot_id="repo_001",
        state=TaskState.intake,
        max_attempts=3,
    )
    assert run.state == TaskState.intake
    assert run.max_attempts == 3
    assert run.final_decision is None


def test_repository_snapshot():
    repo = RepositorySnapshot(
        id="repo_001",
        root="/path/to/repo",
        commit_hash="abc123def456",
        language_profile="python",
    )
    assert repo.language_profile == "python"
    assert repo.commit_hash == "abc123def456"


def test_final_decision():
    decision = FinalDecision(
        task_id="task_001",
        status=FinalStatus.verified_candidate,
        blockers=[],
        summary="All required gates passed",
        provenance_id="prov_001",
    )
    assert decision.status == FinalStatus.verified_candidate
    assert len(decision.blockers) == 0


def test_all_task_types():
    for t in TaskType:
        assert t.value in ["bugfix", "feature", "refactor", "test", "security", "migration"]


def test_all_evidence_states():
    for s in EvidenceState:
        assert s.value in [
            "observed_true", "observed_false", "inferred_supported",
            "unknown", "conflicted", "not_applicable",
        ]


def test_all_gate_policies():
    for p in GatePolicy:
        assert p.value in [
            "mandatory", "mandatory_when_applicable",
            "policy_dependent", "risk_dependent", "optional",
        ]
