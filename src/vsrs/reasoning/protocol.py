"""Reasoning protocol schemas for structured LLM output (Section 7.1).

Defines the Pydantic models that the reasoning model must produce at each
stage. These schemas enforce the reasoning contract: every important claim
is grounded in evidence or tested against executable evidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- Stage 1: Task Parsing ---


class ParsedTask(BaseModel):
    """Output of Stage 1: Parse task.

    Extracts expected behavior, constraints, acceptance criteria, and risk
    from a natural language task description.
    """

    expected_behavior: str = Field(description="What the code should do after the change")
    constraints: list[str] = Field(default_factory=list, description="Technical or domain constraints")
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Observable conditions that must be true"
    )
    risk_level: str = Field(default="low", description="Assessed risk: low, medium, high")
    risk_factors: list[str] = Field(default_factory=list, description="Factors contributing to risk")
    task_type: str = Field(default="bugfix", description="bugfix, feature, refactor, test, security, migration")
    affected_areas: list[str] = Field(
        default_factory=list, description="Likely affected modules/files/symbols"
    )


# --- Stage 2: Evidence Gathering ---


class EvidenceSummary(BaseModel):
    """Output of Stage 2: Gather evidence.

    Summarizes the evidence retrieved from the repository that is relevant
    to the task. Each evidence item must have a locator.
    """

    relevant_symbols: list[str] = Field(
        default_factory=list, description="Qualified names of relevant symbols"
    )
    relevant_files: list[str] = Field(
        default_factory=list, description="File paths relevant to the task"
    )
    relevant_tests: list[str] = Field(
        default_factory=list, description="Test names relevant to the task"
    )
    relevant_configs: list[str] = Field(
        default_factory=list, description="Config files/settings relevant to the task"
    )
    key_observations: list[str] = Field(
        default_factory=list, description="Important facts observed in the evidence"
    )
    evidence_locators: list[str] = Field(
        default_factory=list, description="Locators (file:line) for all evidence shown"
    )


# --- Stage 3: Hypothesis ---


class ReasoningHypothesis(BaseModel):
    """Output of Stage 3: State hypothesis.

    Describes the likely cause of a bug or the implementation strategy for
    a feature. Lists unknowns that need to be resolved.
    """

    statement: str = Field(description="The hypothesis about cause or required behavior")
    supporting_evidence: list[str] = Field(
        default_factory=list, description="Evidence locators supporting this hypothesis"
    )
    unknowns: list[str] = Field(
        default_factory=list, description="Unknowns that remain to be resolved"
    )
    confidence: str = Field(
        default="unknown",
        description="observed_true, inferred_supported, unknown, conflicted",
    )


# --- Stage 4: Predict Effects ---


class PredictedEffects(BaseModel):
    """Output of Stage 4: Predict effects.

    States what files/symbols should change and what behavior must remain
    unchanged.
    """

    files_to_change: list[str] = Field(default_factory=list, description="Files that will be modified")
    symbols_to_change: list[str] = Field(
        default_factory=list, description="Symbols that will be modified"
    )
    new_symbols: list[str] = Field(
        default_factory=list, description="New symbols to be introduced"
    )
    behavior_changes: list[str] = Field(
        default_factory=list, description="Expected behavior changes"
    )
    behavior_preserved: list[str] = Field(
        default_factory=list, description="Behavior that must remain unchanged"
    )
    side_effects: list[str] = Field(
        default_factory=list, description="Potential side effects to watch for"
    )


# --- Stage 5: Falsification Plan ---


class FalsificationPlan(BaseModel):
    """Output of Stage 5: Define falsification.

    States which tests or checks would prove the hypothesis or patch wrong.
    This is the core of P4 (Falsifiability).
    """

    checks: list[str] = Field(
        default_factory=list, description="Tests/checks that would falsify the patch"
    )
    new_tests_needed: list[str] = Field(
        default_factory=list, description="New tests that need to be written"
    )
    existing_tests_to_run: list[str] = Field(
        default_factory=list, description="Existing tests that must still pass"
    )
    edge_cases: list[str] = Field(
        default_factory=list, description="Edge cases to consider"
    )


# --- Stage 6: Patch Proposal ---


class PatchProposal(BaseModel):
    """Output of Stage 6: Produce minimal patch.

    The actual patch as a unified diff, with structured metadata about
    what changed and why.
    """

    diff: str = Field(description="Unified diff of the proposed change")
    changed_files: list[str] = Field(default_factory=list, description="Files changed in the diff")
    changed_symbols: list[str] = Field(default_factory=list, description="Symbols modified")
    new_files: list[str] = Field(default_factory=list, description="New files created")
    new_tests: list[str] = Field(default_factory=list, description="New test functions added")
    rationale: str = Field(description="Why this patch addresses the task")
    assumptions: list[str] = Field(
        default_factory=list, description="Assumptions made in the patch"
    )


# --- Full Reasoning Output ---


class ReasoningOutput(BaseModel):
    """Complete structured output from the reasoning model.

    Combines all stages into a single validated output. This is what the
    model must produce — not free-form chain-of-thought.
    """

    parsed_task: ParsedTask
    evidence_summary: EvidenceSummary
    hypothesis: ReasoningHypothesis
    predicted_effects: PredictedEffects
    falsification_plan: FalsificationPlan
    patch_proposal: PatchProposal
    evidence_contract_refs: list[str] = Field(
        default_factory=list, description="Evidence item IDs referenced in this output"
    )
    timestamp: datetime = Field(default_factory=_utcnow)


# --- Repair Input (for Phase 5) ---


class FailureSummary(BaseModel):
    """Structured failure summary fed back to the reasoner in repair.

    Instead of raw logs, the reasoner receives categorized failures with
    actionable information.
    """

    check_type: str
    status: str  # pass, fail, error, skip
    error_category: str = Field(
        description="syntax, test_failure, type_error, import_error, lint, security, config, other"
    )
    error_message: str = ""
    failed_test_names: list[str] = Field(default_factory=list)
    relevant_file: str = ""
    relevant_line: int | None = None
    suggested_fix: str = ""


class RepairInput(BaseModel):
    """Input to the reasoner for a repair attempt.

    Contains the prior patch, structured failure summaries, and prior
    evidence — not an uncontrolled transcript.
    """

    task_instruction: str
    prior_patch_diff: str
    prior_attempt_no: int
    failures: list[FailureSummary] = Field(default_factory=list)
    prior_evidence_locators: list[str] = Field(default_factory=list)
    prior_assumptions: list[str] = Field(default_factory=list)
    remaining_attempts: int = 1


class RepairOutput(BaseModel):
    """Output from the reasoner for a repair attempt.

    Same structure as a patch proposal but with repair-specific metadata.
    """

    patch_proposal: PatchProposal
    failure_analysis: str = Field(description="Why the prior patch failed")
    revised_assumptions: list[str] = Field(default_factory=list)
    new_evidence_needed: list[str] = Field(
        default_factory=list, description="New evidence to retrieve"
    )
