"""Evidence model: evidence types, states, and contracts (Section 5).

Core types are defined in vsrs.core.schemas.
This module provides evidence-building utilities.

TODO: Phase 2-6 - evidence collection and validation utilities.
"""

from __future__ import annotations

from vsrs.core.ids import generate_evidence_id
from vsrs.core.schemas import EvidenceItem, EvidenceState, EvidenceType
from vsrs.verify.sandbox import Sandbox


def create_structural_evidence(
    source: str,
    locator: str,
    content: str,
    state: EvidenceState = EvidenceState.observed_true,
) -> EvidenceItem:
    """Create a structural evidence item (AST, symbols, types)."""
    return EvidenceItem(
        id=generate_evidence_id(),
        type=EvidenceType.structural,
        source=source,
        locator=locator,
        content=content,
        content_hash=Sandbox.hash_content(content),
        state=state,
    )


def create_executable_evidence(
    source: str,
    locator: str,
    content: str,
    state: EvidenceState = EvidenceState.observed_true,
) -> EvidenceItem:
    """Create an executable evidence item (test pass/fail, build, runtime)."""
    return EvidenceItem(
        id=generate_evidence_id(),
        type=EvidenceType.executable,
        source=source,
        locator=locator,
        content=content,
        content_hash=Sandbox.hash_content(content),
        state=state,
    )


def create_config_evidence(
    source: str,
    locator: str,
    content: str,
    state: EvidenceState = EvidenceState.observed_true,
) -> EvidenceItem:
    """Create a configuration evidence item (lockfile, CI config, compiler flags)."""
    return EvidenceItem(
        id=generate_evidence_id(),
        type=EvidenceType.config,
        source=source,
        locator=locator,
        content=content,
        content_hash=Sandbox.hash_content(content),
        state=state,
    )


def create_historical_evidence(
    source: str,
    locator: str,
    content: str,
    state: EvidenceState = EvidenceState.inferred_supported,
) -> EvidenceItem:
    """Create a historical evidence item (merged commit, regression fix, code owner review)."""
    return EvidenceItem(
        id=generate_evidence_id(),
        type=EvidenceType.historical,
        source=source,
        locator=locator,
        content=content,
        content_hash=Sandbox.hash_content(content),
        state=state,
    )


def create_documentation_evidence(
    source: str,
    locator: str,
    content: str,
    state: EvidenceState = EvidenceState.inferred_supported,
) -> EvidenceItem:
    """Create a documentation evidence item (repo docs, ADR, official library docs)."""
    return EvidenceItem(
        id=generate_evidence_id(),
        type=EvidenceType.documentation,
        source=source,
        locator=locator,
        content=content,
        content_hash=Sandbox.hash_content(content),
        state=state,
    )


def create_inference_evidence(
    source: str,
    locator: str,
    content: str,
    state: EvidenceState = EvidenceState.unknown,
) -> EvidenceItem:
    """Create a model inference evidence item (hypothesis, analogy, design judgment)."""
    return EvidenceItem(
        id=generate_evidence_id(),
        type=EvidenceType.inference,
        source=source,
        locator=locator,
        content=content,
        content_hash=Sandbox.hash_content(content),
        state=state,
    )
