"""Tests for LLM integration: cost tracking, client, prompts, reasoners (Phase 14)."""

import json
from typing import Any

import pytest

from vsrs.core.schemas import RiskLevel, Task, TaskType
from vsrs.llm import (
    CostTracker,
    LLMReasoner,
    LLMRepairReasoner,
    LLMResponse,
    StubClient,
    TokenUsage,
    create_client,
    extract_json,
    format_evidence_for_prompt,
    get_system_prompt,
    parse_reasoning_output,
    parse_repair_output,
    parse_structured_output,
    render_reasoning_prompt,
    render_repair_prompt,
)
from vsrs.reasoning.protocol import (
    FailureSummary,
    ParsedTask,
    PatchProposal,
    ReasoningOutput,
    RepairInput,
    RepairOutput,
)
from vsrs.repo.retrieval import RetrievalResult, RetrievedEvidence


# --- Helpers ---

def _make_task() -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=TaskType.bugfix,
        instruction="Fix the empty password bug in validate_password",
        acceptance_criteria=["empty password must be rejected"],
        risk_level=RiskLevel.low,
    )


def _make_retrieval_result() -> RetrievalResult:
    evidence = [
        RetrievedEvidence(
            kind="symbol",
            locator="src/auth.py:10",
            content="def validate_password(pw: str) -> bool:\n    return bool(pw)",
            source="symbol_index",
            metadata={"name": "validate_password", "qualified_name": "auth.validate_password"},
        ),
    ]
    return RetrievalResult(query="validate_password", evidence=evidence)


def _make_reasoning_json() -> str:
    return json.dumps({
        "parsed_task": {
            "expected_behavior": "Reject empty passwords",
            "constraints": [],
            "acceptance_criteria": ["empty password must be rejected"],
            "risk_level": "low",
            "risk_factors": [],
            "task_type": "bugfix",
            "affected_areas": ["src/auth.py"],
        },
        "evidence_summary": {
            "relevant_symbols": ["auth.validate_password"],
            "relevant_files": ["src/auth.py"],
            "relevant_tests": [],
            "relevant_configs": [],
            "key_observations": ["validate_password returns bool(pw)"],
            "evidence_locators": ["src/auth.py:10"],
        },
        "hypothesis": {
            "statement": "validate_password does not check for empty string",
            "supporting_evidence": ["src/auth.py:10"],
            "unknowns": [],
            "confidence": "inferred_supported",
        },
        "predicted_effects": {
            "files_to_change": ["src/auth.py"],
            "symbols_to_change": ["validate_password"],
            "new_symbols": [],
            "behavior_changes": ["Empty password returns False"],
            "behavior_preserved": ["Non-empty passwords still return True"],
            "side_effects": [],
        },
        "falsification_plan": {
            "checks": ["Test empty password returns False"],
            "new_tests_needed": ["test_empty_password_rejected"],
            "existing_tests_to_run": ["test_valid_password"],
            "edge_cases": ["None input"],
        },
        "patch_proposal": {
            "diff": "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,2 +1,3 @@\n def validate_password(pw):\n-    return bool(pw)\n+    if not pw:\n+        return False\n+    return bool(pw)\n",
            "changed_files": ["src/auth.py"],
            "changed_symbols": ["validate_password"],
            "new_files": [],
            "new_tests": [],
            "rationale": "Add empty string check before bool conversion",
            "assumptions": ["Empty string is the only edge case"],
        },
        "evidence_contract_refs": [],
    })


def _make_repair_json() -> str:
    return json.dumps({
        "patch_proposal": {
            "diff": "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,3 +1,4 @@\n def validate_password(pw):\n-    if not pw:\n-        return False\n+    if pw is None or pw == '':\n+        return False\n+    return bool(pw)\n",
            "changed_files": ["src/auth.py"],
            "changed_symbols": ["validate_password"],
            "new_files": [],
            "new_tests": [],
            "rationale": "Handle both None and empty string",
            "assumptions": ["None input should also be rejected"],
        },
        "failure_analysis": "Prior patch only checked falsy values, not None specifically",
        "revised_assumptions": ["None input should also be rejected"],
        "new_evidence_needed": [],
    })


