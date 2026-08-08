"""Critic: find unsupported assumptions, test gaps, overreach (Section 9.1).

Automated review layer that examines a patch candidate and its verification
report to identify:
- Unsupported assumptions (claims without evidence)
- Test gaps (missing edge case tests, no falsification)
- Overreach (changes beyond what the task requires)
- Grounding issues (symbols/files referenced but not in evidence)
- Behavior preservation risks

Produces ReviewFinding objects with severity levels that feed into the
review decision process.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from vsrs.core.ids import generate_finding_id
from vsrs.core.logging import get_logger
from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    EvidenceContract,
    FinalDecision,
    FinalStatus,
    FindingSeverity,
    PatchCandidate,
    ReviewFinding,
    Task,
    VerificationReport,
)

logger = get_logger("reasoning.critic")


# Categories for critic findings
CATEGORY_UNSUPPORTED_ASSUMPTION = "unsupported_assumption"
CATEGORY_TEST_GAP = "test_gap"
CATEGORY_OVERREACH = "overreach"
CATEGORY_GROUNDING = "grounding_issue"
CATEGORY_BEHAVIOR_PRESERVATION = "behavior_preservation"
CATEGORY_MISSING_FALSIFICATION = "missing_falsification"
CATEGORY_DIFF_QUALITY = "diff_quality"
CATEGORY_SECURITY = "security_concern"


@dataclass
class CriticReport:
    """Result of the critic's review of a patch."""

    findings: list[ReviewFinding] = field(default_factory=list)

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.blocker)

    @property
    def major_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.major)

    @property
    def minor_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.minor)

    @property
    def has_blockers(self) -> bool:
        return self.blocker_count > 0

    @property
    def needs_human_review(self) -> bool:
        return self.blocker_count > 0 or self.major_count > 0

    @property
    def can_auto_approve(self) -> bool:
        return not self.needs_human_review

    def findings_by_severity(self, severity: FindingSeverity) -> list[ReviewFinding]:
        return [f for f in self.findings if f.severity == severity]


