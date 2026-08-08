"""Gate policy: task/risk profile selects required checks (Section 8.1).

Uses the GatePolicyEngine from core.policy.
"""

from __future__ import annotations

from vsrs.core.policy import GatePolicyEngine
from vsrs.core.schemas import CheckResult, CheckStatus, RiskLevel, TaskType

# Re-export for convenience
__all__ = ["GatePolicyEngine", "evaluate_gates"]


def evaluate_gates(
    checks: list[CheckResult],
    required_gate_names: list[str],
) -> tuple[bool, list[str]]:
    """Evaluate whether all required gates pass.

    Args:
        checks: List of check results.
        required_gate_names: Names of gates that must pass.

    Returns:
        (all_required_passed, blockers) tuple.
    """
    check_by_type = {c.check_type: c for c in checks}
    blockers: list[str] = []

    for gate_name in required_gate_names:
        check = check_by_type.get(gate_name)
        if check is None:
            blockers.append(f"Required gate '{gate_name}' was not run")
        elif check.status != CheckStatus.pass_:
            blockers.append(
                f"Required gate '{gate_name}' failed (exit={check.exit_code}): "
                f"{check.error_message or check.output_ref}"
            )

    all_passed = len(blockers) == 0
    return all_passed, blockers
