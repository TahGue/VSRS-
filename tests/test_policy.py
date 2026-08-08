"""Tests for the policy engine (Phase 1)."""

from vsrs.core.policy import GatePolicyEngine
from vsrs.core.schemas import GatePolicy, RiskLevel, TaskType


class TestGatePolicyEngine:
    def test_base_mandatory_gates(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(TaskType.bugfix, RiskLevel.low)
        assert gates["syntax"] == GatePolicy.mandatory
        assert gates["build"] == GatePolicy.mandatory
        assert gates["existing_tests"] == GatePolicy.mandatory

    def test_bugfix_extra_gates(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(TaskType.bugfix, RiskLevel.low)
        assert gates["new_targeted_tests"] == GatePolicy.mandatory

    def test_security_task_gates(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(TaskType.security, RiskLevel.high)
        assert gates["security_scan"] == GatePolicy.mandatory
        assert gates["static_analysis"] == GatePolicy.mandatory

    def test_risk_level_adds_gates(self):
        engine = GatePolicyEngine()
        low = engine.select_gates(TaskType.feature, RiskLevel.low)
        high = engine.select_gates(TaskType.feature, RiskLevel.high)
        assert "static_analysis" not in engine.required_gates(low)
        assert "static_analysis" in engine.required_gates(high)
        assert "security_scan" in engine.required_gates(high)

    def test_dependency_gates(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(
            TaskType.feature, RiskLevel.low, touches_dependencies=True
        )
        assert gates["dependency_validation"] == GatePolicy.mandatory

    def test_api_compatibility_gates(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(
            TaskType.refactor, RiskLevel.low, touches_public_api=True
        )
        assert gates["api_compatibility"] == GatePolicy.mandatory

    def test_performance_gates(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(
            TaskType.feature, RiskLevel.low, has_perf_requirement=True
        )
        assert gates["performance_benchmark"] == GatePolicy.mandatory

    def test_required_vs_optional(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(TaskType.bugfix, RiskLevel.low)
        required = engine.required_gates(gates)
        optional = engine.optional_gates(gates)
        assert "syntax" in required
        assert "build" in required
        assert "existing_tests" in required
        # Optional gates should not be in required
        for gate in optional:
            assert gate not in required

    def test_gate_description(self):
        desc = GatePolicyEngine.gate_description("syntax")
        assert "parsed" in desc.lower()

    def test_migration_gates(self):
        engine = GatePolicyEngine()
        gates = engine.select_gates(TaskType.migration, RiskLevel.medium)
        assert gates["migration_check"] == GatePolicy.mandatory