# --- Cost Tracking Tests ---

class TestTokenUsage:
    def test_basic(self):
        usage = TokenUsage(model="gpt-4o", input_tokens=1000, output_tokens=500)
        assert usage.total_tokens == 1500
        assert usage.cost() > 0

    def test_stub_model_zero_cost(self):
        usage = TokenUsage(model="stub", input_tokens=1000, output_tokens=500)
        assert usage.cost() == 0.0

    def test_unknown_model_zero_cost(self):
        usage = TokenUsage(model="unknown-model", input_tokens=1000, output_tokens=500)
        assert usage.cost() == 0.0


class TestCostTracker:
    def test_record_call(self):
        tracker = CostTracker()
        usage = tracker.record_call("gpt-4o", 1000, 500)
        assert usage.input_tokens == 1000
        assert tracker.call_count == 1
        assert tracker.total_tokens == 1500

    def test_total_cost(self):
        tracker = CostTracker()
        tracker.record_call("gpt-4o", 1000, 500)
        tracker.record_call("gpt-4o-mini", 2000, 1000)
        assert tracker.total_cost > 0
        assert tracker.call_count == 2

    def test_cost_by_model(self):
        tracker = CostTracker()
        tracker.record_call("gpt-4o", 1000, 500)
        tracker.record_call("gpt-4o-mini", 2000, 1000)
        tracker.record_call("gpt-4o", 500, 200)
        breakdown = tracker.cost_by_model()
        assert "gpt-4o" in breakdown
        assert "gpt-4o-mini" in breakdown
        assert breakdown["gpt-4o"]["calls"] == 2
        assert breakdown["gpt-4o-mini"]["calls"] == 1

    def test_summary(self):
        tracker = CostTracker()
        tracker.record_call("gpt-4o", 1000, 500)
        text = tracker.summary()
        assert "Total calls: 1" in text
        assert "Total cost:" in text

    def test_to_dict(self):
        tracker = CostTracker()
        tracker.record_call("gpt-4o", 1000, 500)
        d = tracker.to_dict()
        assert d["call_count"] == 1
        assert d["total_tokens"] == 1500
        assert "by_model" in d
        assert "usages" in d

    def test_reset(self):
        tracker = CostTracker()
        tracker.record_call("gpt-4o", 100, 50)
        tracker.reset()
        assert tracker.call_count == 0
        assert tracker.total_tokens == 0

    def test_set_pricing(self):
        tracker = CostTracker()
        tracker.set_pricing("custom-model", 5.0, 20.0)
        tracker.record_call("custom-model", 1_000_000, 1_000_000)
        assert tracker.total_cost == 25.0

    def test_empty_tracker(self):
        tracker = CostTracker()
        assert tracker.total_cost == 0.0
        assert tracker.call_count == 0
        assert tracker.total_tokens == 0


# --- Client Tests ---

class TestStubClient:
    def test_echo_response(self):
        client = StubClient()
        resp = client.complete("Hello, world")
        assert resp.text == "Hello, world"
        assert resp.model == "stub"
        assert resp.input_tokens > 0
        assert resp.output_tokens > 0

    def test_fixed_response(self):
        client = StubClient(response="Fixed response")
        resp = client.complete("Hello")
        assert resp.text == "Fixed response"

    def test_set_response(self):
        client = StubClient()
        client.set_response("Custom response")
        resp = client.complete("Hello")
        assert resp.text == "Custom response"

    def test_cost_tracking(self):
        tracker = CostTracker()
        client = StubClient(cost_tracker=tracker)
        client.complete("Hello, world")
        assert tracker.call_count == 1

    def test_system_prompt(self):
        client = StubClient()
        resp = client.complete("Hello", system="You are a test assistant")
        assert resp.input_tokens > 0


