"""Prompt rendering and structured output parsing for LLM integration.

Renders prompts from templates with task/evidence context and parses
LLM responses into validated Pydantic models (ReasoningOutput, RepairOutput).

Handles:
- System prompt construction
- Reasoning prompt rendering (stages 1-6)
- Repair prompt rendering
- JSON extraction from LLM responses (handles markdown code fences)
- Pydantic validation with error reporting
- Retry logic for malformed output
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from vsrs.core.logging import get_logger
from vsrs.reasoning.prompts.templates import SYSTEM_PROMPT
from vsrs.reasoning.protocol import (
    EvidenceSummary,
    FalsificationPlan,
    PatchProposal,
    ParsedTask,
    PredictedEffects,
    ReasoningHypothesis,
    ReasoningOutput,
    RepairInput,
    RepairOutput,
)

logger = get_logger("llm.prompts")

T = TypeVar("T", bound=BaseModel)


def render_reasoning_prompt(
    instruction: str,
    acceptance_criteria: list[str],
    evidence_text: str,
    risk_level: str = "low",
    task_type: str = "bugfix",
) -> str:
    """Render the full reasoning prompt for the LLM.

    Combines all 6 stages into a single prompt that asks the model to
    produce a complete ReasoningOutput as JSON.

    Args:
        instruction: The task instruction.
        acceptance_criteria: List of acceptance criteria.
        evidence_text: Pre-formatted evidence context.
        risk_level: Assessed risk level.
        task_type: Task type (bugfix, feature, etc.).

    Returns:
        The rendered prompt string.
    """
    criteria_text = "\n".join(f"- {c}" for c in acceptance_criteria) or "- (none specified)"

    return f"""\
## Task
{instruction}

## Acceptance Criteria
{criteria_text}

## Risk Level
{risk_level}

## Task Type
{task_type}

## Retrieved Evidence
{evidence_text}

## Instructions
You must produce a complete reasoning output as JSON matching the ReasoningOutput schema.
The JSON must contain these fields:

1. **parsed_task**: Parse the task into expected_behavior, constraints, acceptance_criteria, risk_level, risk_factors, task_type, affected_areas
2. **evidence_summary**: Summarize relevant_symbols, relevant_files, relevant_tests, relevant_configs, key_observations, evidence_locators
3. **hypothesis**: State the hypothesis with statement, supporting_evidence (locators), unknowns, confidence (observed_true|inferred_supported|unknown|conflicted)
4. **predicted_effects**: List files_to_change, symbols_to_change, new_symbols, behavior_changes, behavior_preserved, side_effects
5. **falsification_plan**: Define checks, new_tests_needed, existing_tests_to_run, edge_cases
6. **patch_proposal**: Produce a unified diff with changed_files, changed_symbols, new_files, new_tests, rationale, assumptions

Respond with ONLY the JSON object, no markdown formatting or explanation.
"""


def render_repair_prompt(
    repair_input: RepairInput,
    evidence_text: str = "",
) -> str:
    """Render the repair prompt for the LLM.

    Args:
        repair_input: The structured repair input with prior patch and failures.
        evidence_text: Optional additional evidence context.

    Returns:
        The rendered prompt string.
    """
    failures_text = "\n".join(
        f"- [{f.error_category}] {f.error_message}"
        + (f" (test: {', '.join(f.failed_test_names)})" if f.failed_test_names else "")
        + (f" at {f.relevant_file}:{f.relevant_line}" if f.relevant_file else "")
        for f in repair_input.failures
    ) or "- (no specific failures categorized)"

    assumptions_text = "\n".join(f"- {a}" for a in repair_input.prior_assumptions) or "- (none)"

    return f"""\
## Task
{repair_input.task_instruction}

## Prior Patch (attempt {repair_input.prior_attempt_no})
```diff
{repair_input.prior_patch_diff}
```

## Failures
{failures_text}

## Prior Assumptions
{assumptions_text}

## Remaining Attempts
{repair_input.remaining_attempts}

## Additional Evidence
{evidence_text or "(none)"}

## Instructions
Analyze why the prior patch failed and produce a corrected patch as JSON matching the RepairOutput schema.
The JSON must contain:

1. **patch_proposal**: A corrected unified diff with changed_files, changed_symbols, new_files, new_tests, rationale, assumptions
2. **failure_analysis**: Explanation of why the prior patch failed
3. **revised_assumptions**: Updated assumptions list
4. **new_evidence_needed**: Any new evidence that should be retrieved

