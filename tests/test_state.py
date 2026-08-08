"""Tests for the task state machine (Phase 1.1)."""

import pytest

from vsrs.core.state import RESULT_STATES, TERMINAL_STATES, StateMachineError, TaskStateMachine
from vsrs.core.schemas import TaskState


class TestTaskStateMachine:
    def test_initial_state(self):
        sm = TaskStateMachine()
        assert sm.state == TaskState.intake

    def test_valid_transition(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.retrieving)
        assert sm.state == TaskState.retrieving

    def test_invalid_transition(self):
        sm = TaskStateMachine()
        with pytest.raises(StateMachineError, match="Invalid transition"):
            sm.transition(TaskState.verified)

    def test_full_happy_path(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.retrieving)
        sm.transition(TaskState.reasoning)
        sm.transition(TaskState.patching)
        sm.transition(TaskState.verifying)
        sm.transition(TaskState.verified)
        assert sm.state == TaskState.verified
        assert sm.is_terminal
        assert sm.is_result

    def test_repair_loop_path(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.retrieving)
        sm.transition(TaskState.reasoning)
        sm.transition(TaskState.patching)
        sm.transition(TaskState.verifying)
        sm.transition(TaskState.revising)
        sm.transition(TaskState.reasoning)
        sm.transition(TaskState.patching)
        sm.transition(TaskState.verifying)
        sm.transition(TaskState.verified)
        assert sm.state == TaskState.verified

    def test_escalation_path(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.retrieving)
        sm.transition(TaskState.reasoning)
        sm.transition(TaskState.escalated)
        assert sm.state == TaskState.escalated
        # Can resume from escalated
        sm.transition(TaskState.retrieving)
        assert sm.state == TaskState.retrieving

    def test_needs_review_path(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.retrieving)
        sm.transition(TaskState.reasoning)
        sm.transition(TaskState.patching)
        sm.transition(TaskState.verifying)
        sm.transition(TaskState.reviewing)
        sm.transition(TaskState.needs_review)
        assert sm.state == TaskState.needs_review
        assert sm.is_result
        # Can resume from needs_review
        sm.transition(TaskState.revising)
        assert sm.state == TaskState.revising

    def test_rejection_path(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.retrieving)
        sm.transition(TaskState.reasoning)
        sm.transition(TaskState.patching)
        sm.transition(TaskState.verifying)
        sm.transition(TaskState.rejected)
        assert sm.state == TaskState.rejected
        assert sm.is_terminal

    def test_failed_from_intake(self):
        sm = TaskStateMachine()
        sm.transition(TaskState.failed)
        assert sm.state == TaskState.failed
        assert sm.is_terminal

    def test_terminal_no_transitions(self):
        sm = TaskStateMachine(TaskState.verified)
        assert sm.is_terminal
        assert sm.valid_transitions() == []

    def test_can_transition(self):
        sm = TaskStateMachine()
        assert sm.can_transition(TaskState.retrieving)
        assert not sm.can_transition(TaskState.verified)

    def test_valid_transitions_list(self):
        sm = TaskStateMachine(TaskState.verifying)
        valid = sm.valid_transitions()
        assert TaskState.verified in valid
        assert TaskState.revising in valid
        assert TaskState.reviewing in valid
        assert TaskState.rejected in valid

    def test_reset(self):
        sm = TaskStateMachine(TaskState.verifying)
        sm.reset()
        assert sm.state == TaskState.intake

    def test_result_states(self):
        assert TaskState.verified in RESULT_STATES
        assert TaskState.rejected in RESULT_STATES
        assert TaskState.needs_review in RESULT_STATES
        assert TaskState.intake not in RESULT_STATES

    def test_terminal_states(self):
        assert TaskState.verified in TERMINAL_STATES
        assert TaskState.rejected in TERMINAL_STATES
        assert TaskState.failed in TERMINAL_STATES
        assert TaskState.intake not in TERMINAL_STATES
