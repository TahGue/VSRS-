"""Repair loop: orchestrates repair attempts with attempt tracking (Section 7.3).

Coordinates the repair cycle:
1. Verification fails → categorize failures
2. Build RepairInput from prior patch + failures
3. Call RepairReasoner to produce RepairOutput
4. Apply new patch → verify again
5. Repeat until pass or max attempts reached

Enforces max attempt limits and tracks all attempts for provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from vsrs.core.ids import generate_patch_id, generate_run_id
from vsrs.core.logging import get_logger
from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    FinalStatus,
    PatchCandidate,
    Task,
    TaskRun,
    TaskState,
    VerificationReport,
)
from vsrs.reasoning.protocol import (
    FailureSummary,
    PatchProposal,
    RepairInput,
    RepairOutput,
)
from vsrs.repair.categorizer import FailureCategorizer
from vsrs.repair.repair_reasoner import RepairReasoner
from vsrs.verify.runner import VerificationRunner

logger = get_logger("repair.loop")


@dataclass
class AttemptRecord:
    """Record of a single repair attempt."""

    attempt_no: int
    patch_id: str
    verification_report: VerificationReport
    failures: list[FailureSummary] = field(default_factory=list)
    repair_output: RepairOutput | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def passed(self) -> bool:
        return self.verification_report.required_passed


@dataclass
class RepairResult:
    """Result of the full repair loop."""

    task_id: str
    run_id: str
    attempts: list[AttemptRecord] = field(default_factory=list)
    final_status: FinalStatus = FinalStatus.needs_review
    total_attempts: int = 0
    succeeded: bool = False
    final_report: VerificationReport | None = None

    @property
    def max_attempts_reached(self) -> bool:
        return self.total_attempts >= self._max_attempts

    @property
    def _max_attempts(self) -> int:
        return self._max_attempts_value

    _max_attempts_value: int = 3

    def set_max_attempts(self, max_attempts: int) -> None:
        self._max_attempts_value = max_attempts


class RepairLoop:
    """Orchestrates the repair cycle with attempt tracking.

    Implements Section 7.3: structured repair with attempt limits.
    The loop:
    1. Receives initial verification report (from first patch attempt)
    2. If failed, categorizes failures and builds RepairInput
    3. Calls RepairReasoner to produce a corrected patch
    4. Verifies the new patch
    5. Repeats until pass or max attempts reached

    All attempts are tracked for provenance and audit.
    """

    def __init__(
        self,
        verification_runner: VerificationRunner,
        categorizer: FailureCategorizer | None = None,
        repair_reasoner: RepairReasoner | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.verification_runner = verification_runner
        self.categorizer = categorizer or FailureCategorizer()
        self.repair_reasoner = repair_reasoner or RepairReasoner()
        self.max_attempts = max_attempts

    def run(
        self,
        task: Task,
        initial_patch: PatchCandidate,
        initial_report: VerificationReport,
        worktree_path: Path,
        apply_patch_fn: callable | None = None,
    ) -> RepairResult:
        """Run the repair loop.

        Args:
            task: The task being solved.
            initial_patch: The first patch attempt.
            initial_report: Verification report from the first attempt.
            worktree_path: Path to the sandboxed worktree.
            apply_patch_fn: Function to apply a diff to the worktree.
                           If None, patches are not applied (for testing).

        Returns:
            RepairResult with all attempt records and final status.
        """
        result = RepairResult(
            task_id=task.id,
            run_id=generate_run_id(),
        )
        result.set_max_attempts(self.max_attempts)

        # Record the initial attempt
        initial_failures = self.categorizer.categorize(initial_report)
        initial_record = AttemptRecord(
            attempt_no=1,
            patch_id=initial_patch.id,
            verification_report=initial_report,
            failures=initial_failures,
        )
        result.attempts.append(initial_record)
        result.total_attempts = 1

        logger.info(
            f"Repair loop started for task {task.id}: "
            f"attempt 1 {'passed' if initial_record.passed else 'failed'}"
        )

        # If initial attempt passed, we're done
        if initial_record.passed:
            result.succeeded = True
            result.final_status = FinalStatus.verified_candidate
            result.final_report = initial_report
            return result

        # Enter repair loop
        current_patch = initial_patch
        current_report = initial_report
        current_failures = initial_failures
        current_assumptions = list(initial_patch.assumptions)

        while result.total_attempts < self.max_attempts:
            attempt_no = result.total_attempts + 1

            # Build repair input
            repair_input = RepairInput(
                task_instruction=task.instruction,
                prior_patch_diff=current_patch.diff,
                prior_attempt_no=result.total_attempts,
                failures=current_failures,
                prior_assumptions=current_assumptions,
                remaining_attempts=self.max_attempts - result.total_attempts,
            )

            # Get repair output
            repair_output = self.repair_reasoner.repair(repair_input)

            # Create new patch candidate
            new_patch = PatchCandidate(
                id=generate_patch_id(),
                task_id=task.id,
                attempt_no=attempt_no,
                base_commit=current_patch.base_commit,
                diff=repair_output.patch_proposal.diff,
                changed_files=repair_output.patch_proposal.changed_files,
                changed_symbols=repair_output.patch_proposal.changed_symbols,
                assumptions=repair_output.revised_assumptions,
            )

            # Apply the patch if we have an apply function
            if apply_patch_fn and repair_output.patch_proposal.diff:
                success, error = apply_patch_fn(repair_output.patch_proposal.diff, worktree_path)
                if not success:
                    logger.warning(f"Patch application failed for attempt {attempt_no}: {error}")
                    # Create a synthetic failure report
                    failed_report = VerificationReport(
                        patch_id=new_patch.id,
                        checks=[
                            CheckResult(
                                check_type="syntax",
                                command="apply_patch",
                                exit_code=1,
                                status=CheckStatus.error,
                                error_message=f"Patch application failed: {error}",
                            ),
                        ],
                        required_passed=False,
                        blockers=[f"Patch application failed: {error}"],
                        final_status=FinalStatus.needs_review,
                    )
                    new_failures = self.categorizer.categorize(failed_report)
                    record = AttemptRecord(
                        attempt_no=attempt_no,
                        patch_id=new_patch.id,
                        verification_report=failed_report,
                        failures=new_failures,
                        repair_output=repair_output,
                    )
                    result.attempts.append(record)
                    result.total_attempts = attempt_no
                    current_patch = new_patch
                    current_report = failed_report
                    current_failures = new_failures
                    current_assumptions = repair_output.revised_assumptions
                    continue

            # Verify the new patch
            new_report = self.verification_runner.verify(
                patch=new_patch,
                task=task,
                worktree_path=worktree_path,
                changed_files=new_patch.changed_files,
            )

            new_failures = self.categorizer.categorize(new_report)

            record = AttemptRecord(
                attempt_no=attempt_no,
                patch_id=new_patch.id,
                verification_report=new_report,
                failures=new_failures,
                repair_output=repair_output,
            )
            result.attempts.append(record)
            result.total_attempts = attempt_no

            logger.info(
                f"Repair attempt {attempt_no}: "
                f"{'passed' if record.passed else 'failed'} "
                f"({len(new_failures)} failures)"
            )

            if record.passed:
                result.succeeded = True
                result.final_status = FinalStatus.verified_candidate
                result.final_report = new_report
                return result

            # Update for next iteration
            current_patch = new_patch
            current_report = new_report
            current_failures = new_failures
            current_assumptions = repair_output.revised_assumptions

        # Max attempts reached
        result.final_status = FinalStatus.needs_review
        result.final_report = current_report
        logger.info(
            f"Repair loop exhausted: {result.total_attempts} attempts, "
            f"final status: {result.final_status.value}"
        )

        return result

    def should_continue(self, result: RepairResult) -> bool:
        """Check if the repair loop should continue.

        Args:
            result: Current repair result.

        Returns:
            True if more attempts should be made.
        """
        return (
            not result.succeeded
            and result.total_attempts < self.max_attempts
        )

    def build_repair_input(
        self,
        task: Task,
        prior_patch: PatchCandidate,
        failures: list[FailureSummary],
        attempt_no: int,
        prior_assumptions: list[str] | None = None,
    ) -> RepairInput:
        """Build a RepairInput from the prior attempt's failures.

        Args:
            task: The task being solved.
            prior_patch: The prior patch attempt.
            failures: Categorized failures from the prior attempt.
            attempt_no: The prior attempt number.
            prior_assumptions: Assumptions from the prior attempt.

        Returns:
            RepairInput for the repair reasoner.
        """
        return RepairInput(
            task_instruction=task.instruction,
            prior_patch_diff=prior_patch.diff,
            prior_attempt_no=attempt_no,
            failures=failures,
            prior_assumptions=prior_assumptions or list(prior_patch.assumptions),
            remaining_attempts=self.max_attempts - attempt_no,
        )
