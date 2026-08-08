"""Tests for the critic and review service (Phase 6)."""

from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    EvidenceContract,
    FinalStatus,
    FindingSeverity,
    PatchCandidate,
    ReviewFinding,
    RiskLevel,
    Task,
    TaskType,
    VerificationReport,
)
from vsrs.reasoning.critic import (
    CATEGORY_BEHAVIOR_PRESERVATION,
    CATEGORY_DIFF_QUALITY,
    CATEGORY_GROUNDING,
    CATEGORY_MISSING_FALSIFICATION,
    CATEGORY_OVERREACH,
    CATEGORY_SECURITY,
    CATEGORY_TEST_GAP,
    CATEGORY_UNSUPPORTED_ASSUMPTION,
    Critic,
    CriticReport,
    ReviewService,
)


def _make_patch(
    diff: str = "",
    changed_files: list[str] | None = None,
    assumptions: list[str] | None = None,
    falsification_checks: list[str] | None = None,
    changed_symbols: list[str] | None = None,
) -> PatchCandidate:
    return PatchCandidate(
        id="patch_001",
        task_id="task_001",
        attempt_no=1,
        base_commit="abc123",
        diff=diff,
        changed_files=changed_files or ["src/auth.py"],
        changed_symbols=changed_symbols or [],
        assumptions=assumptions or [],
        falsification_checks=falsification_checks or [],
    )


def _make_task(
    task_type: TaskType = TaskType.bugfix,
    acceptance_criteria: list[str] | None = None,
) -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=task_type,
        instruction="Fix the empty password bug in auth",
        acceptance_criteria=acceptance_criteria or [],
        risk_level=RiskLevel.low,
        required_gates=["syntax", "existing_tests"],
    )


def _make_passed_report() -> VerificationReport:
    return VerificationReport(
        patch_id="patch_001",
        checks=[
            CheckResult(check_type="syntax", command="ast.parse", exit_code=0, status=CheckStatus.pass_),
            CheckResult(check_type="existing_tests", command="pytest", exit_code=0, status=CheckStatus.pass_),
            CheckResult(check_type="new_targeted_tests", command="pytest", exit_code=0, status=CheckStatus.pass_),
        ],
        required_passed=True,
        blockers=[],
        final_status=FinalStatus.verified_candidate,
    )


def _make_failed_report() -> VerificationReport:
    return VerificationReport(
        patch_id="patch_001",
        checks=[
            CheckResult(check_type="syntax", command="ast.parse", exit_code=0, status=CheckStatus.pass_),
            CheckResult(check_type="existing_tests", command="pytest", exit_code=1, status=CheckStatus.fail,
                        error_message="test_valid: AssertionError"),
        ],
        required_passed=False,
        blockers=["Required gate 'existing_tests' failed"],
        final_status=FinalStatus.needs_review,
    )


class TestCriticReport:
    def test_empty_report(self):
        report = CriticReport(findings=[])
        assert not report.has_blockers
        assert not report.needs_human_review
        assert report.can_auto_approve
        assert report.blocker_count == 0

    def test_with_blocker(self):
        report = CriticReport(findings=[
            ReviewFinding(id="1", patch_id="p1", severity=FindingSeverity.blocker, category="cat", text="text"),
        ])
        assert report.has_blockers
        assert report.needs_human_review
        assert not report.can_auto_approve
        assert report.blocker_count == 1

    def test_with_major(self):
        report = CriticReport(findings=[
            ReviewFinding(id="1", patch_id="p1", severity=FindingSeverity.major, category="cat", text="text"),
        ])
        assert not report.has_blockers
        assert report.needs_human_review
        assert report.major_count == 1

    def test_with_minor_only(self):
        report = CriticReport(findings=[
            ReviewFinding(id="1", patch_id="p1", severity=FindingSeverity.minor, category="cat", text="text"),
        ])
        assert not report.has_blockers
        assert not report.needs_human_review
        assert report.can_auto_approve
        assert report.minor_count == 1

    def test_findings_by_severity(self):
        report = CriticReport(findings=[
            ReviewFinding(id="1", patch_id="p1", severity=FindingSeverity.blocker, category="cat", text="text"),
            ReviewFinding(id="2", patch_id="p1", severity=FindingSeverity.minor, category="cat", text="text2"),
        ])
        blockers = report.findings_by_severity(FindingSeverity.blocker)
        assert len(blockers) == 1
        minors = report.findings_by_severity(FindingSeverity.minor)
        assert len(minors) == 1


