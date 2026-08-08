"""Repair reasoner: produces RepairOutput from RepairInput (Section 7.3).

Takes a structured RepairInput (prior patch, categorized failures, prior
assumptions) and produces a RepairOutput with a corrected patch proposal
and failure analysis.

In V1, this is a deterministic rule-based repair reasoner. In later phases,
this will be replaced by an LLM call with structured output validation.
"""

from __future__ import annotations

from vsrs.core.logging import get_logger
from vsrs.reasoning.protocol import (
    FailureSummary,
    PatchProposal,
    RepairInput,
    RepairOutput,
)

logger = get_logger("repair.reasoner")


class RepairReasoner:
    """Produces repair patches from structured failure summaries.

    Implements Section 7.3: the repair reasoner receives categorized failures
    (not raw logs) and produces a corrected patch with failure analysis.

    In V1, this is a deterministic reasoner that:
    - Analyzes failure categories to determine what went wrong
    - Produces a failure analysis string
    - Generates revised assumptions
    - Returns an empty patch (actual patch generation requires LLM integration)
    """

    def repair(self, repair_input: RepairInput) -> RepairOutput:
        """Produce a repair output from a repair input.

        Args:
            repair_input: Structured input with prior patch and failures.

        Returns:
            RepairOutput with corrected patch proposal and analysis.
        """
        logger.info(
            f"Repairing attempt {repair_input.prior_attempt_no} "
            f"with {len(repair_input.failures)} failures, "
            f"{repair_input.remaining_attempts} attempts remaining"
        )

        # Analyze failures
        failure_analysis = self._analyze_failures(repair_input.failures)

        # Determine revised assumptions
        revised_assumptions = self._revise_assumptions(
            repair_input.prior_assumptions, repair_input.failures,
        )

        # Determine if new evidence is needed
        new_evidence_needed = self._determine_new_evidence(repair_input.failures)

        # Generate patch proposal (V1: empty diff — LLM generates actual patch)
        patch_proposal = self._generate_repair_patch(repair_input, failure_analysis)

        return RepairOutput(
            patch_proposal=patch_proposal,
            failure_analysis=failure_analysis,
            revised_assumptions=revised_assumptions,
            new_evidence_needed=new_evidence_needed,
        )

    def _analyze_failures(self, failures: list[FailureSummary]) -> str:
        """Analyze the failures and produce a human-readable analysis."""
        if not failures:
            return "No failures detected — prior patch may have succeeded."

        parts: list[str] = []

        # Group by category
        by_category: dict[str, list[FailureSummary]] = {}
        for f in failures:
            by_category.setdefault(f.error_category, []).append(f)

        for category, cat_failures in by_category.items():
            if category == "syntax":
                files = {f.relevant_file for f in cat_failures if f.relevant_file}
                parts.append(
                    f"Syntax errors in {', '.join(files) or 'changed files'}: "
                    f"the patch introduced invalid Python syntax"
                )
            elif category == "test_failure":
                test_names = set()
                for f in cat_failures:
                    test_names.update(f.failed_test_names)
                parts.append(
                    f"Test failures ({len(cat_failures)} checks): "
                    f"tests {', '.join(list(test_names)[:3])} failed — "
                    f"the patch did not produce the expected behavior"
                )
            elif category == "type_error":
                parts.append(
                    f"Type errors ({len(cat_failures)}): "
                    f"the patch introduced type mismatches"
                )
            elif category == "import_error":
                parts.append(
                    f"Import errors ({len(cat_failures)}): "
                    f"the patch references modules that don't exist or aren't installed"
                )
            elif category == "lint":
                parts.append(
                    f"Lint issues ({len(cat_failures)}): "
                    f"the patch introduced style violations"
                )
            elif category == "security":
                parts.append(
                    f"Security findings ({len(cat_failures)}): "
                    f"the patch introduced potential security vulnerabilities"
                )
            elif category == "config":
                parts.append(
                    f"Configuration issues ({len(cat_failures)}): "
                    f"the patch or build configuration is incorrect"
                )
            else:
                parts.append(
                    f"Other issues ({len(cat_failures)}): "
                    f"un categorized failures detected"
                )

        return "; ".join(parts)

    def _revise_assumptions(
        self,
        prior_assumptions: list[str],
        failures: list[FailureSummary],
    ) -> list[str]:
        """Revise assumptions based on failures."""
        revised = list(prior_assumptions)

        # Remove assumptions that were proven wrong
        for failure in failures:
            if failure.error_category == "import_error":
                revised = [
                    a for a in revised
                    if "import" not in a.lower() and "module" not in a.lower()
                ]
                revised.append("The imported module does not exist — need to verify import paths")
            elif failure.error_category == "test_failure":
                revised = [
                    a for a in revised
                    if "behavior" not in a.lower() and "correct" not in a.lower()
                ]
                revised.append("The prior patch did not produce the expected behavior")
            elif failure.error_category == "syntax":
                revised.append("The prior patch had syntax errors — need to be more careful with syntax")
            elif failure.error_category == "type_error":
                revised.append("Type annotations need to be updated to match the changes")

        # Deduplicate
        return list(dict.fromkeys(revised))

    def _determine_new_evidence(self, failures: list[FailureSummary]) -> list[str]:
        """Determine what new evidence needs to be retrieved."""
        needed: list[str] = []

        categories = {f.error_category for f in failures}

        if "import_error" in categories:
            needed.append("Verify which modules exist and their correct import paths")
        if "type_error" in categories:
            needed.append("Retrieve type signatures of affected functions")
        if "test_failure" in categories:
            needed.append("Retrieve the failing test code to understand expected behavior")
        if "syntax" in categories:
            needed.append("Retrieve the current file content to verify syntax context")
        if "security" in categories:
            needed.append("Retrieve security best practices for the identified pattern")

        return needed

    def _generate_repair_patch(
        self,
        repair_input: RepairInput,
        failure_analysis: str,
    ) -> PatchProposal:
        """Generate a repair patch proposal.

        In V1, this returns an empty diff with metadata. Actual patch
        generation requires LLM integration.
        """
        # Collect files from failures
        files_to_fix = list(dict.fromkeys(
            f.relevant_file for f in repair_input.failures if f.relevant_file
        ))

        return PatchProposal(
            diff="",  # V1: empty — LLM generates the actual diff
            changed_files=files_to_fix,
            changed_symbols=[],
            new_files=[],
            new_tests=[],
            rationale=f"Repair attempt {repair_input.prior_attempt_no + 1}: {failure_analysis[:100]}",
            assumptions=repair_input.prior_assumptions,
        )
