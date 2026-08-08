"""Dataset construction for fine-tuning (Section 15.4).

Supports the training stages from Section 15.4:
- SFT/LoRA: verified structured trajectories
- Preference tuning: good vs overreaching/ungrounded patches
- Repair tuning: failure result -> corrected action
- Tool-use tuning: task + repo state -> correct tool query

Additional features:
- Token counting (approximate, character-based)
- Train/validation split with deterministic seeding
- Dataset statistics (entry count, token counts, status distribution)
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from vsrs.training.filters import TrajectoryFilter


def _approx_token_count(text: str) -> int:
    """Approximate token count using character-based heuristic (~4 chars per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def _count_entry_tokens(entry: dict[str, Any]) -> int:
    """Count approximate tokens in a dataset entry."""
    total = 0
    for value in _flatten_values(entry):
        if isinstance(value, str):
            total += _approx_token_count(value)
    return total


def _flatten_values(d: Any) -> list[Any]:
    """Recursively extract all values from a nested dict/list."""
    values: list[Any] = []
    if isinstance(d, dict):
        for v in d.values():
            values.extend(_flatten_values(v))
    elif isinstance(d, list):
        for item in d:
            values.extend(_flatten_values(item))
    else:
        values.append(d)
    return values


class DatasetStats:
    """Statistics for a generated dataset."""

    def __init__(self) -> None:
        self.entry_count: int = 0
        self.total_tokens: int = 0
        self.min_tokens: int = 0
        self.max_tokens: int = 0
        self.avg_tokens: float = 0.0
        self.status_distribution: dict[str, int] = {}

    def add_entry(self, tokens: int, status: str = "") -> None:
        self.entry_count += 1
        self.total_tokens += tokens
        if self.entry_count == 1:
            self.min_tokens = tokens
            self.max_tokens = tokens
        else:
            self.min_tokens = min(self.min_tokens, tokens)
            self.max_tokens = max(self.max_tokens, tokens)
        if status:
            self.status_distribution[status] = self.status_distribution.get(status, 0) + 1

    def finalize(self) -> None:
        if self.entry_count > 0:
            self.avg_tokens = self.total_tokens / self.entry_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_count": self.entry_count,
            "total_tokens": self.total_tokens,
            "min_tokens": self.min_tokens,
            "max_tokens": self.max_tokens,
            "avg_tokens": round(self.avg_tokens, 1),
            "status_distribution": self.status_distribution,
        }


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

    def build_tool_use_dataset(
        self,
        trajectories: list[dict[str, Any]],
        output_path: Path,
    ) -> int:
        """Build a tool-use tuning dataset: task + repo state -> correct tool query.

        Format: JSONL with {context, tool_call, result} entries.
        Each entry captures what evidence was retrieved for a given task.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(output_path, "w") as f:
            for traj in trajectories:
                task = traj.get("task", {})
                evidence = traj.get("retrieved_evidence", [])
                if not task or not evidence:
                    continue
                for ev in evidence:
                    entry = {
                        "context": {
                            "instruction": task.get("instruction", ""),
                            "task_type": task.get("type", ""),
                        },
                        "tool_call": {
                            "tool": "retrieve",
                            "query": ev.get("locator", ""),
                        },
                        "result": {
                            "kind": ev.get("type", ""),
                            "locator": ev.get("locator", ""),
                            "content": ev.get("content", "")[:500],
                        },
                    }
                    f.write(json.dumps(entry, default=str) + "\n")
                    count += 1
        return count

    def train_val_split(
        self,
        trajectories: list[dict[str, Any]],
        val_ratio: float = 0.2,
        seed: int = 42,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split trajectories into train and validation sets.

        Uses deterministic seeding for reproducibility.

        Args:
            trajectories: List of trajectory dicts.
            val_ratio: Fraction of data for validation (0.0–1.0).
            seed: Random seed for reproducibility.

        Returns:
            Tuple of (train_trajectories, val_trajectories).
        """
        rng = random.Random(seed)
        shuffled = list(trajectories)
        rng.shuffle(shuffled)
        val_count = int(len(shuffled) * val_ratio)
        val = shuffled[:val_count]
        train = shuffled[val_count:]
        return train, val

    def build_with_stats(
        self,
        trajectories: list[dict[str, Any]],
        output_path: Path,
        dataset_type: str = "sft",
    ) -> tuple[int, DatasetStats]:
        """Build a dataset and return entry count + statistics.

        Args:
            trajectories: List of trajectory dicts.
            output_path: Where to write the JSONL file.
            dataset_type: One of 'sft', 'repair', 'preference', 'tool_use'.

        Returns:
            Tuple of (entry_count, DatasetStats).
        """
        builders = {
            "sft": self.build_sft_dataset,
            "repair": self.build_repair_dataset,
            "preference": self.build_preference_dataset,
            "tool_use": self.build_tool_use_dataset,
        }
        builder = builders.get(dataset_type)
        if not builder:
            raise ValueError(f"Unknown dataset type: {dataset_type}")

        count = builder(trajectories, output_path)

        # Compute stats by reading back the file
        stats = DatasetStats()
        if output_path.exists():
            with open(output_path) as f:
                for line in f:
                    entry = json.loads(line)
                    tokens = _count_entry_tokens(entry)
                    status = entry.get("final_status", "")
                    stats.add_entry(tokens, status)
        stats.finalize()
        return count, stats
