"""Append-only event log for task runs.

Every state change, tool call, evidence retrieval, and verification result
is recorded as an immutable event. This provides full traceability (P9)
and reproducibility (Section 11.2).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from vsrs.core.ids import generate_id
from vsrs.core.schemas import RunEvent, TaskState


class EventLog:
    """In-memory append-only event log for a single run.

    Events are never overwritten or deleted. The log can be iterated,
    filtered by event type, and exported for persistence.
    """

    def __init__(self, run_id: str, task_id: str) -> None:
        self.run_id = run_id
        self.task_id = task_id
        self._events: list[RunEvent] = []

    def record(
        self,
        state: TaskState,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> RunEvent:
        """Record a new event. Returns the created event."""
        event = RunEvent(
            id=generate_id("evt"),
            run_id=self.run_id,
            task_id=self.task_id,
            state=state,
            event_type=event_type,
            payload=payload or {},
        )
        self._events.append(event)
        return event

    def record_state_change(
        self,
        from_state: TaskState,
        to_state: TaskState,
    ) -> RunEvent:
        """Record a state transition event."""
        return self.record(
            state=to_state,
            event_type="state_change",
            payload={"from": from_state.value, "to": to_state.value},
        )

    def record_tool_call(
        self,
        state: TaskState,
        tool_name: str,
        command: str,
        exit_code: int | None = None,
        duration_seconds: float = 0.0,
        output_summary: str = "",
    ) -> RunEvent:
        """Record a tool execution event."""
        return self.record(
            state=state,
            event_type="tool_call",
            payload={
                "tool": tool_name,
                "command": command,
                "exit_code": exit_code,
                "duration_seconds": duration_seconds,
                "output_summary": output_summary,
            },
        )

    def record_evidence(
        self,
        state: TaskState,
        evidence_id: str,
        evidence_type: str,
        locator: str,
    ) -> RunEvent:
        """Record an evidence retrieval event."""
        return self.record(
            state=state,
            event_type="evidence_retrieved",
            payload={
                "evidence_id": evidence_id,
                "evidence_type": evidence_type,
                "locator": locator,
            },
        )

    def __iter__(self) -> Iterator[RunEvent]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def filter(self, event_type: str) -> list[RunEvent]:
        """Get all events of a specific type."""
        return [e for e in self._events if e.event_type == event_type]

    def latest(self) -> RunEvent | None:
        """Get the most recent event."""
        return self._events[-1] if self._events else None

    def all(self) -> list[RunEvent]:
        """Get all events (immutable copy)."""
        return list(self._events)

    def to_dict_list(self) -> list[dict[str, Any]]:
        """Serialize all events to a list of dictionaries."""
        return [e.model_dump(mode="json") for e in self._events]
