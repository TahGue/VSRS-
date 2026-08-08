"""Plugin system for VSRS.

Provides base classes and registry for extensible plugins:
- VerifierPlugin: Custom verification checks
- RetrieverPlugin: Custom evidence retrieval strategies
- CriticPlugin: Custom critic review checks

Plugins can be discovered via Python entry points or registered manually.
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
from vsrs.plugins.registry import PluginRegistry, get_registry

__all__ = [
    "CriticPlugin",
    "Plugin",
    "PluginInfo",
    "PluginRegistry",
    "PluginType",
    "RetrieverPlugin",
    "VerifierPlugin",
    "get_registry",
]