class TestCritic:
    def test_empty_diff_is_blocker(self):
        critic = Critic()
        patch = _make_patch(diff="")
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assert result.has_blockers
        assert any(f.category == CATEGORY_DIFF_QUALITY and f.severity == FindingSeverity.blocker for f in result.findings)

    def test_non_empty_diff_no_blocker_for_empty(self):
        critic = Critic()
        patch = _make_patch(diff="--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,1 +1,2 @@\n x\n+y\n")
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assert not any(f.severity == FindingSeverity.blocker and "empty diff" in f.text for f in result.findings)

    def test_unsupported_assumption(self):
        critic = Critic()
        patch = _make_patch(
            diff="some diff",
            assumptions=["The API will never change"],
        )
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assert any(f.category == CATEGORY_UNSUPPORTED_ASSUMPTION for f in result.findings)
        assumption_findings = [f for f in result.findings if f.category == CATEGORY_UNSUPPORTED_ASSUMPTION]
        assert assumption_findings[0].severity == FindingSeverity.major

    def test_safe_assumption_is_minor(self):
        critic = Critic()
        patch = _make_patch(
            diff="some diff",
            assumptions=["The change is backward compatible"],
        )
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assumption_findings = [f for f in result.findings if f.category == CATEGORY_UNSUPPORTED_ASSUMPTION]
        assert assumption_findings[0].severity == FindingSeverity.minor

    def test_assumption_in_contract_not_flagged(self):
        critic = Critic()
        patch = _make_patch(
            diff="some diff",
            assumptions=["The API is stable"],
        )
        task = _make_task()
        report = _make_passed_report()
        contract = EvidenceContract(
            change_id="change_001",
            assumptions=["The API is stable"],
        )

        result = critic.review(patch, task, report, contract=contract)

        assert not any(f.category == CATEGORY_UNSUPPORTED_ASSUMPTION for f in result.findings)

    def test_test_gap_no_new_tests(self):
        critic = Critic()
        patch = _make_patch(diff="some diff")
        task = _make_task(acceptance_criteria=["reject empty password"])
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(check_type="syntax", command="ast.parse", exit_code=0, status=CheckStatus.pass_),
                CheckResult(check_type="existing_tests", command="pytest", exit_code=0, status=CheckStatus.pass_),
                CheckResult(check_type="new_targeted_tests", command="pytest", status=CheckStatus.skip),
            ],
            required_passed=True,
        )

        result = critic.review(patch, task, report)

        assert any(f.category == CATEGORY_TEST_GAP for f in result.findings)

    def test_overreach_too_many_files(self):
        critic = Critic()
        patch = _make_patch(
            diff="some diff",
            changed_files=["a.py", "b.py", "c.py", "d.py", "e.py"],
        )
        task = _make_task(task_type=TaskType.bugfix)  # max 3 files for bugfix

        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assert any(f.category == CATEGORY_OVERREACH for f in result.findings)

    def test_no_overreach_within_limit(self):
        critic = Critic()
        patch = _make_patch(
            diff="some diff",
            changed_files=["a.py", "b.py"],
        )
        task = _make_task(task_type=TaskType.bugfix)
        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assert not any(f.category == CATEGORY_OVERREACH for f in result.findings)

    def test_grounding_no_evidence(self):
        critic = Critic()
        patch = _make_patch(diff="some diff", changed_files=["src/auth.py"])
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report, evidence_locators=[])

        assert any(f.category == CATEGORY_GROUNDING for f in result.findings)

    def test_grounding_with_evidence(self):
        critic = Critic()
        patch = _make_patch(diff="some diff", changed_files=["src/auth.py"])
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report, evidence_locators=["src/auth.py:10"])

        assert not any(f.category == CATEGORY_GROUNDING for f in result.findings)

    def test_missing_falsification_in_contract(self):
        critic = Critic()
        patch = _make_patch(diff="some diff")
        task = _make_task()
        report = _make_passed_report()
        contract = EvidenceContract(change_id="change_001", falsification_checks=[])

        result = critic.review(patch, task, report, contract=contract)

        assert any(f.category == CATEGORY_MISSING_FALSIFICATION and f.severity == FindingSeverity.major for f in result.findings)

    def test_missing_falsification_in_patch(self):
        critic = Critic()
        patch = _make_patch(diff="some diff", falsification_checks=[])
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assert any(f.category == CATEGORY_MISSING_FALSIFICATION for f in result.findings)

    def test_debug_statement_in_diff(self):
        critic = Critic()
        patch = _make_patch(diff="+    print('debug')\n")
        task = _make_task()
        report = _make_passed_report()

        result = critic.review(patch, task, report)

        assert any(f.category == CATEGORY_DIFF_QUALITY and "debug" in f.text.lower() for f in result.findings)

    def test_behavior_preservation_existing_tests_fail(self):
        critic = Critic()
        patch = _make_patch(diff="some diff")
        task = _make_task()
        report = _make_failed_report()

        result = critic.review(patch, task, report)

        assert any(f.category == CATEGORY_BEHAVIOR_PRESERVATION and f.severity == FindingSeverity.blocker for f in result.findings)

    def test_security_scan_failure_is_blocker(self):
        critic = Critic()
        patch = _make_patch(diff="some diff")
        task = _make_task()
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(check_type="security_scan", command="bandit", exit_code=1,
                            status=CheckStatus.fail, error_message="B101 hardcoded password"),
            ],
            required_passed=False,
            blockers=["security_scan failed"],
        )

        result = critic.review(patch, task, report)

        assert any(f.category == CATEGORY_SECURITY and f.severity == FindingSeverity.blocker for f in result.findings)

    def test_verification_error_is_major(self):
        critic = Critic()
        patch = _make_patch(diff="some diff")
        task = _make_task()
        report = VerificationReport(
            patch_id="patch_001",
            checks=[
                CheckResult(check_type="type_check", command="mypy", exit_code=-1,
                            status=CheckStatus.error, error_message="mypy crashed"),
            ],
            required_passed=True,
        )

        result = critic.review(patch, task, report)

        assert any(f.severity == FindingSeverity.major and "errored" in f.text for f in result.findings)

    def test_clean_patch_minimal_findings(self):
        critic = Critic()
        patch = _make_patch(
            diff="some diff",
            changed_files=["src/auth.py"],
            assumptions=["The change is backward compatible"],
            falsification_checks=["test_empty_password_rejected"],
        )
        task = _make_task()
        report = _make_passed_report()
        contract = EvidenceContract(
            change_id="change_001",
            assumptions=["The change is backward compatible"],
            falsification_checks=["test_empty_password_rejected"],
        )

        result = critic.review(patch, task, report, contract=contract, evidence_locators=["src/auth.py:10"])

        # Should have only minor findings (safe assumption, edge case hint)
        assert not result.has_blockers
        assert result.major_count == 0


