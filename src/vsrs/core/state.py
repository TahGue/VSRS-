"""Task state machine for VSRS.

Implements the state machine from Section 7.1 and Phase 1.1:
intake -> retrieving -> reasoning -> patching -> verifying -> revising -> (reviewing) -> final

States are defined in schemas.TaskState. This module enforces valid transitions
and provides a clean interface for the orchestrator.
"""

from __future__ import annotations

from vsrs.core.schemas import TaskState


# Valid state transitions
_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.intake: {TaskState.retrieving, TaskState.failed},
    TaskState.retrieving: {TaskState.reasoning, TaskState.failed},
    TaskState.reasoning: {TaskState.patching, TaskState.escalated, TaskState.failed},
    TaskState.patching: {TaskState.verifying, TaskState.failed},
    TaskState.verifying: {
        TaskState.verified,
        TaskState.revising,
        TaskState.reviewing,
        TaskState.rejected,
        TaskState.failed,
    },
    TaskState.revising: {TaskState.reasoning, TaskState.patching, TaskState.escalated, TaskState.failed},
    TaskState.reviewing: {
        TaskState.verified,
        TaskState.rejected,
        TaskState.needs_review,
        TaskState.revising,
        TaskState.failed,
    },
    # Terminal states
    TaskState.verified: set(),
    TaskState.rejected: set(),
    TaskState.needs_review: {TaskState.revising, TaskState.verified, TaskState.rejected},
    TaskState.escalated: {TaskState.retrieving, TaskState.reasoning, TaskState.failed},
    TaskState.failed: set(),
}

# Terminal states (no outgoing transitions)
TERMINAL_STATES: frozenset[TaskState] = frozenset({
    TaskState.verified,
    TaskState.rejected,
    TaskState.failed,
})

# States that can produce a result for the user
RESULT_STATES: frozenset[TaskState] = frozenset({
    TaskState.verified,
    TaskState.rejected,
    TaskState.needs_review,
})


class StateMachineError(Exception):
    """Raised when an invalid state transition is attempted."""


class TaskStateMachine:
    """Enforces valid state transitions for a task run.

    The state machine is intentionally explicit — no framework magic.
    Each transition is validated against the allowed transition table.
    """

    def __init__(self, initial_state: TaskState = TaskState.intake) -> None:
        self._state = initial_state

    @property
    def state(self) -> TaskState:
        """Current state."""
        return self._state

    @property
    def is_terminal(self) -> bool:
        """Whether the current state is terminal."""
        return self._state in TERMINAL_STATES

    @property
    def is_result(self) -> bool:
        """Whether the current state produces a user-facing result."""
        return self._state in RESULT_STATES

    def can_transition(self, target: TaskState) -> bool:
        """Check whether a transition to the target state is valid."""
        return target in _TRANSITIONS.get(self._state, set())

    def transition(self, target: TaskState) -> TaskState:
        """Transition to the target state.

        Raises:
            StateMachineError: If the transition is invalid.
        """
        if not self.can_transition(target):
            raise StateMachineError(
                f"Invalid transition: {self._state.value} -> {target.value}. "
                f"Valid targets from {self._state.value}: "
                f"{[s.value for s in _TRANSITIONS.get(self._state, set())]}"
            )
        self._state = target
        return self._state

    def valid_transitions(self) -> list[TaskState]:
        """List valid target states from the current state."""
        return sorted(_TRANSITIONS.get(self._state, set()), key=lambda s: s.value)

    def reset(self, state: TaskState = TaskState.intake) -> None:
        """Reset the state machine to a given state."""
        self._state = state
