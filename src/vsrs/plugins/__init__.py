"""Plugin system for VSRS.

Provides base classes and registry for extensible plugins:
- VerifierPlugin: Custom verification checks
- RetrieverPlugin: Custom evidence retrieval strategies
- CriticPlugin: Custom critic review checks

Plugins can be discovered via Python entry points or registered manually.
Built-in example plugins are available in vsrs.plugins.builtin.
"""

from __future__ import annotations

from vsrs.plugins.base import (
    CriticPlugin,
    Plugin,
    PluginInfo,
    PluginType,
    RetrieverPlugin,
    VerifierPlugin,
)
from vsrs.plugins.builtin import (
    FileSizeVerifier,
    GitLogRetriever,
    ImportCheckerVerifier,
    MinimalityCritic,
    SecurityCritic,
)
from vsrs.plugins.registry import PluginRegistry, get_registry, register_builtins

__all__ = [
    "CriticPlugin",
    "FileSizeVerifier",
    "GitLogRetriever",
    "ImportCheckerVerifier",
    "MinimalityCritic",
    "Plugin",
    "PluginInfo",
    "PluginRegistry",
    "PluginType",
    "RetrieverPlugin",
    "SecurityCritic",
    "VerifierPlugin",
    "get_registry",
    "register_builtins",
]
