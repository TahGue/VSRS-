"""Tests for Phase 23: Real-time WebSocket and provenance graph viewer.

Tests the WebSocket ConnectionManager, the WebSocket endpoint in the FastAPI app,
and the new dashboard components (useWebSocket hook, LiveProgress, ProvenanceGraph).
"""

import asyncio
import json
import pytest
from pathlib import Path

from vsrs.api.app import create_app
from vsrs.api.websocket import ConnectionManager


def _run_async(coro):
    """Run an async coroutine in a synchronous test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- ConnectionManager Unit Tests ---

class TestConnectionManager:
    def test_init_empty(self):
        mgr = ConnectionManager()
        assert mgr.get_subscriber_count("run_1") == 0
        assert mgr.get_event_history("run_1") == []

    def test_broadcast_stores_history(self):
        mgr = ConnectionManager()
        _run_async(mgr.broadcast("run_1", {"type": "state_change", "from_state": "intake", "to_state": "retrieving"}))
        history = mgr.get_event_history("run_1")
        assert len(history) == 1
        assert history[0]["type"] == "state_change"
        assert history[0]["run_id"] == "run_1"
        assert "timestamp" in history[0]

    def test_broadcast_multiple_events(self):
        mgr = ConnectionManager()
        _run_async(mgr.broadcast("run_1", {"type": "state_change", "from_state": "intake", "to_state": "retrieving"}))
        _run_async(mgr.broadcast("run_1", {"type": "tool_call", "tool": "pytest", "command": "pytest"}))
        history = mgr.get_event_history("run_1")
        assert len(history) == 2
        assert history[0]["type"] == "state_change"
        assert history[1]["type"] == "tool_call"

    def test_publish_state_change(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_state_change("run_1", "intake", "retrieving"))
        history = mgr.get_event_history("run_1")
        assert len(history) == 1
        assert history[0]["type"] == "state_change"
        assert history[0]["from_state"] == "intake"
        assert history[0]["to_state"] == "retrieving"

    def test_publish_state_change_with_attempt(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_state_change("run_1", "verifying", "revising", attempt_no=2))
        history = mgr.get_event_history("run_1")
        assert history[0]["attempt_no"] == 2

    def test_publish_tool_call(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_tool_call("run_1", "pytest", "pytest -xvs", exit_code=0, duration_seconds=1.5))
        history = mgr.get_event_history("run_1")
        assert history[0]["type"] == "tool_call"
        assert history[0]["tool"] == "pytest"
        assert history[0]["exit_code"] == 0
        assert history[0]["duration_seconds"] == 1.5

    def test_publish_verification_result(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_verification_result("run_1", "syntax", True, 0.1))
        history = mgr.get_event_history("run_1")
        assert history[0]["type"] == "verification_result"
        assert history[0]["check_type"] == "syntax"
        assert history[0]["passed"] is True

    def test_publish_verification_result_failed(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_verification_result("run_1", "existing_tests", False, 2.3, "2 tests failed"))
        history = mgr.get_event_history("run_1")
        assert history[0]["passed"] is False
        assert history[0]["error_message"] == "2 tests failed"

    def test_publish_patch(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_patch("run_1", 1, ["src/main.py", "src/utils.py"], "2 files changed"))
        history = mgr.get_event_history("run_1")
        assert history[0]["type"] == "patch_generated"
        assert history[0]["attempt_no"] == 1
        assert "src/main.py" in history[0]["changed_files"]

    def test_publish_review(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_review("run_1", "verified", findings_count=2, blockers=[]))
        history = mgr.get_event_history("run_1")
        assert history[0]["type"] == "review_complete"
        assert history[0]["decision"] == "verified"
        assert history[0]["findings_count"] == 2

    def test_publish_review_with_blockers(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_review("run_1", "rejected", findings_count=3, blockers=["syntax_error", "test_failure"]))
        history = mgr.get_event_history("run_1")
        assert history[0]["decision"] == "rejected"
        assert "syntax_error" in history[0]["blockers"]

    def test_publish_completion(self):
        mgr = ConnectionManager()
        _run_async(mgr.publish_completion("run_1", "verified", attempts=2))
        history = mgr.get_event_history("run_1")
        assert history[0]["type"] == "run_complete"
        assert history[0]["final_state"] == "verified"
        assert history[0]["attempts"] == 2

    def test_clear_history(self):
        mgr = ConnectionManager()
        _run_async(mgr.broadcast("run_1", {"type": "test"}))
        assert len(mgr.get_event_history("run_1")) == 1
        mgr.clear_history("run_1")
        assert len(mgr.get_event_history("run_1")) == 0

    def test_separate_runs(self):
        mgr = ConnectionManager()
        _run_async(mgr.broadcast("run_1", {"type": "event_a"}))
        _run_async(mgr.broadcast("run_2", {"type": "event_b"}))
        assert len(mgr.get_event_history("run_1")) == 1
        assert len(mgr.get_event_history("run_2")) == 1
        assert mgr.get_event_history("run_1")[0]["type"] == "event_a"
        assert mgr.get_event_history("run_2")[0]["type"] == "event_b"

    def test_broadcast_no_subscribers(self):
        """Broadcasting with no subscribers should not error."""
        mgr = ConnectionManager()
        _run_async(mgr.broadcast("run_1", {"type": "test"}))
        assert mgr.get_subscriber_count("run_1") == 0


# --- WebSocket Endpoint Tests ---

class TestWebSocketEndpoint:
    @pytest.fixture
    def app(self):
        return create_app()

    def test_app_has_websocket_route(self, app):
        """Verify the WebSocket route is registered."""
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        assert any("/ws/runs/" in r for r in routes)

    def test_websocket_route_pattern(self, app):
        """Verify the WebSocket route pattern matches /ws/runs/{run_id}."""
        ws_routes = [r for r in app.routes if hasattr(r, 'path') and '/ws/runs/' in r.path]
        assert len(ws_routes) >= 1


# --- Dashboard Component File Tests ---

class TestDashboardComponents:
    def test_use_websocket_hook_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "useWebSocket.ts").exists()

    def test_use_websocket_has_hook(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "useWebSocket.ts").read_text()
        assert "useRunWebSocket" in content
        assert "WebSocket" in content
        assert "WSEvent" in content

    def test_live_progress_component_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "components" / "LiveProgress.tsx").exists()

    def test_live_progress_has_pipeline_stages(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "components" / "LiveProgress.tsx").read_text()
        assert "intake" in content
        assert "retrieving" in content
        assert "reasoning" in content
        assert "verifying" in content
        assert "reviewing" in content

    def test_live_progress_has_event_types(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "components" / "LiveProgress.tsx").read_text()
        assert "state_change" in content
        assert "tool_call" in content
        assert "verification_result" in content
        assert "patch_generated" in content
        assert "review_complete" in content
        assert "run_complete" in content

    def test_provenance_graph_component_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "components" / "ProvenanceGraph.tsx").exists()

    def test_provenance_graph_has_svg(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "components" / "ProvenanceGraph.tsx").read_text()
        assert "svg" in content
        assert "circle" in content
        assert "line" in content

    def test_provenance_graph_fetches_data(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "components" / "ProvenanceGraph.tsx").read_text()
        assert "getRunProvenance" in content
        assert "edges" in content

    def test_provenance_graph_has_node_selection(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "components" / "ProvenanceGraph.tsx").read_text()
        assert "selected" in content
        assert "setSelected" in content

    def test_run_detail_uses_websocket(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "pages" / "RunDetailPage.tsx").read_text()
        assert "useRunWebSocket" in content
        assert "LiveProgress" in content

    def test_run_detail_uses_provenance(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        content = (dash_dir / "src" / "pages" / "RunDetailPage.tsx").read_text()
        assert "ProvenanceGraph" in content

    def test_components_dir_exists(self):
        dash_dir = Path(__file__).parent.parent / "web-dashboard"
        assert (dash_dir / "src" / "components").is_dir()


# --- WebSocket Module Tests ---

class TestWebSocketModule:
    def test_websocket_module_exists(self):
        from vsrs.api import websocket
        assert hasattr(websocket, 'ConnectionManager')
        assert hasattr(websocket, 'manager')

    def test_manager_is_connection_manager(self):
        from vsrs.api.websocket import manager, ConnectionManager
        assert isinstance(manager, ConnectionManager)

    def test_websocket_module_logger(self):
        from vsrs.api.websocket import logger
        assert logger is not None
