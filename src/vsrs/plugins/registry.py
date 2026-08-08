"""Plugin registry for VSRS.

Manages plugin registration, discovery, and lookup.
Supports both manual registration and entry-point discovery.
"""

from __future__ import annotations

from typing import Any

from vsrs.core.logging import get_logger
from vsrs.plugins.base import (
    CriticPlugin,
    Plugin,
    PluginInfo,
    PluginType,
    RetrieverPlugin,
    VerifierPlugin,
)

logger = get_logger("plugins.registry")


class PluginRegistry:
    """Registry for VSRS plugins.

    Supports:
    - Manual registration via register()
    - Discovery via Python entry points (importlib.metadata)
    - Lookup by name, type, or tags
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._discovered: bool = False

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance.

        Args:
            plugin: The plugin instance to register.

        Raises:
            ValueError: If a plugin with the same name is already registered.
        """
        info = plugin.info
        if info.name in self._plugins:
            raise ValueError(f"Plugin '{info.name}' is already registered")
        self._plugins[info.name] = plugin
        logger.info(f"Registered plugin: {info.name} ({info.plugin_type.value})")

    def unregister(self, name: str) -> Plugin | None:
        """Unregister a plugin by name.

        Args:
            name: The plugin name.

        Returns:
            The unregistered plugin, or None if not found.
        """
        plugin = self._plugins.pop(name, None)
        if plugin:
            logger.info(f"Unregistered plugin: {name}")
        return plugin

    def get(self, name: str) -> Plugin | None:
        """Get a plugin by name.

        Args:
            name: The plugin name.

        Returns:
            The plugin instance, or None if not found.
        """
        return self._plugins.get(name)

    def get_by_type(self, plugin_type: PluginType) -> list[Plugin]:
        """Get all plugins of a specific type.

        Args:
            plugin_type: The type of plugins to retrieve.

        Returns:
            List of plugin instances of the given type.
        """
        return [
            p for p in self._plugins.values()
            if p.info.plugin_type == plugin_type
        ]

    def get_verifiers(self) -> list[VerifierPlugin]:
        """Get all verifier plugins."""
        return [p for p in self.get_by_type(PluginType.verifier) if isinstance(p, VerifierPlugin)]

    def get_retrievers(self) -> list[RetrieverPlugin]:
        """Get all retriever plugins."""
        return [p for p in self.get_by_type(PluginType.retriever) if isinstance(p, RetrieverPlugin)]

    def get_critics(self) -> list[CriticPlugin]:
        """Get all critic plugins."""
        return [p for p in self.get_by_type(PluginType.critic) if isinstance(p, CriticPlugin)]

    def all(self) -> dict[str, Plugin]:
        """Get all registered plugins."""
        return dict(self._plugins)

    def names(self) -> list[str]:
        """Get all registered plugin names."""
        return list(self._plugins.keys())

    def count(self) -> int:
        """Get the number of registered plugins."""
        return len(self._plugins)

    def clear(self) -> None:
        """Remove all registered plugins."""
        self._plugins.clear()
        self._discovered = False

    def discover(self) -> int:
        """Discover plugins via Python entry points.

        Looks for entry points in the `vsrs.plugins` group and instantiates
        any plugins found. This uses importlib.metadata for entry point
        discovery.

        Returns:
            Number of plugins discovered and registered.
        """
        if self._discovered:
            return 0

        count = 0
        try:
            from importlib.metadata import entry_points
            eps = entry_points(group="vsrs.plugins")
            for ep in eps:
                try:
                    plugin_class = ep.load()
                    plugin = plugin_class()
                    if isinstance(plugin, Plugin):
                        if plugin.info.name not in self._plugins:
                            self._plugins[plugin.info.name] = plugin
                            count += 1
                            logger.info(f"Discovered plugin: {plugin.info.name} via entry point")
                except Exception as e:
                    logger.warning(f"Failed to load plugin from entry point {ep.name}: {e}")
        except Exception:
            # entry_points may not be available or no plugins installed
            pass

        self._discovered = True
        return count

    def info_all(self) -> list[PluginInfo]:
        """Get metadata for all registered plugins.

        Returns:
            List of PluginInfo for all plugins.
        """
        return [p.info for p in self._plugins.values()]

    def to_dict(self) -> dict[str, Any]:
        """Serialize registry state to dict."""
        return {
            "plugins": [
                {
                    "name": info.name,
                    "version": info.version,
                    "type": info.plugin_type.value,
                    "description": info.description,
                    "author": info.author,
                    "tags": info.tags,
                }
                for info in self.info_all()
            ],
            "count": self.count(),
        }


# Global registry singleton
_registry: PluginRegistry | None = None


def get_registry() -> PluginRegistry:
    """Get the global plugin registry singleton.

    Returns:
        The shared PluginRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = PluginRegistry()
    return _registry
