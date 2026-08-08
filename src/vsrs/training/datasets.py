"""Dataset construction for fine-tuning (Section 15.4).

TODO: Phase 8/9 - full dataset builder implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vsrs.training.filters import TrajectoryFilter


class DatasetBuilder:
    """Build training datasets from filtered trajectories.

    Supports the training stages from Section 15.4:
    - SFT/LoRA: verified structured trajectories
    - Preference tuning: good vs overreaching/ungrounded patches
    - Repair tuning: failure result -> corrected action
    - Tool-use tuning: task + repo state -> correct tool query
    """

    def __init__(self, filter: TrajectoryFilter | None = None) -> None:
        self.filter = filter or TrajectoryFilter()

    def build_sft_dataset(
        self,
        trajectories: list[dict[str, Any]],
        output_path: Path,
    ) -> int:
        """Build an SFT dataset from verified-positive trajectories.

        Format: JSONL with {input, output} pairs following the reasoning protocol.
        """
        verified = [
            t for t in trajectories
            if self.filter.is_verified_positive(t)
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(output_path, "w") as f:
            for traj in verified:
                task = traj.get("task", {})
                final_patch = traj.get("final_patch", {})
                entry = {
                    "input": {
                        "instruction": task.get("instruction", ""),
                        "acceptance_criteria": task.get("acceptance_criteria", []),
                        "evidence": traj.get("retrieved_evidence", []),
                    },
                    "output": {
                        "hypotheses": traj.get("hypotheses", []),
                        "assumptions": final_patch.get("assumptions", []),
                        "predicted_effects": final_patch.get("predicted_effects", []),
                        "falsification_checks": final_patch.get("falsification_checks", []),
                        "diff": final_patch.get("diff", ""),
                    },
                }
                f.write(json.dumps(entry, default=str) + "\n")
                count += 1
        return count

    def build_repair_dataset(
        self,
        trajectories: list[dict[str, Any]],
        output_path: Path,
    ) -> int:
        """Build a repair tuning dataset from failed-then-succeeded trajectories.

        Format: JSONL with {failure, corrected_action} pairs.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(output_path, "w") as f:
            for traj in trajectories:
                patches = traj.get("patch_attempts", [])
                if len(patches) < 2:
                    continue
                if not self.filter.is_verified_positive(traj):
                    continue
                # First patch failed, later patch succeeded
                failed_patch = patches[0]
                success_patch = patches[-1]
                verification_results = traj.get("verification_results", [])
                entry = {
                    "failure": {
                        "diff": failed_patch.get("diff", ""),
                        "verification_results": verification_results[:1],
                    },
                    "corrected_action": {
                        "diff": success_patch.get("diff", ""),
                    },
                }
                f.write(json.dumps(entry, default=str) + "\n")
                count += 1
        return count

    def build_preference_dataset(
        self,
        trajectories: list[dict[str, Any]],
        output_path: Path,
    ) -> int:
        """Build a preference tuning dataset: good vs overreaching patches.

        Format: JSONL with {chosen, rejected} pairs.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        positive = [t for t in trajectories if self.filter.is_verified_positive(t)]
        negative = [t for t in trajectories if self.filter.is_verified_negative(t)]
        count = 0
        with open(output_path, "w") as f:
            for pos, neg in zip(positive, negative, strict=False):
                pos_patch = pos.get("final_patch", {})
                neg_patch = neg.get("final_patch", {})
                if not pos_patch or not neg_patch:
                    continue
                entry = {
                    "chosen": pos_patch.get("diff", ""),
                    "rejected": neg_patch.get("diff", ""),
                    "task": pos.get("task", {}).get("instruction", ""),
                }
                f.write(json.dumps(entry, default=str) + "\n")
                count += 1
        return count
