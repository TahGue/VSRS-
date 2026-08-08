"""Cost tracking for LLM API calls.

Tracks token usage and estimated costs across all LLM calls in a session.
Supports per-model pricing with configurable rates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Default pricing per 1M tokens (in USD)
# Updated to reflect typical pricing as of 2024-2025
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
    "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    # Local models are free
    "local": {"input": 0.0, "output": 0.0},
    "stub": {"input": 0.0, "output": 0.0},
}


@dataclass
class TokenUsage:
    """Token usage for a single LLM call."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def cost(self, pricing: dict[str, dict[str, float]] | None = None) -> float:
        """Estimate the cost in USD.

        Args:
            pricing: Optional pricing override. Uses DEFAULT_PRICING if None.

        Returns:
            Estimated cost in USD.
        """
        rates = (pricing or DEFAULT_PRICING).get(self.model, {"input": 0.0, "output": 0.0})
        input_cost = (self.input_tokens / 1_000_000) * rates.get("input", 0.0)
        output_cost = (self.output_tokens / 1_000_000) * rates.get("output", 0.0)
        return round(input_cost + output_cost, 6)


@dataclass
class CostTracker:
    """Tracks cumulative token usage and cost across multiple LLM calls."""

    usages: list[TokenUsage] = field(default_factory=list)
    _pricing: dict[str, dict[str, float]] = field(default_factory=lambda: dict(DEFAULT_PRICING))

    def record(self, usage: TokenUsage) -> None:
        """Record a token usage entry."""
        self.usages.append(usage)

    def record_call(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> TokenUsage:
        """Record a call and return the usage entry."""
        usage = TokenUsage(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self.usages.append(usage)
        return usage

    @property
    def total_input_tokens(self) -> int:
        return sum(u.input_tokens for u in self.usages)

    @property
    def total_output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usages)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cost(self) -> float:
        return round(sum(u.cost(self._pricing) for u in self.usages), 6)

    @property
    def call_count(self) -> int:
        return len(self.usages)

    def cost_by_model(self) -> dict[str, dict[str, Any]]:
        """Break down cost by model.

        Returns:
            Dict mapping model name to {calls, input_tokens, output_tokens, cost}.
        """
        breakdown: dict[str, dict[str, Any]] = {}
        for u in self.usages:
            if u.model not in breakdown:
                breakdown[u.model] = {
                    "calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": 0.0,
                }
            breakdown[u.model]["calls"] += 1
            breakdown[u.model]["input_tokens"] += u.input_tokens
            breakdown[u.model]["output_tokens"] += u.output_tokens
            breakdown[u.model]["cost"] = round(
                breakdown[u.model]["cost"] + u.cost(self._pricing), 6
            )
        return breakdown

    def summary(self) -> str:
        """Generate a text summary of costs."""
        lines = [
            f"Total calls: {self.call_count}",
            f"Total input tokens: {self.total_input_tokens:,}",
            f"Total output tokens: {self.total_output_tokens:,}",
            f"Total tokens: {self.total_tokens:,}",
            f"Total cost: ${self.total_cost:.4f}",
        ]
        if self.call_count > 0:
            lines.append(f"Avg cost per call: ${self.total_cost / self.call_count:.4f}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "call_count": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "by_model": self.cost_by_model(),
            "usages": [
                {
                    "model": u.model,
                    "input_tokens": u.input_tokens,
                    "output_tokens": u.output_tokens,
                    "cost": u.cost(self._pricing),
                }
                for u in self.usages
            ],
        }

    def reset(self) -> None:
        """Clear all recorded usages."""
        self.usages.clear()

    def set_pricing(self, model: str, input_per_million: float, output_per_million: float) -> None:
        """Set custom pricing for a model."""
        self._pricing[model] = {"input": input_per_million, "output": output_per_million}
