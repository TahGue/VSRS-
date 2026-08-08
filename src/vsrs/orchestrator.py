"""Orchestrator: end-to-end task execution pipeline (Section 7).

Coordinates the full VSRS pipeline:
  intake → retrieving → reasoning → patching → verifying → revising → reviewing → final

Each stage transitions the TaskRun state machine and delegates to the
appropriate component. The orchestrator is the single entry point for
running a task from start to finish.

In V1, the reasoner produces empty diffs (LLM integration is Phase 3+),
so the pipeline focuses on wiring all components together and producing
structured outputs at each stage.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from vsrs.core.ids import generate_run_id, generate_patch_id
from vsrs.core.logging import get_logger
from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    EvidenceContract,
    FinalDecision,
    FinalStatus,
    PatchCandidate,
    RepositorySnapshot,
    Task,
    TaskRun,
    TaskState,
    VerificationReport,
)
from vsrs.core.state import TaskStateMachine
from vsrs.core.config import SandboxConfig
from vsrs.reasoning.critic import CriticReport, ReviewService
from vsrs.reasoning.patcher import Patcher, ValidationResult
from vsrs.reasoning.reasoner import Reasoner
from vsrs.reasoning.protocol import ReasoningOutput
from vsrs.repair.categorizer import FailureCategorizer
from vsrs.repair.loop import RepairLoop, RepairResult
from vsrs.repo.intelligence import RepositoryIntelligence, RepositoryModel
from vsrs.repo.retrieval import RetrievalResult
from vsrs.verify.runner import VerificationConfig, VerificationRunner
from vsrs.verify.sandbox import Sandbox

logger = get_logger("orchestrator")


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator."""

    max_repair_attempts: int = 3
    run_lint: bool = True
    run_type_check: bool = True
    run_security: bool = True
    pytest_timeout: int = 120
    lint_timeout: int = 60
    mypy_timeout: int = 120
    bandit_timeout: int = 60
    cleanup_worktree: bool = True


