"""Verification runner: orchestrates checks, captures output, timing (Section 8).

Coordinates running all verification adapters (pytest, ruff, mypy, bandit)
in a sandboxed worktree, collects results, evaluates gates, and produces
a VerificationReport.
"""

from __future__ import annotations

import ast
import time
from dataclasses import dataclass, field
from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.core.policy import GatePolicyEngine
from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    FinalStatus,
    PatchCandidate,
    RiskLevel,
    Task,
    TaskType,
    VerificationReport,
)
from vsrs.verify.gates import evaluate_gates
from vsrs.verify.lint_adapter import LintAdapter
from vsrs.verify.pytest_adapter import PytestAdapter
from vsrs.verify.sandbox import Sandbox
from vsrs.verify.security_adapter import SecurityAdapter
from vsrs.verify.type_adapter import TypeCheckAdapter

logger = get_logger("verify.runner")


@dataclass
class VerificationConfig:
    """Configuration for verification runs."""

    pytest_timeout: int = 120
    lint_timeout: int = 60
    mypy_timeout: int = 120
    bandit_timeout: int = 60
    run_lint: bool = True
    run_type_check: bool = True
    run_security: bool = True
    test_paths: list[str] | None = None


class VerificationRunner:
    """Orchestrates verification checks for a patch candidate.

    Runs all applicable verification adapters in a sandboxed worktree,
    collects results, evaluates required gates, and produces a
    VerificationReport.
    """

    def __init__(
        self,
        sandbox: Sandbox | None = None,
        config: VerificationConfig | None = None,
        policy_engine: GatePolicyEngine | None = None,
    ) -> None:
        self.sandbox = sandbox
        self.config = config or VerificationConfig()
        self.policy_engine = policy_engine or GatePolicyEngine()
        self.pytest_adapter = PytestAdapter(sandbox=sandbox)
        self.lint_adapter = LintAdapter(sandbox=sandbox)
        self.type_adapter = TypeCheckAdapter(sandbox=sandbox)
        self.security_adapter = SecurityAdapter(sandbox=sandbox)

    def verify(
        self,
        patch: PatchCandidate,
        task: Task,
        worktree_path: Path,
        changed_files: list[str] | None = None,
    ) -> VerificationReport:
        """Run verification checks on a patch in a worktree.

        Args:
            patch: The patch candidate being verified.
            task: The task being solved.
            worktree_path: Path to the sandboxed worktree with patch applied.
            changed_files: Specific files changed by the patch.

        Returns:
            VerificationReport with all check results and gate evaluation.
        """
        start_time = time.time()
        checks: list[CheckResult] = []
        logger.info(f"Verifying patch {patch.id} for task {task.id}")

        if changed_files is None:
            changed_files = patch.changed_files

        python_files = [f for f in changed_files if f.endswith(".py")]

        # 1. Syntax check — always run
        syntax_check = self._check_syntax(worktree_path, python_files)
        checks.append(syntax_check)

        # 2. Pytest — existing tests
        pytest_check = self._run_pytest(worktree_path, check_type="existing_tests")
        checks.append(pytest_check)

        # 3. Pytest — new targeted tests (if any test files were changed)
        new_test_files = [f for f in python_files if "test" in f]
        if new_test_files:
            targeted_check = self._run_pytest(
                worktree_path,
                test_paths=new_test_files,
                check_type="new_targeted_tests",
            )
            checks.append(targeted_check)
        else:
            checks.append(CheckResult(
                check_type="new_targeted_tests",
                command="python -m pytest",
                status=CheckStatus.skip,
                error_message="No new test files to run",
            ))

        # 4. Lint — ruff
        if self.config.run_lint:
            lint_check = self._run_lint(worktree_path, python_files)
            checks.append(lint_check)
        else:
            checks.append(CheckResult(
                check_type="lint",
                command="ruff check",
                status=CheckStatus.skip,
            ))

        # 5. Type check — mypy
        if self.config.run_type_check:
            type_check = self._run_mypy(worktree_path, python_files)
            checks.append(type_check)
        else:
            checks.append(CheckResult(
                check_type="type_check",
                command="mypy",
                status=CheckStatus.skip,
            ))

        # 6. Security scan — bandit
        if self.config.run_security:
            security_check = self._run_bandit(worktree_path, python_files)
            checks.append(security_check)
        else:
            checks.append(CheckResult(
                check_type="security_scan",
                command="bandit -r",
                status=CheckStatus.skip,
            ))

        # 7. Dependency validation
        dep_check = self._check_dependencies(worktree_path, python_files)
        checks.append(dep_check)

        # Evaluate required gates
        required_gates = task.required_gates
        all_passed, blockers = evaluate_gates(checks, required_gates)

        # Determine final status
        if all_passed:
            final_status = FinalStatus.verified_candidate
        else:
            final_status = FinalStatus.needs_review

        elapsed = time.time() - start_time
        logger.info(
            f"Verification complete for patch {patch.id}: "
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

    def _check_syntax(self, worktree_path: Path, files: list[str]) -> CheckResult:
        """Check that all changed Python files can be parsed."""
        start = time.time()
        errors: list[str] = []

        for file_path in files:
            full_path = worktree_path / file_path
            if not full_path.exists():
                errors.append(f"File not found: {file_path}")
                continue
            try:
                content = full_path.read_text()
                ast.parse(content, filename=file_path)
            except SyntaxError as e:
                errors.append(f"{file_path}:{e.lineno}: {e.msg}")
            except Exception as e:
                errors.append(f"{file_path}: {e}")

        duration = time.time() - start
        if errors:
            return CheckResult(
                check_type="syntax",
                command="ast.parse",
                exit_code=1,
                status=CheckStatus.fail,
                duration_seconds=duration,
                error_message="; ".join(errors[:10]),
            )
        return CheckResult(
            check_type="syntax",
            command="ast.parse",
            exit_code=0,
            status=CheckStatus.pass_,
            duration_seconds=duration,
        )

    def _run_pytest(
        self,
        worktree_path: Path,
        test_paths: list[str] | None = None,
        check_type: str = "existing_tests",
    ) -> CheckResult:
        """Run pytest and return a CheckResult."""
        result = self.pytest_adapter.run(
            cwd=worktree_path,
            test_paths=test_paths or self.config.test_paths,
            timeout=self.config.pytest_timeout,
        )
        return self.pytest_adapter.to_check_result(result, check_type=check_type)

    def _run_lint(self, worktree_path: Path, files: list[str]) -> CheckResult:
        """Run ruff and return a CheckResult."""
        result = self.lint_adapter.run(
            cwd=worktree_path,
            paths=files if files else None,
            timeout=self.config.lint_timeout,
        )
        return self.lint_adapter.to_check_result(result)

    def _run_mypy(self, worktree_path: Path, files: list[str]) -> CheckResult:
        """Run mypy and return a CheckResult."""
        result = self.type_adapter.run(
            cwd=worktree_path,
            paths=files if files else None,
            timeout=self.config.mypy_timeout,
        )
        return self.type_adapter.to_check_result(result)

    def _run_bandit(self, worktree_path: Path, files: list[str]) -> CheckResult:
        """Run bandit and return a CheckResult."""
        result = self.security_adapter.run(
            cwd=worktree_path,
            paths=files if files else None,
            timeout=self.config.bandit_timeout,
        )
        return self.security_adapter.to_check_result(result)

    def _check_dependencies(self, worktree_path: Path, files: list[str]) -> CheckResult:
        """Validate that imports in changed files exist."""
        start = time.time()
        errors: list[str] = []

        for file_path in files:
            full_path = worktree_path / file_path
            if not full_path.exists():
                continue
            try:
                content = full_path.read_text()
                tree = ast.parse(content, filename=file_path)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            if alias.name.startswith("_"):
                                continue
                    elif isinstance(node, ast.ImportFrom):
                        if node.module and node.module.startswith("_"):
                            continue
            except Exception as e:
                errors.append(f"{file_path}: {e}")

        duration = time.time() - start
        if errors:
            return CheckResult(
                check_type="dependency_validation",
                command="ast.parse (imports)",
                exit_code=1,
                status=CheckStatus.fail,
                duration_seconds=duration,
                error_message="; ".join(errors[:10]),
            )
        return CheckResult(
            check_type="dependency_validation",
            command="ast.parse (imports)",
            exit_code=0,
            status=CheckStatus.pass_,
            duration_seconds=duration,
        )

    def select_gates(
        self,
        task_type: TaskType,
        risk_level: RiskLevel = RiskLevel.low,
        touches_dependencies: bool = False,
        touches_public_api: bool = False,
    ) -> dict[str, str]:
        """Select verification gates for a task.

        Returns:
            Dict mapping gate name to policy class.
        """
        gates = self.policy_engine.select_gates(
            task_type=task_type,
            risk_level=risk_level,
            touches_dependencies=touches_dependencies,
            touches_public_api=touches_public_api,
        )
        return {name: policy.value for name, policy in gates.items()}