class TestReviewService:
    def test_auto_approve_clean_patch(self):
        service = ReviewService()
        patch = _make_patch(
            diff="some diff",
            assumptions=["The change is backward compatible"],
            falsification_checks=["test_empty_password"],
        )
        task = _make_task()
        report = _make_passed_report()
        contract = EvidenceContract(
            change_id="change_001",
            assumptions=["The change is backward compatible"],
            falsification_checks=["test_empty_password"],
        )

        critic_report, decision = service.review(
            patch, task, report, contract=contract, evidence_locators=["src/auth.py:10"],
        )

        assert decision.status == FinalStatus.verified_candidate
        assert len(decision.blockers) == 0

    def test_reject_when_gates_fail(self):
        service = ReviewService()
        patch = _make_patch(diff="some diff")
        task = _make_task()
        report = _make_failed_report()

        critic_report, decision = service.review(patch, task, report)

        assert decision.status == FinalStatus.rejected
        assert len(decision.blockers) > 0

    def test_needs_review_when_blocker(self):
        service = ReviewService()
        patch = _make_patch(diff="")  # empty diff = blocker
        task = _make_task()
        report = _make_passed_report()

        critic_report, decision = service.review(patch, task, report)

        assert decision.status == FinalStatus.needs_review
        assert any("empty diff" in b for b in decision.blockers)

    def test_needs_review_when_major(self):
        service = ReviewService()
        patch = _make_patch(
            diff="some diff",
            assumptions=["The API will never change"],  # unsupported = major
        )
        task = _make_task()
        report = _make_passed_report()

        critic_report, decision = service.review(patch, task, report)

        assert decision.status == FinalStatus.needs_review

    def test_summary_built(self):
        service = ReviewService()
        patch = _make_patch(diff="")  # blocker
        task = _make_task()
        report = _make_passed_report()

        critic_report, decision = service.review(patch, task, report)

        assert decision.summary
        assert "blocker" in decision.summary.lower()

    def test_summary_no_issues(self):
        service = ReviewService()
        patch = _make_patch(
            diff="some diff",
            assumptions=["The change is backward compatible"],
            falsification_checks=["test_x"],
        )
        task = _make_task()
        report = _make_passed_report()
        contract = EvidenceContract(
            change_id="c1",
            assumptions=["The change is backward compatible"],
            falsification_checks=["test_x"],
        )

        critic_report, decision = service.review(
            patch, task, report, contract=contract, evidence_locators=["src/auth.py:10"],
        )

        assert "No issues" in decision.summary or "passed" in decision.summary
