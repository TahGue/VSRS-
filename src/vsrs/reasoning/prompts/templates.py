"""Prompt templates for reasoning protocol stages (Section 7.1).

Provides structured prompt templates for each reasoning stage. In V1,
these are used for documentation and will be integrated with LLM calls
in later phases.
"""

from __future__ import annotations

from string import Template

# System prompt establishing the reasoning contract
SYSTEM_PROMPT = """\
You are a verified software reasoning system. You must produce structured \
JSON output following the reasoning protocol. Every important claim must be \
grounded in evidence from the repository or tested against executable evidence.

You must NOT:
- Invent file paths, symbol names, or APIs that do not exist in the repository
- Claim a patch works without verification
- Skip the falsification step
- Produce changes beyond what the task requires (minimality)

You MUST:
- Ground every claim in evidence locators (file:line)
- State assumptions explicitly
- Predict effects and side effects
- Define falsification checks before producing a patch
- Keep changes minimal and explainable
"""

# Stage 1: Task parsing prompt
TASK_PARSE_PROMPT = Template("""\
## Task
$instruction

## Pre-defined acceptance criteria
$criteria

## Instructions
Parse the task description and extract:
1. Expected behavior: What should the code do after the change?
2. Constraints: Technical or domain constraints
3. Acceptance criteria: Observable conditions that must be true
4. Risk level: low, medium, or high (with factors)
5. Task type: bugfix, feature, refactor, test, security, or migration
6. Affected areas: Likely affected modules/files/symbols

Respond as JSON matching the ParsedTask schema.
""")

# Stage 2: Evidence gathering prompt
EVIDENCE_GATHER_PROMPT = Template("""\
## Task
$instruction

## Retrieved Evidence
$evidence

## Instructions
Summarize the evidence relevant to this task:
1. Which symbols are relevant?
2. Which files are relevant?
3. Which tests are relevant?
4. What are the key observations from the evidence?

Respond as JSON matching the EvidenceSummary schema.
""")

# Stage 3: Hypothesis prompt
HYPOTHESIS_PROMPT = Template("""\
## Task
$instruction

## Parsed Task
$parsed_task

## Evidence Summary
$evidence_summary

## Instructions
Form a hypothesis about the cause (for bugfix) or required implementation \
strategy (for feature/refactor). Include:
1. A clear statement of the hypothesis
2. Supporting evidence locators
3. Unknowns that remain to be resolved
4. Confidence level: observed_true, inferred_supported, unknown, or conflicted

Respond as JSON matching the ReasoningHypothesis schema.
""")

# Stage 4: Predict effects prompt
PREDICT_EFFECTS_PROMPT = Template("""\
## Task
$instruction

## Hypothesis
$hypothesis

## Evidence Summary
$evidence_summary

## Instructions
Predict the effects of the change:
1. Which files and symbols will be modified?
2. What behavior will change?
3. What behavior must be preserved?
4. What side effects should we watch for?

Respond as JSON matching the PredictedEffects schema.
""")

# Stage 5: Falsification plan prompt
FALSIFICATION_PROMPT = Template("""\
## Task
$instruction

## Predicted Effects
$predicted_effects

## Acceptance Criteria
$criteria

## Instructions
Define a falsification plan:
1. What checks would prove the patch wrong?
2. What new tests need to be written?
3. What existing tests must still pass?
4. What edge cases should be considered?

Respond as JSON matching the FalsificationPlan schema.
""")

# Stage 6: Patch proposal prompt
PATCH_PROPOSAL_PROMPT = Template("""\
## Task
$instruction

## Evidence
$evidence

## Hypothesis
$hypothesis

## Predicted Effects
$predicted_effects

## Falsification Plan
$falsification_plan

## Instructions
Produce a minimal patch as a unified diff that addresses the task. The patch must:
1. Be a valid unified diff that applies cleanly
2. Change only what is necessary (minimality)
3. Not introduce symbols or imports that don't exist in the repository
4. Include any new tests needed for falsification

Respond as JSON matching the PatchProposal schema.
""")

# Repair prompt (for Phase 5)
REPAIR_PROMPT = Template("""\
## Task
$instruction

## Prior Patch (attempt $attempt_no)
```diff
$prior_diff
```

## Failure Summary
$failures

## Prior Assumptions
$assumptions

## Remaining attempts: $remaining

## Instructions
The prior patch failed. Analyze the failures and produce a corrected patch.
1. Why did the prior patch fail?
2. What needs to change?
3. Are there new unknowns or evidence needed?

Respond as JSON matching the RepairOutput schema.
""")


def format_evidence(evidence_items: list[dict]) -> str:
    """Format evidence items for inclusion in prompts."""
    lines: list[str] = []
    for item in evidence_items:
        locator = item.get("locator", "")
        kind = item.get("kind", "")
        content = item.get("content", "")[:500]
        lines.append(f"### {kind} at {locator}\n```\n{content}\n```")
    return "\n\n".join(lines)


def format_failures(failures: list[dict]) -> str:
    """Format failure summaries for repair prompts."""
    lines: list[str] = []
    for f in failures:
        check_type = f.get("check_type", "")
        status = f.get("status", "")
        category = f.get("error_category", "")
        message = f.get("error_message", "")
        lines.append(f"- [{check_type}] {status}: {category} — {message}")
    return "\n".join(lines)