class Critic:
    """Automated critic that reviews patch candidates.

    Implements Section 9.1: the critic examines the patch, verification report,
    evidence contract, and task to find issues that automated checks might miss.

    The critic does NOT modify the patch — it only produces findings that
    feed into the review decision.
    """

    def review(
        self,
        patch: PatchCandidate,
        task: Task,
        report: VerificationReport,
        contract: EvidenceContract | None = None,
        evidence_locators: list[str] | None = None,
    ) -> CriticReport:
        """Review a patch candidate and produce findings.

        Args:
            patch: The patch candidate being reviewed.
            task: The task being solved.
            report: Verification report from the patch attempt.
            contract: Optional evidence contract for the patch.
            evidence_locators: Locators of evidence used to ground the patch.

        Returns:
            CriticReport with all findings.
        """
        findings: list[ReviewFinding] = []
        evidence_locators = evidence_locators or []

        # 1. Check for unsupported assumptions
        findings.extend(self._check_assumptions(patch, contract))

        # 2. Check for test gaps
        findings.extend(self._check_test_gaps(patch, task, report))

        # 3. Check for overreach (changes beyond task scope)
        findings.extend(self._check_overreach(patch, task))

        # 4. Check grounding (are changed symbols in evidence?)
        findings.extend(self._check_grounding(patch, evidence_locators))

        # 5. Check for missing falsification
        findings.extend(self._check_falsification(patch, contract))

        # 6. Check diff quality
        findings.extend(self._check_diff_quality(patch))

        # 7. Check behavior preservation
        findings.extend(self._check_behavior_preservation(patch, report))

        # 8. Check verification failures
        findings.extend(self._check_verification_failures(patch, report))

        logger.info(
            f"Critic reviewed patch {patch.id}: "
            f"{len(findings)} findings "
            f"({self._count_by_severity(findings)})"
        )

        return CriticReport(findings=findings)

    def _count_by_severity(self, findings: list[ReviewFinding]) -> str:
        counts = {}
        for f in findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))

    def _make_finding(
        self,
        patch_id: str,
        severity: FindingSeverity,
        category: str,
        text: str,
        evidence_refs: list[str] | None = None,
    ) -> ReviewFinding:
        return ReviewFinding(
            id=generate_finding_id(),
            patch_id=patch_id,
            severity=severity,
            category=category,
            evidence_refs=evidence_refs or [],
            text=text,
        )

    def _check_assumptions(
        self,
        patch: PatchCandidate,
        contract: EvidenceContract | None,
    ) -> list[ReviewFinding]:
        """Check for unsupported assumptions."""
        findings: list[ReviewFinding] = []

        if not patch.assumptions:
            return findings

        contract_assumptions = set(contract.assumptions) if contract else set()

        for assumption in patch.assumptions:
            if assumption not in contract_assumptions:
                # Check if the assumption is a common safe assumption
                safe_patterns = ["no side effects", "backward compatible", "no breaking changes"]
                is_safe = any(p in assumption.lower() for p in safe_patterns)

                if is_safe:
                    findings.append(self._make_finding(
                        patch_id=patch.id,
                        severity=FindingSeverity.minor,
                        category=CATEGORY_UNSUPPORTED_ASSUMPTION,
                        text=f"Assumption not in evidence contract (likely safe): '{assumption}'",
                    ))
                else:
                    findings.append(self._make_finding(
                        patch_id=patch.id,
                        severity=FindingSeverity.major,
                        category=CATEGORY_UNSUPPORTED_ASSUMPTION,
                        text=f"Assumption not grounded in evidence contract: '{assumption}'",
                    ))

        return findings

    def _check_test_gaps(
        self,
        patch: PatchCandidate,
        task: Task,
        report: VerificationReport,
    ) -> list[ReviewFinding]:
        """Check for test gaps."""
        findings: list[ReviewFinding] = []

        # Check if new targeted tests were run
        targeted_checks = [c for c in report.checks if c.check_type == "new_targeted_tests"]
        for check in targeted_checks:
            if check.status == CheckStatus.skip:
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.major,
                    category=CATEGORY_TEST_GAP,
                    text="No new targeted tests were run for this patch — behavior change is untested",
                ))

        # Check if acceptance criteria have corresponding tests
        if task.acceptance_criteria and not any(
            c.check_type == "new_targeted_tests" and c.status == CheckStatus.pass_
            for c in report.checks
        ):
            findings.append(self._make_finding(
                patch_id=patch.id,
                severity=FindingSeverity.major,
                category=CATEGORY_TEST_GAP,
                text=f"Acceptance criteria defined ({len(task.acceptance_criteria)}) but no new tests pass to verify them",
            ))

        # Check for edge case coverage
        if patch.changed_files and not any(
            "edge" in str.lower(c.error_message) or "edge" in c.check_type
            for c in report.checks
        ):
            # Only flag if there are changed files but no edge case tests
            if task.type.value in ("bugfix", "feature", "security"):
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.minor,
                    category=CATEGORY_TEST_GAP,
                    text="No edge case tests detected — consider testing boundary conditions",
                ))

        return findings

    def _check_overreach(
        self,
        patch: PatchCandidate,
        task: Task,
    ) -> list[ReviewFinding]:
        """Check for changes beyond task scope."""
        findings: list[ReviewFinding] = []

        # Check if too many files changed
        max_files = self._expected_max_files(task)
        if len(patch.changed_files) > max_files:
            findings.append(self._make_finding(
                patch_id=patch.id,
                severity=FindingSeverity.major,
                category=CATEGORY_OVERREACH,
                text=f"Patch changes {len(patch.changed_files)} files but task likely requires at most {max_files}",
            ))

        # Check if changed symbols seem unrelated to task
        task_keywords = set(task.instruction.lower().split())
        for symbol in patch.changed_symbols:
            symbol_words = set(symbol.lower().replace("_", " ").replace(".", " ").split())
            overlap = task_keywords & symbol_words
            if not overlap and len(patch.changed_symbols) > 3:
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.minor,
                    category=CATEGORY_OVERREACH,
                    text=f"Changed symbol '{symbol}' has no keyword overlap with task instruction",
                ))

        return findings

    def _expected_max_files(self, task: Task) -> int:
        """Estimate the expected max number of files for a task type."""
        limits = {
            "bugfix": 3,
            "feature": 5,
            "refactor": 10,
            "test": 5,
            "security": 3,
            "migration": 7,
        }
        return limits.get(task.type.value, 5)

    def _check_grounding(
        self,
        patch: PatchCandidate,
        evidence_locators: list[str],
    ) -> list[ReviewFinding]:
        """Check that changed files/symbols are grounded in evidence."""
        findings: list[ReviewFinding] = []

        if not evidence_locators:
            if patch.changed_files:
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.major,
                    category=CATEGORY_GROUNDING,
                    text="No evidence locators provided but patch changes files — changes are ungrounded",
                ))
            return findings

        # Check if changed files appear in evidence
        evidence_files = set()
        for loc in evidence_locators:
            # Extract file path from locator (file:line format)
            parts = loc.split(":")
            if parts:
                evidence_files.add(parts[0])

        for file in patch.changed_files:
            if file not in evidence_files:
                # Check partial match
                partial_match = any(file in ef or ef in file for ef in evidence_files)
                if not partial_match:
                    findings.append(self._make_finding(
                        patch_id=patch.id,
                        severity=FindingSeverity.minor,
                        category=CATEGORY_GROUNDING,
                        text=f"Changed file '{file}' not found in evidence locators",
                    ))

        return findings

    def _check_falsification(
        self,
        patch: PatchCandidate,
        contract: EvidenceContract | None,
    ) -> list[ReviewFinding]:
        """Check for missing falsification checks."""
        findings: list[ReviewFinding] = []

        if contract and not contract.falsification_checks:
            findings.append(self._make_finding(
                patch_id=patch.id,
                severity=FindingSeverity.major,
                category=CATEGORY_MISSING_FALSIFICATION,
                text="Evidence contract has no falsification checks — patch cannot be proven wrong",
            ))

        if not patch.falsification_checks:
            findings.append(self._make_finding(
                patch_id=patch.id,
                severity=FindingSeverity.minor,
                category=CATEGORY_MISSING_FALSIFICATION,
                text="Patch has no falsification checks defined",
            ))

        return findings

    def _check_diff_quality(self, patch: PatchCandidate) -> list[ReviewFinding]:
        """Check diff quality issues."""
        findings: list[ReviewFinding] = []

        if not patch.diff.strip():
            findings.append(self._make_finding(
                patch_id=patch.id,
                severity=FindingSeverity.blocker,
                category=CATEGORY_DIFF_QUALITY,
                text="Patch has an empty diff — no changes were made",
            ))
        else:
            # Check for large diffs
            diff_lines = patch.diff.count("\n")
            if diff_lines > 200:
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.minor,
                    category=CATEGORY_DIFF_QUALITY,
                    text=f"Diff is large ({diff_lines} lines) — consider splitting into smaller patches",
                ))

            # Check for debug statements
            debug_patterns = ["print(", "breakpoint()", "pdb.set_trace", "import pdb"]
            for pattern in debug_patterns:
                if pattern in patch.diff:
                    findings.append(self._make_finding(
                        patch_id=patch.id,
                        severity=FindingSeverity.major,
                        category=CATEGORY_DIFF_QUALITY,
                        text=f"Debug statement '{pattern}' found in diff",
                    ))
                    break

        return findings

    def _check_behavior_preservation(
        self,
        patch: PatchCandidate,
        report: VerificationReport,
    ) -> list[ReviewFinding]:
        """Check for behavior preservation risks."""
        findings: list[ReviewFinding] = []

        # Check if existing tests still pass
        existing_test_checks = [c for c in report.checks if c.check_type == "existing_tests"]
        for check in existing_test_checks:
            if check.status == CheckStatus.fail:
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.blocker,
                    category=CATEGORY_BEHAVIOR_PRESERVATION,
                    text="Existing tests fail — patch may have broken existing behavior",
                ))

        # Check for API compatibility
        api_checks = [c for c in report.checks if c.check_type == "api_compatibility"]
        for check in api_checks:
            if check.status == CheckStatus.fail:
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.major,
                    category=CATEGORY_BEHAVIOR_PRESERVATION,
                    text="API compatibility check failed — public contract may have changed",
                ))

        return findings

    def _check_verification_failures(
        self,
        patch: PatchCandidate,
        report: VerificationReport,
    ) -> list[ReviewFinding]:
        """Check for verification failures that need attention."""
        findings: list[ReviewFinding] = []

        for check in report.checks:
            if check.status == CheckStatus.error:
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.major,
                    category=CATEGORY_DIFF_QUALITY,
                    text=f"Verification check '{check.check_type}' errored: {check.error_message[:100]}",
                ))
            elif check.status == CheckStatus.fail and check.check_type == "security_scan":
                findings.append(self._make_finding(
                    patch_id=patch.id,
                    severity=FindingSeverity.blocker,
                    category=CATEGORY_SECURITY,
                    text=f"Security scan failed: {check.error_message[:100]}",
                ))

        return findings


