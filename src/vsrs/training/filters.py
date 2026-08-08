"""Quality filters for training trajectories (Section 15.2).

TODO: Phase 8 - full filter implementation.
"""

from __future__ import annotations

from typing import Any


class TrajectoryFilter:
    """Filter training trajectories by quality criteria.

    Implements the quality filters from Section 15.2.
    """

    @staticmethod
    def is_reproducible(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory has a reproducible repository snapshot."""
        return bool(trajectory.get("repository_snapshot_id"))

    @staticmethod
    def is_verified_positive(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory is a verified success."""
        return trajectory.get("final_status") == "verified_candidate"

    @staticmethod
    def is_verified_negative(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory is a verified failure."""
        return trajectory.get("final_status") in ("rejected", "failed")

    @staticmethod
    def is_unresolved(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory was unresolved."""
        return trajectory.get("final_status") == "needs_review"

    @staticmethod
    def has_patch(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory has at least one patch attempt."""
        attempts = trajectory.get("patch_attempts", [])
        return len(attempts) > 0

    @staticmethod
    def has_evidence(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory has retrieved evidence."""
        evidence = trajectory.get("retrieved_evidence", [])
        return len(evidence) > 0

    @staticmethod
    def has_verification_results(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory has verification results."""
        results = trajectory.get("verification_results", [])
        return len(results) > 0

    def filter(
        self,
        trajectories: list[dict[str, Any]],
        require_reproducible: bool = True,
        require_patch: bool = True,
        require_evidence: bool = True,
        require_verification: bool = True,
        exclude_statuses: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Apply all quality filters to a list of trajectories."""
        exclude_statuses = exclude_statuses or set()
        result = []
        for traj in trajectories:
            if require_reproducible and not self.is_reproducible(traj):
                continue
            if require_patch and not self.has_patch(traj):
                continue
            if require_evidence and not self.has_evidence(traj):
                continue
            if require_verification and not self.has_verification_results(traj):
                continue
            if traj.get("final_status") in exclude_statuses:
                continue
            result.append(traj)
        return result

    def categorize(self, trajectory: dict[str, Any]) -> str:
        """Categorize a trajectory as verified_positive, verified_negative, or unresolved."""
        if self.is_verified_positive(trajectory):
            return "verified_positive"
        elif self.is_verified_negative(trajectory):
            return "verified_negative"
        else:
            return "unresolved"
