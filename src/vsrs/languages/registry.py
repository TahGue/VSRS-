"""Language registry for multi-language support.

Manages language adapter registration, detection, and lookup.
Determines which language adapter to use based on repository contents
or changed file extensions.
"""

from __future__ import annotations

from pathlib import Path

from vsrs.core.logging import get_logger
from vsrs.languages.base import LanguageAdapter

logger = get_logger("languages.registry")


class LanguageRegistry:
    """Registry for language adapters.

    Supports:
    - Manual registration via register()
    - Language detection by repository contents
    - Language detection by file extensions
    - Lookup by name
    """

    def __init__(self) -> None:
        self._adapters: dict[str, LanguageAdapter] = {}

    def register(self, adapter: LanguageAdapter) -> None:
        """Register a language adapter.

        Args:
            adapter: The language adapter to register.

        Raises:
            ValueError: If an adapter with the same name is already registered.
        """
        name = adapter.info.name
        if name in self._adapters:
            raise ValueError(f"Language '{name}' is already registered")
        self._adapters[name] = adapter
        logger.info(f"Registered language adapter: {name}")

    def unregister(self, name: str) -> LanguageAdapter | None:
        """Unregister a language adapter by name."""
        adapter = self._adapters.pop(name, None)
        if adapter:
            logger.info(f"Unregistered language adapter: {name}")
        return adapter

    def get(self, name: str) -> LanguageAdapter | None:
        """Get a language adapter by name."""
        return self._adapters.get(name)

    def all(self) -> dict[str, LanguageAdapter]:
        """Get all registered language adapters."""
        return dict(self._adapters)

    def names(self) -> list[str]:
        """Get all registered language names."""
        return list(self._adapters.keys())

    def count(self) -> int:
        """Get the number of registered languages."""
        return len(self._adapters)

    def clear(self) -> None:
        """Remove all registered adapters."""
        self._adapters.clear()

    def detect_for_repo(self, repo_path: Path) -> list[LanguageAdapter]:
        """Detect which languages are used in a repository.

        Args:
            repo_path: Path to the repository root.

        Returns:
            List of language adapters for languages detected in the repo.
        """
        detected: list[LanguageAdapter] = []
        for adapter in self._adapters.values():
            try:
                if adapter.detect(repo_path):
                    detected.append(adapter)
            except Exception as e:
                logger.warning(f"Error detecting {adapter.info.name}: {e}")
        return detected

    def detect_for_files(self, files: list[str]) -> list[LanguageAdapter]:
        """Detect which languages are needed for a set of files.

        Args:
            files: List of file paths.

        Returns:
            List of language adapters that match the given files.
        """
        detected: list[LanguageAdapter] = []
        for adapter in self._adapters.values():
            if adapter.matches_files(files):
                detected.append(adapter)
        return detected

    def get_adapter_for_file(self, file_path: str) -> LanguageAdapter | None:
        """Get the language adapter for a specific file.

        Args:
            file_path: A file path.

        Returns:
            The matching language adapter, or None if no match.
        """
        for adapter in self._adapters.values():
            if adapter.matches_files([file_path]):
                return adapter
        return None


# Global registry singleton
_registry: LanguageRegistry | None = None


def get_registry() -> LanguageRegistry:
    """Get the global language registry singleton.

    Returns:
        The shared LanguageRegistry instance with all built-in adapters registered.
    """
    global _registry
    if _registry is None:
        _registry = LanguageRegistry()
        _register_builtins(_registry)
    return _registry


def _register_builtins(reg: LanguageRegistry) -> None:
    """Register all built-in language adapters."""
    from vsrs.languages.go import GoAdapter
    from vsrs.languages.java import JavaAdapter
    from vsrs.languages.python import PythonAdapter
    from vsrs.languages.rust import RustAdapter
    from vsrs.languages.typescript import TypeScriptAdapter

    for adapter_cls in [PythonAdapter, GoAdapter, RustAdapter, TypeScriptAdapter, JavaAdapter]:
        adapter = adapter_cls()
        if adapter.info.name not in reg.all():
            reg.register(adapter)


def detect_language(repo_path: Path | str) -> list[LanguageAdapter]:
    """Detect languages in a repository using the global registry.

    Args:
        repo_path: Path to the repository root.

        Returns:
        List of language adapters for detected languages.
    """
    return get_registry().detect_for_repo(Path(repo_path))