class ReviewService:
    """Review service: collects critic findings and produces a final decision.

    Implements Section 9.2: determines whether a patch can be auto-approved,
    needs human review, or should be rejected based on critic findings and
    verification results.
    """

    def __init__(self, critic: Critic | None = None) -> None:
        self.critic = critic or Critic()

    def review(
        self,
        patch: PatchCandidate,
        task: Task,
        report: VerificationReport,
        contract: EvidenceContract | None = None,
        evidence_locators: list[str] | None = None,
    ) -> tuple[CriticReport, FinalDecision]:
        """Review a patch and produce a final decision.

        Args:
            patch: The patch candidate.
            task: The task being solved.
            report: Verification report.
            contract: Optional evidence contract.
            evidence_locators: Evidence locators used.

        Returns:
            Tuple of (CriticReport, FinalDecision).
        """
        critic_report = self.critic.review(
            patch=patch,
            task=task,
            report=report,
            contract=contract,
            evidence_locators=evidence_locators,
        )

        # Determine final status
        if not report.required_passed:
            status = FinalStatus.rejected
            blockers = list(report.blockers)
        elif critic_report.has_blockers:
            status = FinalStatus.needs_review
            blockers = [f.text for f in critic_report.findings_by_severity(FindingSeverity.blocker)]
        elif critic_report.needs_human_review:
            status = FinalStatus.needs_review
            blockers = [f.text for f in critic_report.findings_by_severity(FindingSeverity.major)]
        else:
            status = FinalStatus.verified_candidate
            blockers = []

        # Collect all blockers
        all_blockers = list(report.blockers)
        all_blockers.extend(blockers)

        decision = FinalDecision(
            task_id=task.id,
            status=status,
            blockers=all_blockers,
            waived_gates=[],
            summary=self._build_summary(critic_report, report),
            provenance_id="",
        )

        logger.info(
            f"Review decision for patch {patch.id}: {status.value} "
            f"({len(all_blockers)} blockers, {len(critic_report.findings)} findings)"
        )

        return critic_report, decision

    def _build_summary(self, critic_report: CriticReport, verification_report: VerificationReport) -> str:
        """Build a human-readable summary of the review."""
        parts: list[str] = []

        if critic_report.has_blockers:
            parts.append(f"{critic_report.blocker_count} blocker(s)")
        if critic_report.major_count > 0:
            parts.append(f"{critic_report.major_count} major issue(s)")
        if critic_report.minor_count > 0:
            parts.append(f"{critic_report.minor_count} minor issue(s)")

        if not parts:
            parts.append("No issues found")

        if verification_report.required_passed:
            parts.append("all required gates passed")
        else:
            parts.append("required gates failed")

        return "; ".join(parts)
