"""WebSocket manager for real-time run progress streaming.

Provides a pub/sub system where clients can subscribe to run updates
and receive events as they happen during the VSRS pipeline.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from vsrs.core.logging import get_logger

logger = get_logger("api.websocket")


class ConnectionManager:
    """Manages WebSocket connections grouped by run_id.

    Each run has a set of subscriber connections. When an event is
    published for a run, all subscribers receive it as JSON.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[Any]] = {}
        self._event_history: dict[str, list[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, run_id: str, websocket: Any) -> None:
        """Accept a WebSocket connection and subscribe it to a run."""
        await websocket.accept()
        async with self._lock:
            if run_id not in self._connections:
                self._connections[run_id] = set()
            self._connections[run_id].add(websocket)
        logger.info(
            "WebSocket connected",
            extra={"run_id": run_id, "subscribers": len(self._connections.get(run_id, set()))},
        )

        history = self._event_history.get(run_id, [])
        for event in history:
            await websocket.send_text(json.dumps(event))

    async def disconnect(self, run_id: str, websocket: Any) -> None:
        """Remove a WebSocket connection from a run's subscribers."""
        async with self._lock:
            if run_id in self._connections:
                self._connections[run_id].discard(websocket)
                if not self._connections[run_id]:
                    del self._connections[run_id]
        logger.info(
            "WebSocket disconnected",
            extra={"run_id": run_id, "subscribers": len(self._connections.get(run_id, set()))},
        )

    async def broadcast(self, run_id: str, event: dict[str, Any]) -> None:
        """Send an event to all subscribers of a run."""
        event_with_ts = {
            **event,
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        async with self._lock:
            if run_id not in self._event_history:
                self._event_history[run_id] = []
            self._event_history[run_id].append(event_with_ts)

            subscribers = list(self._connections.get(run_id, set()))

        disconnected: list[Any] = []
        for ws in subscribers:
            try:
                await ws.send_text(json.dumps(event_with_ts))
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            await self.disconnect(run_id, ws)

    async def publish_state_change(
        self,
        run_id: str,
        from_state: str,
        to_state: str,
        attempt_no: int = 1,
    ) -> None:
        """Publish a state transition event."""
        await self.broadcast(run_id, {
            "type": "state_change",
            "from_state": from_state,
            "to_state": to_state,
            "attempt_no": attempt_no,
        })

    async def publish_tool_call(
        self,
        run_id: str,
        tool: str,
        command: str,
        exit_code: int | None = None,
        duration_seconds: float = 0.0,
        status: str = "running",
    ) -> None:
        """Publish a tool execution event."""
        await self.broadcast(run_id, {
            "type": "tool_call",
            "tool": tool,
            "command": command,
            "exit_code": exit_code,
            "duration_seconds": duration_seconds,
            "status": status,
        })

    async def publish_verification_result(
        self,
        run_id: str,
        check_type: str,
        passed: bool,
        duration_seconds: float = 0.0,
        error_message: str = "",
    ) -> None:
        """Publish a verification check result."""
        await self.broadcast(run_id, {
            "type": "verification_result",
            "check_type": check_type,
            "passed": passed,
            "duration_seconds": duration_seconds,
            "error_message": error_message,
        })

    async def publish_patch(
        self,
        run_id: str,
        attempt_no: int,
        changed_files: list[str],
        diff_summary: str = "",
    ) -> None:
        """Publish a patch generation event."""
        await self.broadcast(run_id, {
            "type": "patch_generated",
            "attempt_no": attempt_no,
            "changed_files": changed_files,
            "diff_summary": diff_summary,
        })

    async def publish_review(
        self,
        run_id: str,
        decision: str,
        findings_count: int = 0,
        blockers: list[str] | None = None,
    ) -> None:
        """Publish a critic review event."""
        await self.broadcast(run_id, {
            "type": "review_complete",
            "decision": decision,
            "findings_count": findings_count,
            "blockers": blockers or [],
        })

    async def publish_completion(
        self,
        run_id: str,
        final_state: str,
        attempts: int = 1,
    ) -> None:
        """Publish a run completion event."""
        await self.broadcast(run_id, {
            "type": "run_complete",
            "final_state": final_state,
            "attempts": attempts,
        })

    def get_subscriber_count(self, run_id: str) -> int:
        """Get the number of active subscribers for a run."""
        return len(self._connections.get(run_id, set()))

    def get_event_history(self, run_id: str) -> list[dict[str, Any]]:
        """Get the event history for a run."""
        return list(self._event_history.get(run_id, []))

    def clear_history(self, run_id: str) -> None:
        """Clear event history for a run."""
        self._event_history.pop(run_id, None)


manager = ConnectionManager()
