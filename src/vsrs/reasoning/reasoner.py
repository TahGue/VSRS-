"""Primary reasoning model: structured hypothesis, predicted effects, patch (Section 7.1).

Orchestrates the reasoning protocol stages 2-6. Takes a parsed task and
retrieved evidence, produces a structured ReasoningOutput with hypothesis,
predicted effects, falsification plan, and patch proposal.

In V1, this is a deterministic rule-based reasoner. In later phases, this
will be replaced by an LLM call with structured output validation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from vsrs.core.ids import generate_hypothesis_id, generate_patch_id
from vsrs.core.logging import get_logger
from vsrs.core.schemas import (
    EvidenceItem,
    EvidenceState,
    EvidenceType,
    Hypothesis,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskType,
)
from vsrs.reasoning.protocol import (
    EvidenceSummary,
    FalsificationPlan,
    PatchProposal,
    PredictedEffects,
    ParsedTask,
    ReasoningHypothesis,
    ReasoningOutput,
)
from vsrs.reasoning.task_parser import TaskParser
from vsrs.repo.retrieval import RetrievalResult

logger = get_logger("reasoning.reasoner")


class Reasoner:
    """Primary reasoning model implementing stages 2-6 of the protocol.

    In V1, this is a deterministic reasoner that:
    - Summarizes evidence from the retrieval result
    - Forms a hypothesis based on evidence patterns
    - Predicts effects based on the task and evidence
    - Creates a falsification plan from acceptance criteria
    - Produces a patch proposal (empty diff in V1 — actual patch generation
      requires LLM integration in Phase 3+)

    In later phases, this will call an LLM with structured output validation.
    """

    def __init__(self, task_parser: TaskParser | None = None) -> None:
        self.task_parser = task_parser or TaskParser()

    def reason(
        self,
        task: Task,
        retrieval_result: RetrievalResult,
        parsed_task: ParsedTask | None = None,
    ) -> ReasoningOutput:
        """Run the full reasoning pipeline on a task.

        Args:
            task: The task to reason about.
            retrieval_result: Evidence retrieved from the repository.
            parsed_task: Pre-parsed task (if None, will parse from task instruction).

        Returns:
            ReasoningOutput with all stages completed.
        """
        logger.info(f"Reasoning on task {task.id}: {task.instruction[:80]}")

        # Stage 1: Parse task (if not already done)
        if parsed_task is None:
            parsed_task = self.task_parser.parse(
                instruction=task.instruction,
                acceptance_criteria=task.acceptance_criteria,
                task_type=task.type,
                risk_level=task.risk_level,
            )

        # Stage 2: Summarize evidence
        evidence_summary = self._summarize_evidence(retrieval_result)

        # Stage 3: Form hypothesis
        hypothesis = self._form_hypothesis(task, parsed_task, evidence_summary)

        # Stage 4: Predict effects
        predicted_effects = self._predict_effects(task, parsed_task, evidence_summary)

        # Stage 5: Falsification plan
        falsification_plan = self._create_falsification_plan(
            task, parsed_task, predicted_effects,
        )

        # Stage 6: Patch proposal
        patch_proposal = self._propose_patch(
            task, parsed_task, evidence_summary, predicted_effects,
        )

        # Collect evidence contract refs
        evidence_refs = [
            ev.metadata.get("name", ev.locator)
            for ev in retrieval_result.evidence
        ]

        return ReasoningOutput(
            parsed_task=parsed_task,
            evidence_summary=evidence_summary,
            hypothesis=hypothesis,
            predicted_effects=predicted_effects,
            falsification_plan=falsification_plan,
            patch_proposal=patch_proposal,
            evidence_contract_refs=evidence_refs,
        )

    def _summarize_evidence(self, result: RetrievalResult) -> EvidenceSummary:
        """Stage 2: Summarize retrieved evidence."""
        symbols: list[str] = []
        files: list[str] = []
        tests: list[str] = []
        configs: list[str] = []
        observations: list[str] = []
        locators: list[str] = []

        for ev in result.evidence:
            locators.append(ev.locator)

            if ev.kind == "symbol":
                name = ev.metadata.get("name", "")
                qual = ev.metadata.get("qualified_name", name)
                if qual:
                    symbols.append(qual)
                # Extract observation from signature
                sig = ev.metadata.get("signature", "")
                if sig:
                    observations.append(f"{ev.locator}: {sig}")

            elif ev.kind == "file":
                files.append(ev.locator)

            elif ev.kind == "test":
                name = ev.metadata.get("name", "")
                if name:
                    tests.append(name)

            elif ev.kind == "config":
                configs.append(ev.locator)

            elif ev.kind == "import":
                files.append(ev.locator)

        return EvidenceSummary(
            relevant_symbols=list(dict.fromkeys(symbols)),
            relevant_files=list(dict.fromkeys(files)),
            relevant_tests=list(dict.fromkeys(tests)),
            relevant_configs=list(dict.fromkeys(configs)),
            key_observations=observations[:10],
            evidence_locators=locators,
        )

    def _form_hypothesis(
        self,
        task: Task,
        parsed: ParsedTask,
        evidence: EvidenceSummary,
    ) -> ReasoningHypothesis:
        """Stage 3: Form a hypothesis about the cause or required behavior."""
        # Build hypothesis statement based on task type and evidence
        if parsed.task_type == "bugfix":
            statement = self._bugfix_hypothesis(task, parsed, evidence)
        elif parsed.task_type == "feature":
            statement = self._feature_hypothesis(task, parsed, evidence)
        elif parsed.task_type == "refactor":
            statement = self._refactor_hypothesis(task, parsed, evidence)
        elif parsed.task_type == "security":
            statement = self._security_hypothesis(task, parsed, evidence)
        else:
            statement = f"Task requires modification to: {', '.join(parsed.affected_areas[:3])}"

        # Supporting evidence from locators
        supporting = evidence.evidence_locators[:5]

        # Unknowns from the evidence
        unknowns = self._identify_unknowns(parsed, evidence)

        # Confidence based on evidence availability
        if len(evidence.relevant_symbols) >= 2 and len(evidence.relevant_tests) >= 1:
            confidence = "inferred_supported"
        elif len(evidence.relevant_symbols) >= 1:
            confidence = "inferred_supported"
        else:
            confidence = "unknown"

        return ReasoningHypothesis(
            statement=statement,
            supporting_evidence=supporting,
            unknowns=unknowns,
            confidence=confidence,
        )

    def _bugfix_hypothesis(
        self, task: Task, parsed: ParsedTask, evidence: EvidenceSummary,
    ) -> str:
        parts: list[str] = []
        if parsed.affected_areas:
            parts.append(f"The bug is likely in {parsed.affected_areas[0]}")
        if evidence.relevant_symbols:
            parts.append(f"related to {', '.join(evidence.relevant_symbols[:2])}")
        if parsed.expected_behavior:
            parts.append(f"The expected behavior is: {parsed.expected_behavior}")
        return ". ".join(parts) if parts else task.instruction

    def _feature_hypothesis(
        self, task: Task, parsed: ParsedTask, evidence: EvidenceSummary,
    ) -> str:
        parts: list[str] = []
        parts.append(f"New functionality needed: {parsed.expected_behavior}")
        if evidence.relevant_files:
            parts.append(f"to be added in {', '.join(evidence.relevant_files[:2])}")
        if parsed.affected_areas:
            parts.append(f"integrating with {', '.join(parsed.affected_areas[:2])}")
        return ". ".join(parts)

    def _refactor_hypothesis(
        self, task: Task, parsed: ParsedTask, evidence: EvidenceSummary,
    ) -> str:
        parts: list[str] = []
        parts.append(f"Refactoring needed: {parsed.expected_behavior}")
        if evidence.relevant_symbols:
            parts.append(f"affecting {', '.join(evidence.relevant_symbols[:3])}")
        parts.append("while preserving existing behavior")
        return ". ".join(parts)

    def _security_hypothesis(
        self, task: Task, parsed: ParsedTask, evidence: EvidenceSummary,
    ) -> str:
        parts: list[str] = []
        parts.append(f"Security issue: {parsed.expected_behavior}")
        if parsed.risk_factors:
            parts.append(f"Risk factors: {', '.join(parsed.risk_factors[:3])}")
        parts.append("requires careful validation and testing")
        return ". ".join(parts)

    def _identify_unknowns(
        self, parsed: ParsedTask, evidence: EvidenceSummary,
    ) -> list[str]:
        """Identify unknowns that need to be resolved."""
        unknowns: list[str] = []

        if not evidence.relevant_symbols:
            unknowns.append("No relevant symbols found — need to identify the exact code to modify")
        if not evidence.relevant_tests:
            unknowns.append("No existing tests found — need to write new tests")
        if not evidence.relevant_files:
            unknowns.append("No relevant files identified — need to locate the code")
        if len(parsed.affected_areas) > 3:
            unknowns.append("Multiple affected areas — need to determine scope")

        return unknowns

    def _predict_effects(
        self,
        task: Task,
        parsed: ParsedTask,
        evidence: EvidenceSummary,
    ) -> PredictedEffects:
        """Stage 4: Predict effects of the change."""
        files_to_change = evidence.relevant_files[:5]
        symbols_to_change = evidence.relevant_symbols[:5]

        behavior_changes = parsed.acceptance_criteria[:5]
        behavior_preserved = [
            "All existing tests must continue to pass",
            "No new syntax errors introduced",
        ]
        if parsed.task_type == "refactor":
            behavior_preserved.append("Public API remains unchanged")
        if parsed.task_type == "security":
            behavior_preserved.append("No new security vulnerabilities introduced")

        side_effects: list[str] = []
        if parsed.risk_level in ("medium", "high"):
            side_effects.append("Changes may affect dependent modules")
        if "dependency" in " ".join(parsed.constraints).lower():
            side_effects.append("Dependency changes may require lockfile update")

        return PredictedEffects(
            files_to_change=files_to_change,
            symbols_to_change=symbols_to_change,
            new_symbols=[],
            behavior_changes=behavior_changes,
            behavior_preserved=behavior_preserved,
            side_effects=side_effects,
        )

    def _create_falsification_plan(
        self,
        task: Task,
        parsed: ParsedTask,
        effects: PredictedEffects,
    ) -> FalsificationPlan:
        """Stage 5: Create a falsification plan."""
        checks: list[str] = []
        new_tests: list[str] = []
        existing_tests: list[str] = []
        edge_cases: list[str] = []

        # Checks from acceptance criteria
        for criterion in parsed.acceptance_criteria:
            checks.append(f"Verify: {criterion}")

        # Checks from predicted behavior changes
        for change in effects.behavior_changes:
            checks.append(f"Test that: {change}")

        # New tests needed
        if parsed.task_type == "bugfix":
            new_tests.append("Test that reproduces the original bug")
            new_tests.append("Test that verifies the fix works")
        elif parsed.task_type == "feature":
            new_tests.append("Test for the new functionality")
            new_tests.append("Test for edge cases of the new feature")
        elif parsed.task_type == "security":
            new_tests.append("Test that the vulnerability is fixed")
            new_tests.append("Test that the fix doesn't introduce new issues")

        # Existing tests to run
        existing_tests.append("Run full test suite to check for regressions")

        # Edge cases
        edge_cases.extend([
            "Empty input",
            "None/null input",
            "Boundary values",
        ])
        if parsed.task_type == "security":
            edge_cases.extend(["Malicious input", "Injection attempts"])
        if parsed.risk_level == "high":
            edge_cases.append("Concurrent access scenarios")

        return FalsificationPlan(
            checks=checks,
            new_tests_needed=new_tests,
            existing_tests_to_run=existing_tests,
            edge_cases=edge_cases,
        )

    def _propose_patch(
        self,
        task: Task,
        parsed: ParsedTask,
        evidence: EvidenceSummary,
        effects: PredictedEffects,
    ) -> PatchProposal:
        """Stage 6: Propose a minimal patch.

        In V1, this produces an empty diff with structured metadata.
        Actual patch generation requires LLM integration.
        """
        return PatchProposal(
            diff="",  # V1: empty — LLM generates the actual diff
            changed_files=effects.files_to_change,
            changed_symbols=effects.symbols_to_change,
            new_files=[],
            new_tests=[],
            rationale=f"Patch for {parsed.task_type} task: {parsed.expected_behavior[:100]}",
            assumptions=[
                "The identified files and symbols are the correct targets",
                "Existing tests cover the current behavior adequately",
            ],
        )

    def to_hypothesis_model(
        self, task_id: str, hypothesis: ReasoningHypothesis,
    ) -> Hypothesis:
        """Convert a protocol ReasoningHypothesis to a core Hypothesis model."""
        return Hypothesis(
            id=generate_hypothesis_id(),
            task_id=task_id,
            statement=hypothesis.statement,
            unknowns=hypothesis.unknowns,
            supporting_evidence_ids=hypothesis.supporting_evidence,
        )

    def to_patch_model(
        self, task_id: str, proposal: PatchProposal, attempt_no: int,
        base_commit: str = "",
    ) -> PatchCandidate:
        """Convert a protocol PatchProposal to a core PatchCandidate model."""
        return PatchCandidate(
            id=generate_patch_id(),
            task_id=task_id,
            attempt_no=attempt_no,
            base_commit=base_commit,
            diff=proposal.diff,
            changed_files=proposal.changed_files,
            changed_symbols=proposal.changed_symbols,
            assumptions=proposal.assumptions,
            predicted_effects=[],  # filled from PredictedEffects in orchestrator
            falsification_checks=[],  # filled from FalsificationPlan in orchestrator
        )
