"""Dependency injection for the VSRS API."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from vsrs.core.config import VSRSConfig
from vsrs.core.store import Store


@lru_cache(maxsize=1)
def get_config() -> VSRSConfig:
    """Get the VSRS configuration (cached)."""
    config = VSRSConfig.load()
    config.ensure_dirs()
    return config


def get_store() -> Store:
    """Get a Store instance (yields, closes after use)."""
    config = get_config()
    store = Store(config.database.url)
    try:
        yield store
    finally:
        store.close()
