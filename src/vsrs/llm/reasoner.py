"""LLM-backed reasoner and repair reasoner.

Wraps the deterministic Reasoner and RepairReasoner with LLM integration.
When an LLM client is provided, these use the LLM to generate patches and
repair outputs. When no client is provided, they fall back to the
deterministic implementations.
"""

from __future__ import annotations

from typing import Any

from vsrs.core.logging import get_logger
from vsrs.core.schemas import EvidenceItem, PatchCandidate, RiskLevel, Task, TaskType
from vsrs.llm.client import LLMClient, LLMResponse, StubClient
from vsrs.llm.cost import CostTracker
from vsrs.llm.prompts import (
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
from vsrs.reasoning.reasoner import Reasoner
from vsrs.reasoning.task_parser import TaskParser
from vsrs.repo.retrieval import RetrievalResult
from vsrs.repair.repair_reasoner import RepairReasoner

logger = get_logger("llm.reasoner")


class LLMReasoner:
    """LLM-backed reasoning model.

    Uses an LLM client to generate structured reasoning output.
    Falls back to the deterministic Reasoner when no client is provided
    or when LLM output parsing fails.

    Args:
        client: LLM client for completions. If None, uses deterministic reasoner.
        task_parser: Task parser instance.
        cost_tracker: Optional cost tracker for usage recording.
        fallback_reasoner: Optional deterministic reasoner for fallback.
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        task_parser: TaskParser | None = None,
        cost_tracker: CostTracker | None = None,
        fallback_reasoner: Reasoner | None = None,
    ) -> None:
        self.client = client
        self.task_parser = task_parser or TaskParser()
        self.cost_tracker = cost_tracker
        self.fallback = fallback_reasoner or Reasoner(task_parser=self.task_parser)

    def reason(
        self,
        task: Task,
        retrieval_result: RetrievalResult,
        parsed_task: ParsedTask | None = None,
    ) -> ReasoningOutput:
        """Run the reasoning pipeline, using LLM if available.

        Args:
            task: The task to reason about.
            retrieval_result: Evidence retrieved from the repository.
            parsed_task: Pre-parsed task (if None, will parse).

        Returns:
            ReasoningOutput with all stages completed.
        """
        if self.client is None:
            return self.fallback.reason(task, retrieval_result, parsed_task)

        logger.info(f"LLM reasoning on task {task.id}: {task.instruction[:80]}")

        # Stage 1: Parse task (deterministic — no need for LLM)
        if parsed_task is None:
            parsed_task = self.task_parser.parse(
                instruction=task.instruction,
                acceptance_criteria=task.acceptance_criteria,
                task_type=task.type,
                risk_level=task.risk_level,
            )

        # Format evidence for prompt
        evidence_items = [
            {
                "type": ev.kind,
                "locator": ev.locator,
                "content": ev.content or "",
            }
            for ev in retrieval_result.evidence
        ]
        evidence_text = format_evidence_for_prompt(evidence_items)

        # Render prompt
        prompt = render_reasoning_prompt(
            instruction=task.instruction,
            acceptance_criteria=task.acceptance_criteria,
            evidence_text=evidence_text,
            risk_level=task.risk_level.value,
            task_type=task.type.value,
        )

        system = get_system_prompt()

        try:
            response = self.client.complete(
                prompt=prompt,
                system=system,
                max_tokens=4096,
                temperature=0.2,
            )

            output = parse_reasoning_output(response.text)

            # Override parsed_task with our deterministic parse
            output.parsed_task = parsed_task

            # Collect evidence contract refs
            output.evidence_contract_refs = [
                ev.metadata.get("name", ev.locator)
                for ev in retrieval_result.evidence
            ]

            logger.info(f"LLM reasoning succeeded for task {task.id}")
            return output

        except Exception as e:
            logger.warning(
                f"LLM reasoning failed for task {task.id}: {e}. "
                f"Falling back to deterministic reasoner."
            )
            return self.fallback.reason(task, retrieval_result, parsed_task)


class LLMRepairReasoner:
    """LLM-backed repair reasoner.

    Uses an LLM client to generate repair outputs from structured failures.
    Falls back to the deterministic RepairReasoner when no client is provided
    or when LLM output parsing fails.

    Args:
        client: LLM client for completions. If None, uses deterministic repair reasoner.
        cost_tracker: Optional cost tracker for usage recording.
        fallback: Optional deterministic repair reasoner for fallback.
    """

    def __init__(
        self,
        client: LLMClient | None = None,
        cost_tracker: CostTracker | None = None,
        fallback: RepairReasoner | None = None,
    ) -> None:
        self.client = client
        self.cost_tracker = cost_tracker
        self.fallback = fallback or RepairReasoner()

    def repair(self, repair_input: RepairInput) -> RepairOutput:
        """Produce a repair output, using LLM if available.

        Args:
            repair_input: Structured input with prior patch and failures.

        Returns:
            RepairOutput with corrected patch proposal and analysis.
        """
        if self.client is None:
            return self.fallback.repair(repair_input)

        logger.info(
            f"LLM repairing attempt {repair_input.prior_attempt_no} "
            f"with {len(repair_input.failures)} failures"
        )

        prompt = render_repair_prompt(repair_input)
        system = get_system_prompt()

        try:
            response = self.client.complete(
                prompt=prompt,
                system=system,
                max_tokens=4096,
                temperature=0.2,
            )

            output = parse_repair_output(response.text)

            logger.info("LLM repair succeeded")
            return output

        except Exception as e:
            logger.warning(
                f"LLM repair failed: {e}. "
                f"Falling back to deterministic repair reasoner."
            )
            return self.fallback.repair(repair_input)