Respond with ONLY the JSON object, no markdown formatting or explanation.
"""


def extract_json(text: str) -> str:
    """Extract JSON from an LLM response.

    Handles:
    - Plain JSON
    - JSON wrapped in ```json ... ``` code fences
    - JSON with leading/trailing text

    Args:
        text: Raw LLM response text.

    Returns:
        Extracted JSON string.

    Raises:
        ValueError: If no valid JSON block is found.
    """
    # Try to find ```json ... ``` block
    json_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_block:
        return json_block.group(1).strip()

    # Try to find the first { ... } block
    # Find the first opening brace
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")

    # Find the matching closing brace by counting depth
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1].strip()

    # If no matching brace, try the whole thing from start
    return text[start:].strip()


def parse_structured_output(
    text: str,
    model_class: type[T],
) -> T:
    """Parse an LLM response into a validated Pydantic model.

    Args:
        text: Raw LLM response text.
        model_class: The Pydantic model class to validate against.

    Returns:
        Validated model instance.

    Raises:
        ValueError: If JSON extraction fails.
        ValidationError: If Pydantic validation fails.
    """
    json_str = extract_json(text)
    data = json.loads(json_str)
    return model_class.model_validate(data)


def _preprocess_reasoning_data(data: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM output issues before Pydantic validation.

    Handles:
    - String fields that should be lists (constraints, risk_factors, etc.)
    - Missing diff in patch_proposal (construct from changed_files/new content)
    - Missing rationale in patch_proposal
    - Missing required fields with sensible defaults
    """
    # Fix parsed_task: ensure list fields are lists
    pt = data.get("parsed_task", {})
    if isinstance(pt, dict):
        for key in ("constraints", "acceptance_criteria", "risk_factors", "affected_areas"):
            if key in pt and isinstance(pt[key], str):
                pt[key] = [pt[key]]
        data["parsed_task"] = pt

    # Fix evidence_summary: ensure list fields are lists
    es = data.get("evidence_summary", {})
    if isinstance(es, dict):
        for key in ("relevant_symbols", "relevant_files", "relevant_tests",
                     "relevant_configs", "key_observations", "evidence_locators"):
            if key in es and isinstance(es[key], str):
                es[key] = [es[key]]
        data["evidence_summary"] = es

    # Fix predicted_effects: ensure list fields are lists
    pe = data.get("predicted_effects", {})
    if isinstance(pe, dict):
        for key in ("files_to_change", "symbols_to_change", "new_symbols",
                     "behavior_changes", "behavior_preserved", "side_effects"):
            if key in pe and isinstance(pe[key], str):
                pe[key] = [pe[key]]
        data["predicted_effects"] = pe

    # Fix falsification_plan: ensure list fields are lists
    fp = data.get("falsification_plan", {})
    if isinstance(fp, dict):
        for key in ("checks", "new_tests_needed", "existing_tests_to_run", "edge_cases"):
            if key in fp and isinstance(fp[key], str):
                fp[key] = [fp[key]]
        data["falsification_plan"] = fp

    # Fix patch_proposal: ensure diff exists, list fields are lists
    pp = data.get("patch_proposal", {})
    if isinstance(pp, dict):
        for key in ("changed_files", "changed_symbols", "new_files", "new_tests", "assumptions"):
            if key in pp and isinstance(pp[key], str):
                pp[key] = [pp[key]]

        # If diff is missing, try to construct from new_content or code fields
        if "diff" not in pp or not pp.get("diff"):
            # Check for alternative field names LLMs might use
            diff = pp.get("diff", "") or pp.get("unified_diff", "") or pp.get("patch", "")
            if not diff:
                # Try to construct from new_content/code fields
                for file_key in ("new_content", "code", "content", "file_content"):
                    if file_key in pp and pp[file_key]:
                        changed = pp.get("changed_files", ["unknown"])
                        fname = changed[0] if isinstance(changed, list) and changed else "unknown"
                        new_content = pp[file_key]
                        if isinstance(new_content, dict):
                            # might be {filename: content}
                            for fn, content in new_content.items():
                                diff += f"--- a/{fn}\n+++ b/{fn}\n@@ -0,0 +1,{content.count(chr(10))+1} @@\n"
                                for line in content.split("\n"):
                                    diff += f"+{line}\n"
                        elif isinstance(new_content, str):
                            diff += f"--- a/{fname}\n+++ b/{fname}\n"
                            for line in new_content.split("\n"):
                                diff += f"+{line}\n"
                        break
            pp["diff"] = diff or ""

        # Ensure rationale exists
        if "rationale" not in pp or not pp.get("rationale"):
            pp["rationale"] = pp.get("rationale", "") or pp.get("explanation", "") or "LLM-generated patch"

        data["patch_proposal"] = pp

    return data


def parse_reasoning_output(text: str) -> ReasoningOutput:
    """Parse an LLM response into a ReasoningOutput.

    Args:
        text: Raw LLM response text.

    Returns:
        Validated ReasoningOutput.

    Raises:
        ValueError: If JSON extraction or parsing fails.
        ValidationError: If validation fails.
    """
    json_str = extract_json(text)
    data = json.loads(json_str)
    data = _preprocess_reasoning_data(data)
    return ReasoningOutput.model_validate(data)


def parse_repair_output(text: str) -> RepairOutput:
    """Parse an LLM response into a RepairOutput.

    Args:
        text: Raw LLM response text.

    Returns:
        Validated RepairOutput.

    Raises:
        ValueError: If JSON extraction or parsing fails.
        ValidationError: If validation fails.
    """
    return parse_structured_output(text, RepairOutput)


def format_evidence_for_prompt(
    evidence_items: list[dict[str, Any]],
    max_items: int = 20,
    max_content_length: int = 500,
) -> str:
    """Format evidence items into a text block for the prompt.

    Args:
        evidence_items: List of evidence item dicts (from store or trajectory).
        max_items: Maximum number of items to include.
        max_content_length: Truncate content to this length.

    Returns:
        Formatted evidence text.
    """
    if not evidence_items:
        return "(no evidence retrieved)"

    lines = []
    for i, item in enumerate(evidence_items[:max_items]):
        ev_type = item.get("type", "unknown")
        locator = item.get("locator", "unknown")
        content = item.get("content", "")
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        lines.append(f"[{i + 1}] ({ev_type}) {locator}\n    {content}")

    if len(evidence_items) > max_items:
        lines.append(f"\n... and {len(evidence_items) - max_items} more items")

    return "\n".join(lines)


def get_system_prompt() -> str:
    """Get the system prompt for reasoning tasks."""
    return SYSTEM_PROMPT
