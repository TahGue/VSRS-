"""Quality filters for training trajectories (Section 15.2).

Implements quality filters and scoring functions for training trajectory
selection:
- Basic filters: reproducible, verified_positive/negative, unresolved, has_patch, has_evidence, has_verification
- Advanced filters: minimality score, evidence quality score, repair efficiency
- Composite filter with configurable criteria
- Categorization into verified_positive, verified_negative, unresolved
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

    @staticmethod
    def minimality_score(trajectory: dict[str, Any]) -> float:
        """Compute a minimality score for the final patch.

        Score is 1.0 for a single-file patch and decreases with more files.
        Returns 0.0 if no patch.

        Range: [0.0, 1.0] where higher is more minimal.
        """
        final_patch = trajectory.get("final_patch")
        if not final_patch:
            return 0.0
        changed_files = final_patch.get("changed_files", [])
        if not changed_files:
            return 0.0
        return max(0.0, 1.0 - len(changed_files) * 0.1)

    @staticmethod
    def evidence_quality_score(trajectory: dict[str, Any]) -> float:
        """Compute an evidence quality score.

        Combines evidence count and verification coverage.
        Score is boosted by having both evidence and verification results.

        Range: [0.0, 1.0] where higher means better evidence quality.
        """
        evidence = trajectory.get("retrieved_evidence", [])
        verification = trajectory.get("verification_results", [])
        hypotheses = trajectory.get("hypotheses", [])

        score = 0.0
        if evidence:
            score += 0.3
        if verification:
            score += 0.3
        if hypotheses:
            score += 0.2
        if evidence and verification:
            score += 0.2

        return min(1.0, score)

    @staticmethod
    def repair_efficiency(trajectory: dict[str, Any]) -> float:
        """Compute repair efficiency.

        Returns 1.0 for first-attempt success (pass@1).
        Returns decreasing values for more attempts.
        Returns 0.0 if not verified or no patches.

        Range: [0.0, 1.0] where higher means more efficient.
        """
        if not TrajectoryFilter.is_verified_positive(trajectory):
            return 0.0
        patches = trajectory.get("patch_attempts", [])
        if not patches:
            return 0.0
        if len(patches) == 1:
            return 1.0
        return max(0.0, 1.0 - (len(patches) - 1) * 0.25)

    @staticmethod
    def has_provenance(trajectory: dict[str, Any]) -> bool:
        """Check if trajectory has provenance edges."""
        edges = trajectory.get("provenance_edges", [])
        return len(edges) > 0

    def filter(
        self,
        trajectories: list[dict[str, Any]],
        require_reproducible: bool = True,
        require_patch: bool = True,
        require_evidence: bool = True,
        require_verification: bool = True,
        exclude_statuses: set[str] | None = None,
        min_minimality: float = 0.0,
        min_evidence_quality: float = 0.0,
        min_repair_efficiency: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Apply all quality filters to a list of trajectories.

        Args:
            trajectories: List of trajectory dicts.
            require_reproducible: Require a repository snapshot ID.
            require_patch: Require at least one patch attempt.
            require_evidence: Require at least one evidence item.
            require_verification: Require at least one verification result.
            exclude_statuses: Set of final statuses to exclude.
            min_minimality: Minimum minimality score (0.0–1.0).
            min_evidence_quality: Minimum evidence quality score (0.0–1.0).
            min_repair_efficiency: Minimum repair efficiency score (0.0–1.0).

        Returns:
            Filtered list of trajectories.
        """
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
            if min_minimality > 0 and self.minimality_score(traj) < min_minimality:
                continue
            if min_evidence_quality > 0 and self.evidence_quality_score(traj) < min_evidence_quality:
                continue
            if min_repair_efficiency > 0 and self.repair_efficiency(traj) < min_repair_efficiency:
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

    def score(self, trajectory: dict[str, Any]) -> dict[str, float]:
        """Compute all quality scores for a trajectory.

        Returns:
            Dict with minimality, evidence_quality, repair_efficiency scores.
        """
        return {
            "minimality": self.minimality_score(trajectory),
            "evidence_quality": self.evidence_quality_score(trajectory),
            "repair_efficiency": self.repair_efficiency(trajectory),
        }
