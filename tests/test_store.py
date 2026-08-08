"""Tests for the SQLite persistence layer (Phase 1.2)."""

import tempfile
from pathlib import Path

from vsrs.core.ids import generate_evidence_id, generate_finding_id, generate_hypothesis_id, generate_patch_id, generate_provenance_id, generate_run_id, generate_task_id
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
    Hypothesis,
    PatchCandidate,
    ProvenanceEdge,
    RepositorySnapshot,
    ReviewFinding,
    RunEvent,
    Task,
    TaskRun,
    TaskState,
    TaskType,
    RiskLevel,
    VerificationReport,
)
from vsrs.core.store import Store


class TestStore:
    def _get_store(self, tmp_path: Path) -> Store:
        return Store(str(tmp_path / "test.db"))

    def test_repository_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            repo = RepositorySnapshot(
                id="repo_001",
                root="/path/to/repo",
                commit_hash="abc123",
            )
            store.save_repository(repo)
            loaded = store.get_repository("repo_001")
            assert loaded is not None
            assert loaded.root == "/path/to/repo"
            assert loaded.commit_hash == "abc123"

    def test_task_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            task = Task(
                id="task_001",
                repo_snapshot_id="repo_001",
                type=TaskType.bugfix,
                instruction="Fix empty password bug",
                acceptance_criteria=["reject empty", "preserve valid"],
                risk_level=RiskLevel.medium,
                required_gates=["syntax", "build"],
            )
            store.save_task(task)
            loaded = store.get_task("task_001")
            assert loaded is not None
            assert loaded.type == TaskType.bugfix
            assert loaded.instruction == "Fix empty password bug"
            assert len(loaded.acceptance_criteria) == 2
            assert loaded.risk_level == RiskLevel.medium

    def test_run_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            run = TaskRun(
                id="run_001",
                task_id="task_001",
                repo_snapshot_id="repo_001",
                state=TaskState.verifying,
                attempt_no=2,
            )
            store.save_run(run)
            loaded = store.get_run("run_001")
            assert loaded is not None
            assert loaded.state == TaskState.verifying
            assert loaded.attempt_no == 2

    def test_run_with_final_decision(self, tmp_path):
        with self._get_store(tmp_path) as store:
            decision = FinalDecision(
                task_id="task_001",
                status=FinalStatus.verified_candidate,
                summary="All gates passed",
                provenance_id="prov_001",
            )
            run = TaskRun(
                id="run_002",
                task_id="task_001",
                repo_snapshot_id="repo_001",
                state=TaskState.verified,
                final_decision=decision,
            )
            store.save_run(run)
            loaded = store.get_run("run_002")
            assert loaded is not None
            assert loaded.final_decision is not None
            assert loaded.final_decision.status == FinalStatus.verified_candidate

    def test_evidence_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            ev = EvidenceItem(
                id="ev_001",
                type=EvidenceType.structural,
                source="ast",
                locator="src/auth.py:42",
                content="def validate_password(pw)",
                state=EvidenceState.observed_true,
            )
            store.save_evidence(ev, task_id="task_001")
            items = store.get_evidence_for_task("task_001")
            assert len(items) == 1
            assert items[0].type == EvidenceType.structural
            assert items[0].locator == "src/auth.py:42"

    def test_hypothesis_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            hyp = Hypothesis(
                id="hyp_001",
                task_id="task_001",
                statement="Empty string treated as valid",
                unknowns=["whether another layer rejects it"],
                supporting_evidence_ids=["ev_001"],
            )
            store.save_hypothesis(hyp)
            hyps = store.get_hypotheses_for_task("task_001")
            assert len(hyps) == 1
            assert "Empty string" in hyps[0].statement

    def test_patch_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            patch = PatchCandidate(
                id="patch_001",
                task_id="task_001",
                attempt_no=1,
                base_commit="abc123",
                diff="--- a/src/auth.py\n+++ b/src/auth.py\n",
                changed_files=["src/auth.py"],
                changed_symbols=["validate_password"],
            )
            store.save_patch(patch)
            patches = store.get_patches_for_task("task_001")
            assert len(patches) == 1
            assert patches[0].attempt_no == 1
            latest = store.get_latest_patch("task_001")
            assert latest is not None
            assert latest.id == "patch_001"

    def test_multiple_patches_append(self, tmp_path):
        with self._get_store(tmp_path) as store:
            for i in range(1, 4):
                patch = PatchCandidate(
                    id=f"patch_{i:03d}",
                    task_id="task_001",
                    attempt_no=i,
                    base_commit="abc123",
                    diff=f"diff_{i}",
                )
                store.save_patch(patch)
            patches = store.get_patches_for_task("task_001")
            assert len(patches) == 3
            assert patches[0].attempt_no == 1
            assert patches[2].attempt_no == 3
            latest = store.get_latest_patch("task_001")
            assert latest.attempt_no == 3

    def test_verification_report_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            report = VerificationReport(
                patch_id="patch_001",
                checks=[
                    CheckResult(
                        check_type="pytest",
                        command="pytest",
                        exit_code=0,
                        status=CheckStatus.pass_,
                    ),
                ],
                required_passed=True,
                final_status=FinalStatus.verified_candidate,
            )
            store.save_verification_report(report)
            reports = store.get_verification_reports("patch_001")
            assert len(reports) == 1
            assert reports[0].required_passed is True
            assert len(reports[0].checks) == 1

    def test_review_finding_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            finding = ReviewFinding(
                id="finding_001",
                patch_id="patch_001",
                severity=FindingSeverity.major,
                category="missing_edge_case",
                text="Whitespace-only password not handled",
            )
            store.save_finding(finding)
            findings = store.get_findings_for_patch("patch_001")
            assert len(findings) == 1
            assert findings[0].severity == FindingSeverity.major

    def test_evidence_contract_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            contract = EvidenceContract(
                change_id="change_001",
                requirement_ids=["req_001"],
                affected_symbols=["validate_password"],
                complete=True,
                final_status=FinalStatus.verified_candidate,
            )
            store.save_evidence_contract(contract)
            loaded = store.get_evidence_contract("change_001")
            assert loaded is not None
            assert loaded.complete is True
            assert loaded.final_status == FinalStatus.verified_candidate

    def test_provenance_edges(self, tmp_path):
        with self._get_store(tmp_path) as store:
            edge = ProvenanceEdge(
                from_type="requirement",
                from_id="req_001",
                relation="motivates",
                to_type="patch",
                to_id="patch_001",
            )
            store.save_provenance_edge(edge)
            outgoing = store.get_provenance_edges_from("requirement", "req_001")
            assert len(outgoing) == 1
            assert outgoing[0].relation == "motivates"
            incoming = store.get_provenance_edges_to("patch", "patch_001")
            assert len(incoming) == 1

    def test_run_events_append_only(self, tmp_path):
        with self._get_store(tmp_path) as store:
            for i in range(5):
                event = RunEvent(
                    id=f"evt_{i:03d}",
                    run_id="run_001",
                    task_id="task_001",
                    state=TaskState.intake if i == 0 else TaskState.retrieving,
                    event_type="state_change",
                    payload={"step": i},
                )
                store.save_event(event)
            events = store.get_events_for_run("run_001")
            assert len(events) == 5
            assert events[0].payload["step"] == 0
            assert events[4].payload["step"] == 4

    def test_final_decision_roundtrip(self, tmp_path):
        with self._get_store(tmp_path) as store:
            decision = FinalDecision(
                task_id="task_001",
                status=FinalStatus.needs_review,
                blockers=["unclear requirement"],
                summary="Cannot verify due to ambiguity",
                provenance_id="prov_001",
            )
            store.save_final_decision(decision)
            loaded = store.get_final_decision("task_001")
            assert loaded is not None
            assert loaded.status == FinalStatus.needs_review
            assert len(loaded.blockers) == 1

    def test_get_nonexistent(self, tmp_path):
        with self._get_store(tmp_path) as store:
            assert store.get_task("nonexistent") is None
            assert store.get_run("nonexistent") is None
            assert store.get_repository("nonexistent") is None
            assert store.get_latest_patch("nonexistent") is None
            assert store.get_final_decision("nonexistent") is None
