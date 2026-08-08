"""Pydantic request/response models for the VSRS API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RunRequest(BaseModel):
    """Request to start a new task run."""

    repo_path: str = Field(..., description="Path to the repository")
    task_instruction: str = Field(..., description="Task instruction text")
    task_type: str = Field(default="bugfix", description="Task type: bugfix, feature, refactor, test, security, migration")
    risk: str = Field(default="low", description="Risk level: low, medium, high")
    acceptance_criteria: list[str] = Field(default_factory=list, description="Acceptance criteria")


class RunResponse(BaseModel):
    """Response for a run."""

    run_id: str
    task_id: str
    state: str
    started_at: str
    attempt_no: int
    max_attempts: int


class RunListResponse(BaseModel):
    """Paginated list of runs."""

    runs: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    offset: int = 0
    limit: int = 100


class TaskResponse(BaseModel):
    """Response for a task."""

    id: str
    type: str
    risk_level: str
    instruction: str
    acceptance_criteria: list[str]
    required_gates: list[str]


class EvidenceResponse(BaseModel):
    """Response for evidence items."""

    items: list[dict[str, Any]] = Field(default_factory=list)


class PatchResponse(BaseModel):
    """Response for a patch."""

    id: str
    attempt_no: int
    base_commit: str
    diff: str
    changed_files: list[str]
    assumptions: list[str]


class VerificationResponse(BaseModel):
    """Response for verification report."""

    checks: list[dict[str, Any]] = Field(default_factory=list)
    required_passed: bool = False
    final_status: str = ""
    blockers: list[str] = Field(default_factory=list)
    unresolved_unknowns: list[str] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    """Response for critic review."""

    findings: list[dict[str, Any]] = Field(default_factory=list)
    final_decision: dict[str, Any] | None = None


class ProvenanceResponse(BaseModel):
    """Response for provenance graph."""

    edges: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] | None = None


class ReportResponse(BaseModel):
    """Response for report generation."""

    report: str
    format: str = "markdown"


class ExportResponse(BaseModel):
    """Response for trajectory export."""

    trajectory: dict[str, Any]


class ConfigResponse(BaseModel):
    """Response for configuration."""

    config: dict[str, Any]


class ConfigValidationResponse(BaseModel):
    """Response for config validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)


class BenchmarkListResponse(BaseModel):
    """Response for benchmark list."""

    tasks: list[dict[str, Any]] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    """Response for run history."""

    task_id: str
    runs: list[dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    error_code: str = "error"
