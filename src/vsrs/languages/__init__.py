"""Multi-language support for VSRS.

Provides language-specific adapters for syntax checking, building,
testing, linting, and type checking across multiple programming languages.
"""

from __future__ import annotations

from vsrs.languages.base import LanguageAdapter, LanguageInfo
from vsrs.languages.go import GoAdapter
from vsrs.languages.java import JavaAdapter
from vsrs.languages.python import PythonAdapter
from vsrs.languages.registry import LanguageRegistry, detect_language, get_registry
from vsrs.languages.rust import RustAdapter
from vsrs.languages.typescript import TypeScriptAdapter

__all__ = [
    "GoAdapter",
    "JavaAdapter",
    "LanguageAdapter",
    "LanguageInfo",
    "LanguageRegistry",
    "PythonAdapter",
    "RustAdapter",
    "TypeScriptAdapter",
    "detect_language",
    "get_registry",
]
