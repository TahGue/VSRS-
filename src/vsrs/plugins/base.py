"""Base classes for VSRS plugins.

All plugins inherit from `Plugin` and implement the `run` method.
Plugin types are identified by the `PluginType` enum.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from vsrs.core.schemas import CheckResult, PatchCandidate, Task
from vsrs.repo.retrieval import RetrievalResult


class PluginType(str, Enum):
    """Types of VSRS plugins."""

    verifier = "verifier"
    retriever = "retriever"
    critic = "critic"


@dataclass
class PluginInfo:
    """Metadata about a plugin."""

    name: str
    version: str
    plugin_type: PluginType
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)


class Plugin(ABC):
    """Base class for all VSRS plugins.

    Subclasses must implement:
    - `info`: Return PluginInfo metadata
    - `run`: Execute the plugin's logic
    """

    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Return plugin metadata."""
        ...

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """Execute the plugin's logic.

        Args and return type depend on the plugin type.
        """
        ...


class VerifierPlugin(Plugin):
    """Base class for custom verification plugins.

    A verifier plugin runs a specific check on a patch candidate and
    returns a CheckResult. This allows extending the verification
    pipeline with custom checks beyond the built-in gates.
    """

    @abstractmethod
    def run(
        self,
        patch: PatchCandidate,
        repo_path: str,
        **kwargs: Any,
    ) -> CheckResult:
        """Run a verification check on a patch.

        Args:
            patch: The patch candidate to verify.
            repo_path: Path to the repository (or sandbox worktree).
            **kwargs: Additional plugin-specific options.

        Returns:
            CheckResult with the outcome of the verification check.
        """
        ...


class RetrieverPlugin(Plugin):
    """Base class for custom retriever plugins.

    A retriever plugin implements an alternative evidence retrieval
    strategy. It takes a task and returns a RetrievalResult with
    evidence items relevant to the task.
    """

    @abstractmethod
    def run(
        self,
        task: Task,
        repo_path: str,
        **kwargs: Any,
    ) -> RetrievalResult:
        """Retrieve evidence for a task.

        Args:
            task: The task to retrieve evidence for.
            repo_path: Path to the repository.
            **kwargs: Additional plugin-specific options.

        Returns:
            RetrievalResult with retrieved evidence items.
        """
        ...


class CriticPlugin(Plugin):
    """Base class for custom critic plugins.

    A critic plugin implements a domain-specific review check. It takes
    a patch and verification report and returns a list of findings.
    """

    @abstractmethod
    def run(
        self,
        patch: PatchCandidate,
        verification_passed: bool,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Run a critic review check on a patch.

        Args:
            patch: The patch candidate to review.
            verification_passed: Whether the patch passed verification.
            **kwargs: Additional plugin-specific options.

        Returns:
            List of finding dicts with keys: severity, category, text.
        """
        ...
