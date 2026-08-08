"""Tests for the event log (Phase 1.2)."""

from vsrs.core.events import EventLog
from vsrs.core.schemas import TaskState


class TestEventLog:
    def test_record(self):
        log = EventLog("run_001", "task_001")
        event = log.record(TaskState.intake, "task_created", {"prompt": "Fix bug"})
        assert event.run_id == "run_001"
        assert event.event_type == "task_created"
        assert len(log) == 1

    def test_record_state_change(self):
        log = EventLog("run_001", "task_001")
        log.record_state_change(TaskState.intake, TaskState.retrieving)
        assert len(log) == 1
        event = log.latest()
        assert event.event_type == "state_change"
        assert event.payload["from"] == "intake"
        assert event.payload["to"] == "retrieving"

    def test_record_tool_call(self):
        log = EventLog("run_001", "task_001")
        log.record_tool_call(
            TaskState.verifying,
            tool_name="pytest",
            command="pytest tests/",
            exit_code=0,
            duration_seconds=2.5,
        )
        assert len(log) == 1
        event = log.latest()
        assert event.event_type == "tool_call"
        assert event.payload["tool"] == "pytest"
        assert event.payload["exit_code"] == 0

    def test_record_evidence(self):
        log = EventLog("run_001", "task_001")
        log.record_evidence(
            TaskState.retrieving,
            evidence_id="ev_001",
            evidence_type="structural",
            locator="src/auth.py:42",
        )
        assert len(log) == 1
        event = log.latest()
        assert event.event_type == "evidence_retrieved"
        assert event.payload["evidence_id"] == "ev_001"

    def test_filter(self):
        log = EventLog("run_001", "task_001")
        log.record(TaskState.intake, "task_created")
        log.record(TaskState.retrieving, "evidence_retrieved")
        log.record(TaskState.retrieving, "evidence_retrieved")
        log.record(TaskState.verifying, "tool_call")

        evidence_events = log.filter("evidence_retrieved")
        assert len(evidence_events) == 2
        tool_events = log.filter("tool_call")
        assert len(tool_events) == 1

    def test_latest(self):
        log = EventLog("run_001", "task_001")
        assert log.latest() is None
        log.record(TaskState.intake, "first")
        log.record(TaskState.retrieving, "second")
        assert log.latest().event_type == "second"

    def test_all(self):
        log = EventLog("run_001", "task_001")
        log.record(TaskState.intake, "a")
        log.record(TaskState.retrieving, "b")
        events = log.all()
        assert len(events) == 2
        # Ensure it's a copy
        events.clear()
        assert len(log) == 2

    def test_to_dict_list(self):
        log = EventLog("run_001", "task_001")
        log.record(TaskState.intake, "test", {"key": "value"})
        dicts = log.to_dict_list()
        assert len(dicts) == 1
        assert dicts[0]["event_type"] == "test"
        assert dicts[0]["payload"]["key"] == "value"

    def test_iteration(self):
        log = EventLog("run_001", "task_001")
        log.record(TaskState.intake, "a")
        log.record(TaskState.retrieving, "b")
        types = [e.event_type for e in log]
        assert types == ["a", "b"]
