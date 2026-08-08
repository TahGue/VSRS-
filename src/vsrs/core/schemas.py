"""Core Pydantic schemas for VSRS.

Implements the data models from Appendix A of the VSRS plan:
- Task
- EvidenceItem
- PatchCandidate
- VerificationReport
- Plus supporting types: Hypothesis, ReviewFinding, EvidenceContract, etc.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Enums ---


class TaskType(str, Enum):
    """Type of software task."""

    bugfix = "bugfix"
    feature = "feature"
    refactor = "refactor"
    test = "test"
    security = "security"
    migration = "migration"


class RiskLevel(str, Enum):
    """Risk level for a task."""

    low = "low"
    medium = "medium"
    high = "high"


class EvidenceType(str, Enum):
    """Type of evidence (Section 5.3)."""

    executable = "executable"
    structural = "structural"
    config = "config"
    historical = "historical"
    documentation = "documentation"
    inference = "inference"


class EvidenceState(str, Enum):
    """Evidence state instead of raw confidence (Section 5.4)."""

    observed_true = "observed_true"
    observed_false = "observed_false"
    inferred_supported = "inferred_supported"
    unknown = "unknown"
    conflicted = "conflicted"
    not_applicable = "not_applicable"


class TaskState(str, Enum):
    """State machine states for a task run."""

    intake = "intake"
    retrieving = "retrieving"
    reasoning = "reasoning"
    patching = "patching"
    verifying = "verifying"
    revising = "revising"
    reviewing = "reviewing"
    verified = "verified"
    rejected = "rejected"
    needs_review = "needs_review"
    escalated = "escalated"
    failed = "failed"


class CheckStatus(str, Enum):
    """Status of a single verification check."""

    pass_ = "pass"
    fail = "fail"
    skip = "skip"
    error = "error"
    waived = "waived"


class FinalStatus(str, Enum):
    """Final decision status for a patch candidate."""

    verified_candidate = "verified_candidate"
    rejected = "rejected"
    needs_review = "needs_review"


class FindingSeverity(str, Enum):
    """Severity levels for critic findings (Section 9.2)."""

    blocker = "blocker"
    major = "major"
    minor = "minor"
    question = "question"
    suggestion = "suggestion"


class GatePolicy(str, Enum):
    """Policy class for a verification gate."""

    mandatory = "mandatory"
    mandatory_when_applicable = "mandatory_when_applicable"
    policy_dependent = "policy_dependent"
    risk_dependent = "risk_dependent"
    optional = "optional"


# --- Core Schemas (Appendix A) ---


class Task(BaseModel):
    """A software task / bug / feature request (Appendix A.1)."""

    id: str
    repo_snapshot_id: str
    type: TaskType
    instruction: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.low
    required_gates: list[str] = Field(default_factory=list)
    state: TaskState = TaskState.intake
    created_at: datetime = Field(default_factory=_utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceItem(BaseModel):
    """A single piece of evidence (Appendix A.2)."""

    id: str
    type: EvidenceType
    source: str
    locator: str
    content_hash: str = ""
    state: EvidenceState = EvidenceState.unknown
    timestamp: datetime = Field(default_factory=_utcnow)
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatchCandidate(BaseModel):
    """A proposed patch (Appendix A.3)."""

    id: str
    task_id: str
    attempt_no: int = 1
    base_commit: str
    diff: str
    changed_files: list[str] = Field(default_factory=list)
    changed_symbols: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    predicted_effects: list[str] = Field(default_factory=list)
    falsification_checks: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class CheckResult(BaseModel):
    """Result of a single verification check."""

    check_type: str
    command: str
    exit_code: int | None = None
    status: CheckStatus = CheckStatus.skip
    output_ref: str = ""
    duration_seconds: float = 0.0
    timestamp: datetime = Field(default_factory=_utcnow)
    error_message: str = ""


class VerificationReport(BaseModel):
    """Verification report for a patch candidate (Appendix A.4)."""

    patch_id: str
    checks: list[CheckResult] = Field(default_factory=list)
    required_passed: bool = False
    blockers: list[str] = Field(default_factory=list)
    unresolved_unknowns: list[str] = Field(default_factory=list)
    final_status: FinalStatus = FinalStatus.needs_review
    timestamp: datetime = Field(default_factory=_utcnow)


# --- Supporting Schemas ---


class Hypothesis(BaseModel):
    """A hypothesis about cause or required behavior."""

    id: str
    task_id: str
    statement: str
    unknowns: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)


class EvidenceContract(BaseModel):
    """Required evidence contract for every patch candidate (Section 5.1)."""

    change_id: str
    requirement_ids: list[str] = Field(default_factory=list)
    affected_symbols: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    expected_behavior_changes: list[str] = Field(default_factory=list)
    falsification_checks: list[str] = Field(default_factory=list)
    verification_results: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    final_status: FinalStatus = FinalStatus.needs_review
    complete: bool = False


class ReviewFinding(BaseModel):
    """A critic finding (Section 9.2)."""

    id: str
    patch_id: str
    severity: FindingSeverity
    category: str
    evidence_refs: list[str] = Field(default_factory=list)
    text: str
    created_at: datetime = Field(default_factory=_utcnow)


class ProvenanceEdge(BaseModel):
    """An edge in the provenance graph."""

    from_type: str
    from_id: str
    relation: str
    to_type: str
    to_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinalDecision(BaseModel):
    """Final decision for a task run."""

    task_id: str
    status: FinalStatus
    blockers: list[str] = Field(default_factory=list)
    waived_gates: list[str] = Field(default_factory=list)
    summary: str = ""
    provenance_id: str = ""
    decided_at: datetime = Field(default_factory=_utcnow)


class RunEvent(BaseModel):
    """An append-only event in a task run's lifecycle."""

    id: str
    run_id: str
    task_id: str
    state: TaskState
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)


class RepositorySnapshot(BaseModel):
    """A snapshot of a repository at a point in time."""

    id: str
    root: str
    commit_hash: str
    language_profile: str = "python"
    config_hash: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class TaskRun(BaseModel):
    """A full task run, linking task, repository, and all attempts."""

    id: str
    task_id: str
    repo_snapshot_id: str
    state: TaskState = TaskState.intake
    attempt_no: int = 0
    max_attempts: int = 3
    started_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    worktree_path: str = ""
    final_decision: FinalDecision | None = None
