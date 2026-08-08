"""Policy engine for task routing and verification gate selection.

Implements Section 8: task-specific verification profiles and gate logic.
The policy engine selects mandatory and optional gates based on task type
and risk level.
"""

from __future__ import annotations

from vsrs.core.schemas import GatePolicy, RiskLevel, TaskType


# Gate definitions: gate_name -> (description, default_policy)
GATE_DEFINITIONS: dict[str, tuple[str, GatePolicy]] = {
    "syntax": ("Can changed files be parsed?", GatePolicy.mandatory),
    "build": ("Does the project or affected target build?", GatePolicy.mandatory_when_applicable),
    "existing_tests": ("Do unchanged expectations still pass?", GatePolicy.mandatory),
    "new_targeted_tests": ("Does the requested behavior pass?", GatePolicy.mandatory),
    "type_check": ("Are type invariants preserved?", GatePolicy.mandatory_when_applicable),
    "lint": ("Does code satisfy repository quality rules?", GatePolicy.policy_dependent),
    "static_analysis": ("Are obvious bug/security patterns introduced?", GatePolicy.risk_dependent),
    "dependency_validation": ("Are imports/versions real and permitted?", GatePolicy.mandatory),
    "security_scan": ("Secrets, injection, unsafe patterns", GatePolicy.risk_dependent),
    "api_compatibility": ("Did public contracts change?", GatePolicy.mandatory),
    "migration_check": ("Can schema/data/config migrate safely?", GatePolicy.mandatory),
    "performance_benchmark": ("Did defined latency/memory budget regress?", GatePolicy.optional),
}

# Task-specific extra required checks (Section 8.2)
TASK_EXTRA_GATES: dict[TaskType, list[str]] = {
    TaskType.bugfix: ["new_targeted_tests"],
    TaskType.feature: ["new_targeted_tests", "api_compatibility"],
    TaskType.refactor: ["api_compatibility"],
    TaskType.security: ["security_scan", "static_analysis"],
    TaskType.migration: ["migration_check"],
    TaskType.test: [],
}

# Risk-dependent gates
RISK_GATES: dict[RiskLevel, list[str]] = {
    RiskLevel.low: [],
    RiskLevel.medium: ["static_analysis"],
    RiskLevel.high: ["static_analysis", "security_scan"],
}


class GatePolicyEngine:
    """Selects verification gates based on task type and risk level."""

    def select_gates(
        self,
        task_type: TaskType,
        risk_level: RiskLevel = RiskLevel.low,
        touches_dependencies: bool = False,
        touches_public_api: bool = False,
        has_perf_requirement: bool = False,
        has_build_step: bool = True,
        has_type_checking: bool = False,
    ) -> dict[str, GatePolicy]:
        """Select required and optional gates for a task.

        Returns:
            Dict mapping gate name to its effective policy.
            Gates with mandatory policy are always required.
            Gates with mandatory_when_applicable are required if the
            corresponding condition is met.
        """
        selected: dict[str, GatePolicy] = {}

        # Base mandatory gates
        for gate_name, (_, policy) in GATE_DEFINITIONS.items():
            if policy == GatePolicy.mandatory:
                selected[gate_name] = GatePolicy.mandatory

        # Task-specific extra gates
        for gate_name in TASK_EXTRA_GATES.get(task_type, []):
            if gate_name in GATE_DEFINITIONS:
                selected[gate_name] = GatePolicy.mandatory

        # Risk-dependent gates
        for gate_name in RISK_GATES.get(risk_level, []):
            if gate_name in GATE_DEFINITIONS:
                selected[gate_name] = GatePolicy.mandatory

        # Conditional mandatory gates
        if touches_dependencies:
            selected["dependency_validation"] = GatePolicy.mandatory
        if touches_public_api:
            selected["api_compatibility"] = GatePolicy.mandatory
        if has_perf_requirement:
            selected["performance_benchmark"] = GatePolicy.mandatory

        # Promote mandatory_when_applicable gates to mandatory when conditions are met
        if has_build_step:
            selected["build"] = GatePolicy.mandatory
        if has_type_checking:
            selected["type_check"] = GatePolicy.mandatory

        # Add applicable gates that aren't mandatory
        for gate_name, (_, policy) in GATE_DEFINITIONS.items():
            if gate_name not in selected:
                if policy == GatePolicy.mandatory_when_applicable:
                    selected[gate_name] = GatePolicy.optional
                elif policy in (GatePolicy.policy_dependent, GatePolicy.risk_dependent, GatePolicy.optional):
                    selected[gate_name] = GatePolicy.optional

        return selected

    def required_gates(self, gates: dict[str, GatePolicy]) -> list[str]:
        """Filter to only mandatory gates."""
        return sorted(name for name, policy in gates.items() if policy == GatePolicy.mandatory)

    def optional_gates(self, gates: dict[str, GatePolicy]) -> list[str]:
        """Filter to only optional gates."""
        return sorted(name for name, policy in gates.items() if policy != GatePolicy.mandatory)

    @staticmethod
    def gate_description(gate_name: str) -> str:
        """Get the description for a gate."""
        if gate_name in GATE_DEFINITIONS:
            return GATE_DEFINITIONS[gate_name][0]
        return f"Unknown gate: {gate_name}"
