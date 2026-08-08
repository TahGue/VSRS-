"""LLM integration package: client, cost tracking, prompt rendering, reasoners."""

from vsrs.llm.client import (
    AnthropicClient,
    LLMClient,
    LLMResponse,
    OpenAIClient,
    StubClient,
    create_client,
)
from vsrs.llm.cost import CostTracker, TokenUsage
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
from vsrs.llm.reasoner import LLMReasoner, LLMRepairReasoner

__all__ = [
    "AnthropicClient",
    "CostTracker",
    "LLMClient",
    "LLMReasoner",
    "LLMRepairReasoner",
    "LLMResponse",
    "OpenAIClient",
    "StubClient",
    "TokenUsage",
    "create_client",
    "extract_json",
    "format_evidence_for_prompt",
    "get_system_prompt",
    "parse_reasoning_output",
    "parse_repair_output",
    "parse_structured_output",
    "render_reasoning_prompt",
    "render_repair_prompt",
]
