"""ID generation for runs, tasks, evidence items, and other entities."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def generate_id(prefix: str = "") -> str:
    """Generate a unique ID with an optional prefix.

    Format: prefix_YYYYMMDDHHMMSS_shortuuid
    Uses UUID4 hex truncated to 12 chars for compactness.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{timestamp}_{short_uuid}"
    return f"{timestamp}_{short_uuid}"


def generate_run_id() -> str:
    """Generate a run ID."""
    return generate_id("run")


def generate_task_id() -> str:
    """Generate a task ID."""
    return generate_id("task")


def generate_evidence_id() -> str:
    """Generate an evidence item ID."""
    return generate_id("ev")


def generate_patch_id() -> str:
    """Generate a patch candidate ID."""
    return generate_id("patch")


def generate_verification_id() -> str:
    """Generate a verification run ID."""
    return generate_id("verify")


def generate_hypothesis_id() -> str:
    """Generate a hypothesis ID."""
    return generate_id("hyp")


def generate_provenance_id() -> str:
    """Generate a provenance ID."""
    return generate_id("prov")


def generate_finding_id() -> str:
    """Generate a review finding ID."""
    return generate_id("finding")