@dataclass
class StageResult:
    """Result of a single pipeline stage."""

    stage: str
    state: TaskState
    success: bool
    duration_seconds: float = 0.0
    error: str = ""
    data: dict = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Complete result of running a task through the pipeline."""

    run: TaskRun
    stages: list[StageResult] = field(default_factory=list)
    reasoning_output: ReasoningOutput | None = None
    patch: PatchCandidate | None = None
    patch_validation: ValidationResult | None = None
    verification_report: VerificationReport | None = None
    repair_result: RepairResult | None = None
    critic_report: CriticReport | None = None
    final_decision: FinalDecision | None = None
    succeeded: bool = False

    @property
    def final_state(self) -> TaskState:
        return self.run.state

    @property
    def total_duration(self) -> float:
        return sum(s.duration_seconds for s in self.stages)


class Orchestrator:
    """End-to-end task execution orchestrator.

    Coordinates all VSRS components through the full pipeline:
    1. Intake — create task run, snapshot repository
    2. Retrieve — build repository intelligence, retrieve evidence
    3. Reason — run reasoning protocol on task + evidence
    4. Patch — validate and apply the proposed patch
    5. Verify — run verification checks in sandbox
    6. Repair — if verification fails, enter repair loop
    7. Review — run critic, produce final decision

    Each stage updates the TaskRun state machine and records results.
    """

    def __init__(
        self,
        config: OrchestratorConfig | None = None,
        sandbox: Sandbox | None = None,
        reasoner: Reasoner | None = None,
        patcher: Patcher | None = None,
        verification_runner: VerificationRunner | None = None,
        repair_loop: RepairLoop | None = None,
        review_service: ReviewService | None = None,
    ) -> None:
        self.config = config or OrchestratorConfig()
        self.sandbox = sandbox
        self.reasoner = reasoner or Reasoner()
        self.patcher = patcher or Patcher()
        self.verification_runner = verification_runner
        self.repair_loop = repair_loop
        self.review_service = review_service or ReviewService()

    def run(
        self,
        task: Task,
        repo_root: Path,
        repo_snapshot: RepositorySnapshot | None = None,
        run_id: str | None = None,
    ) -> PipelineResult:
        """Run a task through the full VSRS pipeline.

        Args:
            task: The task to execute.
            repo_root: Path to the repository root.
            repo_snapshot: Optional pre-created snapshot.
            run_id: Optional pre-generated run ID. If None, a new one is generated.

        Returns:
            PipelineResult with all stage results and final decision.
        """
        # Create run
        run = TaskRun(
            id=run_id or generate_run_id(),
            task_id=task.id,
            repo_snapshot_id=repo_snapshot.id if repo_snapshot else "",
            state=TaskState.intake,
            max_attempts=self.config.max_repair_attempts,
        )
        sm = TaskStateMachine(initial_state=TaskState.intake)
        result = PipelineResult(run=run)
        logger.info(f"Starting pipeline for task {task.id} (run {run.id})")

        # Stage 1: Intake
        stage = self._stage_intake(task, repo_root, repo_snapshot, run, sm)
        result.stages.append(stage)
        if not stage.success:
            run.state = TaskState.failed
            result.succeeded = False
            return result

        # Stage 2: Retrieve
        stage, repo_model, retrieval_result = self._stage_retrieve(
            task, repo_root, run, sm,
        )
        result.stages.append(stage)
        if not stage.success:
            run.state = TaskState.failed
            result.succeeded = False
            return result

        # Stage 3: Reason
        stage, reasoning_output = self._stage_reason(
            task, retrieval_result, run, sm,
        )
        result.stages.append(stage)
        result.reasoning_output = reasoning_output
        if not stage.success:
            run.state = TaskState.failed
            result.succeeded = False
            return result

        # Stage 4: Patch
        stage, patch, validation = self._stage_patch(
            task, reasoning_output, repo_root, run, sm,
        )
        result.stages.append(stage)
        result.patch = patch
        result.patch_validation = validation
        if not stage.success:
            run.state = TaskState.failed
            result.succeeded = False
            return result

        # Stage 5: Verify
        stage, verification_report, worktree = self._stage_verify(
            task, patch, repo_root, run, sm,
        )
        result.stages.append(stage)
        result.verification_report = verification_report
        if not stage.success and verification_report is None:
            run.state = TaskState.failed
            result.succeeded = False
            return result

        # Stage 6: Repair (if needed)
        if verification_report and not verification_report.required_passed:
            stage, repair_result = self._stage_repair(
                task, patch, verification_report, worktree or repo_root, run, sm,
            )
            result.stages.append(stage)
            result.repair_result = repair_result
            if repair_result and repair_result.succeeded:
                result.verification_report = repair_result.final_report
                result.patch = PatchCandidate(
                    id=repair_result.attempts[-1].patch_id,
                    task_id=task.id,
                    attempt_no=repair_result.attempts[-1].attempt_no,
                    base_commit=patch.base_commit,
                    diff="",
                    changed_files=patch.changed_files,
                )

        # Stage 7: Review
        stage, critic_report, decision = self._stage_review(
            task, result.patch or patch, result.verification_report or verification_report,
            reasoning_output, run, sm,
        )
        result.stages.append(stage)
        result.critic_report = critic_report
        result.final_decision = decision
        run.final_decision = decision

        # Set final state
        if decision and decision.status == FinalStatus.verified_candidate:
            run.state = TaskState.verified
            result.succeeded = True
        elif decision and decision.status == FinalStatus.rejected:
            run.state = TaskState.rejected
            result.succeeded = False
        else:
            run.state = TaskState.needs_review
            result.succeeded = False

        run.finished_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)

        # Cleanup worktree
        if self.config.cleanup_worktree and worktree and self.sandbox:
            worktree_obj = self.sandbox._worktrees.get(task.id)
            if worktree_obj:
                worktree_obj.cleanup()

        logger.info(
            f"Pipeline complete for task {task.id}: "
            f"state={run.state.value}, succeeded={result.succeeded}, "
            f"stages={len(result.stages)}, duration={result.total_duration:.2f}s"
        )

        return result

    def _stage_intake(
        self,
        task: Task,
        repo_root: Path,
        repo_snapshot: RepositorySnapshot | None,
        run: TaskRun,
        sm: TaskStateMachine,
    ) -> StageResult:
        """Stage 1: Intake — validate inputs, create snapshot."""
        start = time.time()
        logger.info(f"Stage 1: Intake for task {task.id}")

        if not repo_root.exists():
            return StageResult(
                stage="intake",
                state=TaskState.failed,
                success=False,
                duration_seconds=time.time() - start,
                error=f"Repository root does not exist: {repo_root}",
            )

        # Get commit hash
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
            )
            commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            commit_hash = "unknown"

        run.state = sm.transition(TaskState.retrieving)
        run.updated_at = datetime.now(timezone.utc)

        return StageResult(
            stage="intake",
            state=run.state,
            success=True,
            duration_seconds=time.time() - start,
            data={"commit_hash": commit_hash},
        )

    def _stage_retrieve(
        self,
        task: Task,
        repo_root: Path,
        run: TaskRun,
        sm: TaskStateMachine,
    ) -> tuple[StageResult, RepositoryModel | None, RetrievalResult | None]:
        """Stage 2: Retrieve — build repository intelligence, retrieve evidence."""
        start = time.time()
        logger.info(f"Stage 2: Retrieve for task {task.id}")

        try:
            intel = RepositoryIntelligence(repo_root)
            repo_model = intel.build()
            retriever = repo_model.build_retriever()
            retrieval_result = retriever.retrieve(task.instruction)
        except Exception as e:
            run.state = sm.transition(TaskState.failed)
            return (
                StageResult(
                    stage="retrieve",
                    state=TaskState.failed,
                    success=False,
                    duration_seconds=time.time() - start,
                    error=str(e),
                ),
                None,
                None,
            )

        run.state = sm.transition(TaskState.reasoning)

        return (
            StageResult(
                stage="retrieve",
                state=run.state,
                success=True,
                duration_seconds=time.time() - start,
                data={
                    "evidence_count": len(retrieval_result.evidence),
                    "files_indexed": repo_model.file_index.count,
                    "symbols_indexed": repo_model.symbol_index.count,
                },
            ),
            repo_model,
            retrieval_result,
        )

    def _stage_reason(
        self,
        task: Task,
        retrieval_result: RetrievalResult | None,
        run: TaskRun,
        sm: TaskStateMachine,
    ) -> tuple[StageResult, ReasoningOutput | None]:
        """Stage 3: Reason — run reasoning protocol."""
        start = time.time()
        logger.info(f"Stage 3: Reason for task {task.id}")

        if retrieval_result is None:
            run.state = sm.transition(TaskState.failed)
            return (
                StageResult(
                    stage="reason",
                    state=TaskState.failed,
                    success=False,
                    duration_seconds=time.time() - start,
                    error="No retrieval result provided",
                ),
                None,
            )

        try:
            reasoning_output = self.reasoner.reason(task, retrieval_result)
        except Exception as e:
            run.state = sm.transition(TaskState.failed)
            return (
                StageResult(
                    stage="reason",
                    state=TaskState.failed,
                    success=False,
                    duration_seconds=time.time() - start,
                    error=str(e),
                ),
                None,
            )

        run.state = sm.transition(TaskState.patching)

        return (
            StageResult(
                stage="reason",
                state=run.state,
                success=True,
                duration_seconds=time.time() - start,
                data={
                    "hypothesis": reasoning_output.hypothesis.statement[:100],
                    "predicted_effects": len(reasoning_output.predicted_effects.behavior_changes),
                },
            ),
            reasoning_output,
        )

    def _stage_patch(
        self,
        task: Task,
        reasoning_output: ReasoningOutput | None,
        repo_root: Path,
        run: TaskRun,
        sm: TaskStateMachine,
    ) -> tuple[StageResult, PatchCandidate | None, ValidationResult | None]:
        """Stage 4: Patch — validate and prepare patch candidate."""
        start = time.time()
        logger.info(f"Stage 4: Patch for task {task.id}")

        if reasoning_output is None or reasoning_output.patch_proposal is None:
            run.state = sm.transition(TaskState.failed)
            return (
                StageResult(
                    stage="patch",
                    state=TaskState.failed,
                    success=False,
                    duration_seconds=time.time() - start,
                    error="No patch proposal from reasoning",
                ),
                None,
                None,
            )

        proposal = reasoning_output.patch_proposal

        # Validate the diff
        validation = self.patcher.validate(proposal.diff, repo_root)

        # Create patch candidate
        patch = PatchCandidate(
            id=generate_patch_id(),
            task_id=task.id,
            attempt_no=1,
            base_commit=run.repo_snapshot_id or "unknown",
            diff=proposal.diff,
            changed_files=proposal.changed_files,
            changed_symbols=proposal.changed_symbols,
            assumptions=proposal.assumptions,
            predicted_effects=[str(e) for e in proposal.new_tests],
            falsification_checks=[],
        )

        run.state = sm.transition(TaskState.verifying)

        return (
            StageResult(
                stage="patch",
                state=run.state,
                success=True,
                duration_seconds=time.time() - start,
                data={
                    "patch_id": patch.id,
                    "changed_files": len(patch.changed_files),
                    "validation_valid": validation.valid,
                },
            ),
            patch,
            validation,
        )

    def _stage_verify(
        self,
        task: Task,
        patch: PatchCandidate,
        repo_root: Path,
        run: TaskRun,
        sm: TaskStateMachine,
    ) -> tuple[StageResult, VerificationReport | None, Path | None]:
        """Stage 5: Verify — run verification checks."""
        start = time.time()
        logger.info(f"Stage 5: Verify for task {task.id}")

        worktree_path = repo_root
        worktree = None

        # Create sandbox worktree if sandbox is available
        if self.sandbox:
            try:
                worktree = self.sandbox.create_worktree(
                    repo_root=repo_root,
                    task_id=task.id,
                )
                worktree_path = worktree.path
                run.worktree_path = str(worktree.path)
            except Exception as e:
                logger.warning(f"Failed to create worktree: {e}, using repo root directly")

        # Apply patch to worktree if non-empty
        if patch.diff.strip():
            success, error = self.patcher.apply(patch.diff, worktree_path)
            if not success:
                logger.warning(f"Patch application failed: {error}")

        # Build verification runner if not provided
        runner = self.verification_runner
        if runner is None:
            runner = VerificationRunner(
                config=VerificationConfig(
                    run_lint=self.config.run_lint,
                    run_type_check=self.config.run_type_check,
                    run_security=self.config.run_security,
                    pytest_timeout=self.config.pytest_timeout,
                    lint_timeout=self.config.lint_timeout,
                    mypy_timeout=self.config.mypy_timeout,
                    bandit_timeout=self.config.bandit_timeout,
                ),
            )

        try:
            report = runner.verify(
                patch=patch,
                task=task,
                worktree_path=worktree_path,
                changed_files=patch.changed_files,
            )
        except Exception as e:
            run.state = sm.transition(TaskState.failed)
            return (
                StageResult(
                    stage="verify",
                    state=TaskState.failed,
                    success=False,
                    duration_seconds=time.time() - start,
                    error=str(e),
                ),
                None,
                worktree_path,
            )

        # Transition based on result
        if report.required_passed:
            run.state = sm.transition(TaskState.reviewing)
        else:
            run.state = sm.transition(TaskState.revising)

        return (
            StageResult(
                stage="verify",
                state=run.state,
                success=True,
                duration_seconds=time.time() - start,
                data={
                    "checks": len(report.checks),
                    "required_passed": report.required_passed,
                    "blockers": len(report.blockers),
                },
            ),
            report,
            worktree_path,
        )

    def _stage_repair(
        self,
        task: Task,
        patch: PatchCandidate,
        report: VerificationReport,
        worktree_path: Path,
        run: TaskRun,
        sm: TaskStateMachine,
    ) -> tuple[StageResult, RepairResult | None]:
        """Stage 6: Repair — enter repair loop if verification failed."""
        start = time.time()
        logger.info(f"Stage 6: Repair for task {task.id}")

        # Build repair loop if not provided
        loop = self.repair_loop
        if loop is None:
            runner = self.verification_runner
            if runner is None:
                runner = VerificationRunner(
                    config=VerificationConfig(
                        run_lint=self.config.run_lint,
                        run_type_check=self.config.run_type_check,
                        run_security=self.config.run_security,
                    ),
                )
            loop = RepairLoop(
                verification_runner=runner,
                max_attempts=self.config.max_repair_attempts,
            )

        try:
            repair_result = loop.run(
                task=task,
                initial_patch=patch,
                initial_report=report,
                worktree_path=worktree_path,
            )
        except Exception as e:
            run.state = sm.transition(TaskState.failed)
            return (
                StageResult(
                    stage="repair",
                    state=TaskState.failed,
                    success=False,
                    duration_seconds=time.time() - start,
                    error=str(e),
                ),
                None,
            )

        # Transition from revising through the full cycle to reviewing
        if sm.state == TaskState.revising:
            run.state = sm.transition(TaskState.reasoning)
            run.state = sm.transition(TaskState.patching)
            run.state = sm.transition(TaskState.verifying)
            run.state = sm.transition(TaskState.reviewing)
        elif sm.state == TaskState.reasoning:
            run.state = sm.transition(TaskState.patching)
            run.state = sm.transition(TaskState.verifying)
            run.state = sm.transition(TaskState.reviewing)

        return (
            StageResult(
                stage="repair",
                state=run.state,
                success=True,
                duration_seconds=time.time() - start,
                data={
                    "attempts": repair_result.total_attempts,
                    "succeeded": repair_result.succeeded,
                },
            ),
            repair_result,
        )

    def _stage_review(
        self,
        task: Task,
        patch: PatchCandidate,
        report: VerificationReport | None,
        reasoning_output: ReasoningOutput | None,
        run: TaskRun,
        sm: TaskStateMachine,
    ) -> tuple[StageResult, CriticReport | None, FinalDecision | None]:
        """Stage 7: Review — run critic and produce final decision."""
        start = time.time()
        logger.info(f"Stage 7: Review for task {task.id}")

        if report is None:
            report = VerificationReport(
                patch_id=patch.id,
                checks=[],
                required_passed=False,
                blockers=["No verification report available"],
                final_status=FinalStatus.needs_review,
            )

        # Build evidence contract if reasoning output available
        contract = None
        if reasoning_output:
            contract = EvidenceContract(
                change_id=patch.id,
                assumptions=patch.assumptions,
                falsification_checks=patch.falsification_checks,
            )

        # Get evidence locators from reasoning
        evidence_locators = []
        if reasoning_output and reasoning_output.evidence_summary:
            evidence_locators = reasoning_output.evidence_summary.evidence_locators

        try:
            critic_report, decision = self.review_service.review(
                patch=patch,
                task=task,
                report=report,
                contract=contract,
                evidence_locators=evidence_locators,
            )
        except Exception as e:
            run.state = sm.transition(TaskState.failed)
            return (
                StageResult(
                    stage="review",
                    state=TaskState.failed,
                    success=False,
                    duration_seconds=time.time() - start,
                    error=str(e),
                ),
                None,
                None,
            )

        return (
            StageResult(
                stage="review",
                state=run.state,
                success=True,
                duration_seconds=time.time() - start,
                data={
                    "findings": len(critic_report.findings),
                    "blockers": critic_report.blocker_count,
                    "decision": decision.status.value,
                },
            ),
            critic_report,
            decision,
        )
