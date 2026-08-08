"""Multi-language verification runner.

Extends the verification pipeline to support multiple programming languages.
Detects the language(s) in the repository or from changed files and runs
the appropriate checks using language adapters.
"""

from __future__ import annotations

import time
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    FinalStatus,
    PatchCandidate,
    Task,
    VerificationReport,
)
from vsrs.languages.base import LanguageAdapter
from vsrs.languages.registry import LanguageRegistry, get_registry
from vsrs.verify.gates import evaluate_gates

logger = get_logger("verify.multilang")


class MultiLanguageVerificationRunner:
    """Verification runner that supports multiple programming languages.

    Detects which languages are present in the changed files and runs
    the appropriate checks for each language using its adapter.

    Args:
        registry: Optional language registry. Defaults to the global registry.
    """

    def __init__(
        self,
        registry: LanguageRegistry | None = None,
    ) -> None:
        self.registry = registry or get_registry()

    def verify(
        self,
        patch: PatchCandidate,
        task: Task,
        worktree_path: Path,
        changed_files: list[str] | None = None,
    ) -> VerificationReport:
        """Run verification checks for all detected languages.

        Args:
            patch: The patch candidate being verified.
            task: The task being solved.
            worktree_path: Path to the worktree with patch applied.
            changed_files: Specific files changed by the patch.

        Returns:
            VerificationReport with all check results and gate evaluation.
        """
        start_time = time.time()
        checks: list[CheckResult] = []

        if changed_files is None:
            changed_files = patch.changed_files

        # Detect languages from changed files
        adapters = self.registry.detect_for_files(changed_files)

        if not adapters:
            # Fallback: detect from repo
            adapters = self.registry.detect_for_repo(worktree_path)

        if not adapters:
            logger.warning("No language adapters matched the changed files")
            checks.append(CheckResult(
                check_type="syntax",
                command="none",
                status=CheckStatus.skip,
                error_message="No language detected for changed files",
            ))
        else:
            for adapter in adapters:
                lang_name = adapter.info.name
                lang_files = adapter.filter_files(changed_files)
                logger.info(
                    f"Running {lang_name} checks for {len(lang_files)} files"
                )

                # Syntax check
                checks.append(adapter.syntax_check(worktree_path, lang_files))

                # Build
                checks.append(adapter.build(worktree_path))

                # Tests
                checks.append(adapter.run_tests(worktree_path))

                # Lint
                checks.append(adapter.lint(worktree_path, lang_files))

                # Type check
                checks.append(adapter.type_check(worktree_path, lang_files))

        # Evaluate required gates
        required_gates = task.required_gates
        all_passed, blockers = evaluate_gates(checks, required_gates)

        final_status = FinalStatus.verified_candidate if all_passed else FinalStatus.needs_review

        elapsed = time.time() - start_time
        logger.info(
            f"Multi-language verification complete: "
            f"{len(checks)} checks, {len(blockers)} blockers, "
            f"final={final_status.value}, duration={elapsed:.2f}s"
        )

        return VerificationReport(
            patch_id=patch.id,
            checks=checks,
            required_passed=all_passed,
            blockers=blockers,
            unresolved_unknowns=[],
            final_status=final_status,
        )

    def detect_languages(self, files: list[str]) -> list[str]:
        """Detect which languages are needed for a set of files.

        Args:
            files: List of file paths.

        Returns:
            List of language names detected.
        """
        adapters = self.registry.detect_for_files(files)
        return [a.info.name for a in adapters]
