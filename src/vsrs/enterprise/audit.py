"""Audit logging for enterprise compliance.

Records all significant actions for compliance, debugging, and
security analysis. Supports filtering, export, and retention policies.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from vsrs.core.logging import get_logger

logger = get_logger("enterprise.audit")


class AuditEventType(str, Enum):
    """Types of audit events."""

    auth_login = "auth:login"
    auth_logout = "auth:logout"
    auth_key_create = "auth:key_create"
    auth_key_revoke = "auth:key_revoke"
    auth_key_validate = "auth:key_validate"

    task_create = "task:create"
    task_update = "task:update"
    task_delete = "task:delete"

    verify_run = "verify:run"
    repair_run = "repair:run"
    benchmark_run = "benchmark:run"

    admin_config_change = "admin:config_change"
    admin_user_create = "admin:user_create"
    admin_user_delete = "admin:user_delete"

    rate_limit_hit = "rate_limit:hit"
    permission_denied = "permission:denied"


@dataclass
class AuditEvent:
    """A single audit event.

    Attributes:
        timestamp: When the event occurred.
        event_type: Type of event.
        user_id: ID of the user who triggered the event.
        resource: Resource affected (e.g. task ID, key ID).
        action: Action performed.
        success: Whether the action succeeded.
        details: Additional event-specific data.
        ip_address: Optional IP address of the requester.
        request_id: Optional request/correlation ID.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    user_id: str = ""
    resource: str = ""
    action: str = ""
    success: bool = True
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "user_id": self.user_id,
            "resource": self.resource,
            "action": self.action,
            "success": self.success,
            "details": self.details,
            "ip_address": self.ip_address,
            "request_id": self.request_id,
        }

    def to_jsonl(self) -> str:
        """Serialize to a single JSONL line."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Logs audit events to memory and optionally to file.

    Args:
        log_file: Optional path to append audit events as JSONL.
        max_events: Maximum events to keep in memory (0 = unlimited).
    """

    def __init__(
        self,
        log_file: str | Path | None = None,
        max_events: int = 10000,
    ) -> None:
        self.log_file = Path(log_file) if log_file else None
        self.max_events = max_events
        self._events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        """Record an audit event.

        Args:
            event: The event to record.
        """
        self._events.append(event)

        # Enforce max events (keep most recent)
        if self.max_events > 0 and len(self._events) > self.max_events:
            self._events = self._events[-self.max_events:]

        # Write to file if configured
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a") as f:
                f.write(event.to_jsonl() + "\n")

        logger.debug(
            f"Audit: {event.event_type} user={event.user_id} "
            f"resource={event.resource} success={event.success}"
        )

    def log_event(
        self,
        event_type: str | AuditEventType,
        user_id: str = "",
        resource: str = "",
        action: str = "",
        success: bool = True,
        details: dict[str, Any] | None = None,
        ip_address: str = "",
        request_id: str = "",
    ) -> AuditEvent:
        """Convenience method to create and log an event.

        Returns:
            The created AuditEvent.
        """
        event = AuditEvent(
            event_type=event_type.value if isinstance(event_type, AuditEventType) else event_type,
            user_id=user_id,
            resource=resource,
            action=action,
            success=success,
            details=details or {},
            ip_address=ip_address,
            request_id=request_id,
        )
        self.log(event)
        return event

    def query(
        self,
        event_type: str | None = None,
        user_id: str | None = None,
        resource: str | None = None,
        success: bool | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Query audit events with filters.

        Args:
            event_type: Filter by event type.
            user_id: Filter by user ID.
            resource: Filter by resource.
            success: Filter by success status.
            start_time: Filter events after this time.
            end_time: Filter events before this time.
            limit: Maximum number of events to return.

        Returns:
            List of matching events (most recent first).
        """
        results = list(self._events)

        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        if user_id is not None:
            results = [e for e in results if e.user_id == user_id]
        if resource is not None:
            results = [e for e in results if e.resource == resource]
        if success is not None:
            results = [e for e in results if e.success == success]
        if start_time is not None:
            results = [e for e in results if e.timestamp >= start_time]
        if end_time is not None:
            results = [e for e in results if e.timestamp <= end_time]

        # Most recent first
        results.reverse()
        return results[:limit]

    def count(self) -> int:
        """Get total number of logged events."""
        return len(self._events)

    def clear(self) -> None:
        """Clear all events from memory."""
        self._events.clear()

    def export_jsonl(self, path: str | Path) -> int:
        """Export all events to a JSONL file.

        Returns:
            Number of events exported.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for event in self._events:
                f.write(event.to_jsonl() + "\n")
        return len(self._events)
