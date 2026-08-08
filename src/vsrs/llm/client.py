"""Unified LLM client interface with provider implementations.

Supports:
- OpenAI-compatible API (GPT-4o, etc.)
- Anthropic API (Claude 3.5 Sonnet, etc.)
- Stub provider for testing/offline development

All providers implement the LLMClient protocol with a single `complete` method.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from vsrs.core.logging import get_logger
from vsrs.llm.cost import CostTracker, TokenUsage

logger = get_logger("llm.client")


@dataclass
class LLMResponse:
    """Response from an LLM completion."""

    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM completion clients."""

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a completion for the given prompt.

        Args:
            prompt: The user prompt text.
            system: Optional system prompt.
            max_tokens: Maximum output tokens.
            temperature: Sampling temperature.
            **kwargs: Provider-specific options.

        Returns:
            LLMResponse with generated text and token usage.
        """
        ...


class StubClient:
    """Deterministic stub client for testing and offline development.

    Returns a configurable response or echoes the prompt.
    """

    def __init__(
        self,
        model: str = "stub",
        response: str | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.model = model
        self._response = response
        self.cost_tracker = cost_tracker

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        text = self._response if self._response is not None else prompt
        input_tokens = len(prompt) // 4 + len(system) // 4
        output_tokens = len(text) // 4

        if self.cost_tracker:
            self.cost_tracker.record_call(self.model, input_tokens, output_tokens)

        return LLMResponse(
            text=text,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            raw={"stub": True},
        )

    def set_response(self, response: str) -> None:
        """Set a fixed response for subsequent calls."""
        self._response = response


class OpenAIClient:
    """OpenAI API client.

    Requires the `openai` package and an API key.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url
        self.cost_tracker = cost_tracker
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as e:
                raise ImportError(
                    "openai package is required. Install with: pip install openai"
                ) from e
            kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        choice = response.choices[0]
        usage = response.usage

        result = LLMResponse(
            text=choice.message.content or "",
            model=self.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            finish_reason=choice.finish_reason or "stop",
            raw=response.model_dump() if hasattr(response, "model_dump") else {},
        )

        if self.cost_tracker:
            self.cost_tracker.record_call(self.model, result.input_tokens, result.output_tokens)

        return result


class AnthropicClient:
    """Anthropic API client.

    Requires the `anthropic` package and an API key.
    """

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: str | None = None,
        base_url: str | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = base_url
        self.cost_tracker = cost_tracker
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise ImportError(
                    "anthropic package is required. Install with: pip install anthropic"
                ) from e
            kwargs: dict[str, Any] = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()

        response = client.messages.create(
            model=self.model,
            system=system if system else "You are a helpful assistant.",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        result = LLMResponse(
            text=text,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            finish_reason=response.stop_reason or "stop",
            raw={"id": response.id, "model": response.model},
        )

        if self.cost_tracker:
            self.cost_tracker.record_call(self.model, result.input_tokens, result.output_tokens)

        return result


class LMStudioClient:
    """LM Studio client using OpenAI-compatible API.

    LM Studio runs a local server at http://localhost:1234/v1 that is
    fully OpenAI API compatible. This client wraps OpenAIClient with
    sensible defaults and auto-detection of loaded models.

    Requires the `openai` package (pip install openai).
    """

    DEFAULT_BASE_URL = "http://localhost:1234/v1"
    DEFAULT_MODEL = "local-model"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str = "lm-studio",
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self.base_url = base_url or os.environ.get(
            "LMSTUDIO_BASE_URL", self.DEFAULT_BASE_URL
        )
        self.cost_tracker = cost_tracker
        self._model = model
        self._client = OpenAIClient(
            model=model or self.DEFAULT_MODEL,
            api_key=api_key,
            base_url=self.base_url,
            cost_tracker=cost_tracker,
        )

    @property
    def model(self) -> str:
        return self._client.model

    def list_models(self) -> list[str]:
        """List available models from LM Studio."""
        try:
            from openai import OpenAI
        except ImportError:
            return []
        client = OpenAI(api_key="lm-studio", base_url=self.base_url)
        try:
            models = client.models.list()
            return [m.id for m in models.data]
        except Exception:
            return []

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.2,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generate a completion via LM Studio."""
        if self._model is None:
            models = self.list_models()
            if models:
                self._client.model = models[0]
                logger.info(f"LM Studio auto-selected model: {models[0]}")
        return self._client.complete(
            prompt, system=system, max_tokens=max_tokens,
            temperature=temperature, **kwargs,
        )


def create_client(
    provider: str = "stub",
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    cost_tracker: CostTracker | None = None,
) -> LLMClient:
    """Factory function to create an LLM client by provider name.

    Args:
        provider: One of 'stub', 'openai', 'anthropic', 'lmstudio'.
        model: Model name. Defaults to provider's default.
        api_key: API key. Falls back to environment variable.
        base_url: Optional base URL override.
        cost_tracker: Optional cost tracker for usage recording.

    Returns:
        An LLMClient instance.
    """
    if provider == "stub":
        return StubClient(model=model or "stub", cost_tracker=cost_tracker)
    elif provider == "openai":
        return OpenAIClient(
            model=model or "gpt-4o",
            api_key=api_key,
            base_url=base_url,
            cost_tracker=cost_tracker,
        )
    elif provider == "anthropic":
        return AnthropicClient(
            model=model or "claude-3-5-sonnet-20241022",
            api_key=api_key,
            base_url=base_url,
            cost_tracker=cost_tracker,
        )
    elif provider == "lmstudio":
        return LMStudioClient(
            model=model,
            base_url=base_url,
            cost_tracker=cost_tracker,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            "Use 'stub', 'openai', 'anthropic', or 'lmstudio'."
        )