class TestCreateClient:
    def test_create_stub(self):
        client = create_client("stub")
        assert isinstance(client, StubClient)

    def test_create_stub_with_model(self):
        client = create_client("stub", model="test-model")
        assert client.model == "test-model"

    def test_create_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_client("unknown")


# --- Prompt Tests ---

class TestPrompts:
    def test_render_reasoning_prompt(self):
        prompt = render_reasoning_prompt(
            instruction="Fix a bug",
            acceptance_criteria=["test passes"],
            evidence_text="evidence here",
        )
        assert "Fix a bug" in prompt
        assert "test passes" in prompt
        assert "evidence here" in prompt
        assert "JSON" in prompt

    def test_render_repair_prompt(self):
        repair_input = RepairInput(
            task_instruction="Fix a bug",
            prior_patch_diff="--- a/f.py\n+++ b/f.py\n",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="test",
                    status="fail",
                    error_category="test_failure",
                    error_message="test failed",
                    failed_test_names=["test_foo"],
                ),
            ],
            prior_assumptions=["assumption1"],
            remaining_attempts=2,
        )
        prompt = render_repair_prompt(repair_input)
        assert "Fix a bug" in prompt
        assert "test_failure" in prompt
        assert "assumption1" in prompt

    def test_extract_json_plain(self):
        text = '{"key": "value"}'
        result = extract_json(text)
        assert json.loads(result)["key"] == "value"

    def test_extract_json_code_fence(self):
        text = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        result = extract_json(text)
        assert json.loads(result)["key"] == "value"

    def test_extract_json_code_fence_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        result = extract_json(text)
        assert json.loads(result)["key"] == "value"

    def test_extract_json_with_prefix(self):
        text = 'Here is the result:\n{"key": "value"}'
        result = extract_json(text)
        assert json.loads(result)["key"] == "value"

    def test_extract_json_nested(self):
        text = '{"outer": {"inner": "value"}, "list": [1, 2, 3]}'
        result = extract_json(text)
        data = json.loads(result)
        assert data["outer"]["inner"] == "value"

    def test_extract_json_no_json(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            extract_json("just text, no json")

    def test_parse_structured_output(self):
        text = '{"expected_behavior": "test", "constraints": []}'
        result = parse_structured_output(text, ParsedTask)
        assert result.expected_behavior == "test"

    def test_parse_reasoning_output(self):
        text = _make_reasoning_json()
        result = parse_reasoning_output(text)
        assert isinstance(result, ReasoningOutput)
        assert result.hypothesis.statement == "validate_password does not check for empty string"
        assert result.patch_proposal.diff.startswith("--- a/src/auth.py")

    def test_parse_repair_output(self):
        text = _make_repair_json()
        result = parse_repair_output(text)
        assert isinstance(result, RepairOutput)
        assert "Prior patch" in result.failure_analysis

    def test_format_evidence_empty(self):
        text = format_evidence_for_prompt([])
        assert "no evidence" in text

    def test_format_evidence_with_items(self):
        items = [
            {"type": "structural", "locator": "src/auth.py:10", "content": "def foo(): pass"},
            {"type": "test", "locator": "tests/test_auth.py:5", "content": "def test_foo(): pass"},
        ]
        text = format_evidence_for_prompt(items)
        assert "src/auth.py:10" in text
        assert "tests/test_auth.py:5" in text

    def test_format_evidence_truncation(self):
        items = [{"type": "structural", "locator": "f.py", "content": "x" * 1000}]
        text = format_evidence_for_prompt(items, max_content_length=50)
        assert "..." in text

    def test_format_evidence_max_items(self):
        items = [{"type": "x", "locator": f"f{i}.py", "content": "x"} for i in range(30)]
        text = format_evidence_for_prompt(items, max_items=5)
        assert "more items" in text

    def test_get_system_prompt(self):
        prompt = get_system_prompt()
        assert "verified software reasoning system" in prompt
        assert "JSON" in prompt


# --- LLM Reasoner Tests ---

class TestLLMReasoner:
    def test_fallback_when_no_client(self):
        reasoner = LLMReasoner(client=None)
        task = _make_task()
        retrieval = _make_retrieval_result()
        output = reasoner.reason(task, retrieval)
        assert isinstance(output, ReasoningOutput)
        # Deterministic reasoner produces empty diff
        assert output.patch_proposal.diff == ""

    def test_llm_reasoning_success(self):
        reasoning_json = _make_reasoning_json()
        client = StubClient(response=reasoning_json)
        reasoner = LLMReasoner(client=client)
        task = _make_task()
        retrieval = _make_retrieval_result()
        output = reasoner.reason(task, retrieval)
        assert isinstance(output, ReasoningOutput)
        assert output.patch_proposal.diff.startswith("--- a/src/auth.py")
        assert output.hypothesis.statement == "validate_password does not check for empty string"

    def test_llm_reasoning_fallback_on_parse_error(self):
        client = StubClient(response="not valid json at all")
        reasoner = LLMReasoner(client=client)
        task = _make_task()
        retrieval = _make_retrieval_result()
        output = reasoner.reason(task, retrieval)
        assert isinstance(output, ReasoningOutput)
        # Should fall back to deterministic (empty diff)
        assert output.patch_proposal.diff == ""

    def test_llm_reasoning_with_cost_tracker(self):
        reasoning_json = _make_reasoning_json()
        tracker = CostTracker()
        client = StubClient(response=reasoning_json, cost_tracker=tracker)
        reasoner = LLMReasoner(client=client, cost_tracker=tracker)
        task = _make_task()
        retrieval = _make_retrieval_result()
        reasoner.reason(task, retrieval)
        assert tracker.call_count == 1


class TestLLMRepairReasoner:
    def _make_repair_input(self) -> RepairInput:
        return RepairInput(
            task_instruction="Fix the empty password bug",
            prior_patch_diff="--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,2 +1,2 @@\n def validate_password(pw):\n-    return bool(pw)\n+    if not pw: return False\n+    return bool(pw)\n",
            prior_attempt_no=1,
            failures=[
                FailureSummary(
                    check_type="test",
                    status="fail",
                    error_category="test_failure",
                    error_message="test_none_input fails with AttributeError",
                    failed_test_names=["test_none_input"],
                ),
            ],
            prior_assumptions=["Empty string is the only edge case"],
            remaining_attempts=2,
        )

    def test_fallback_when_no_client(self):
        reasoner = LLMRepairReasoner(client=None)
        repair_input = self._make_repair_input()
        output = reasoner.repair(repair_input)
        assert isinstance(output, RepairOutput)
        # Deterministic repair produces empty diff
        assert output.patch_proposal.diff == ""

    def test_llm_repair_success(self):
        repair_json = _make_repair_json()
        client = StubClient(response=repair_json)
        reasoner = LLMRepairReasoner(client=client)
        repair_input = self._make_repair_input()
        output = reasoner.repair(repair_input)
        assert isinstance(output, RepairOutput)
        assert output.patch_proposal.diff.startswith("--- a/src/auth.py")
        assert "Prior patch" in output.failure_analysis

    def test_llm_repair_fallback_on_parse_error(self):
        client = StubClient(response="invalid json {{{")
        reasoner = LLMRepairReasoner(client=client)
        repair_input = self._make_repair_input()
        output = reasoner.repair(repair_input)
        assert isinstance(output, RepairOutput)
        # Should fall back to deterministic (empty diff)
        assert output.patch_proposal.diff == ""

    def test_llm_repair_with_cost_tracker(self):
        repair_json = _make_repair_json()
        tracker = CostTracker()
        client = StubClient(response=repair_json, cost_tracker=tracker)
        reasoner = LLMRepairReasoner(client=client, cost_tracker=tracker)
        repair_input = self._make_repair_input()
        reasoner.repair(repair_input)
        assert tracker.call_count == 1
