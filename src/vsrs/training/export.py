"""Trajectory export: export normalized successful/failed trajectories (Section 15.1).

TODO: Phase 8 - full export pipeline implementation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vsrs.core.store import Store


class TrajectoryExporter:
    """Export task runs as normalized training trajectories.

    Produces the TrainingTrajectory structure from Section 15.1.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    def export_run(self, run_id: str) -> dict[str, Any] | None:
        """Export a single run as a training trajectory dict."""
        run = self.store.get_run(run_id)
        if not run:
            return None

        task = self.store.get_task(run.task_id)
        evidence = self.store.get_evidence_for_task(run.task_id)
        hypotheses = self.store.get_hypotheses_for_task(run.task_id)
        patches = self.store.get_patches_for_task(run.task_id)
        events = self.store.get_events_for_run(run_id)
        decision = self.store.get_final_decision(run.task_id)

        # Build verification results per patch
        verification_results = []
        for patch in patches:
            reports = self.store.get_verification_reports(patch.id)
            for report in reports:
                verification_results.append(report.model_dump(mode="json"))

        # Build critic findings per patch
        critic_findings = []
        for patch in patches:
            findings = self.store.get_findings_for_patch(patch.id)
            for finding in findings:
                critic_findings.append(finding.model_dump(mode="json"))

        return {
            "task": task.model_dump(mode="json") if task else None,
            "repository_snapshot_id": run.repo_snapshot_id,
            "retrieved_evidence": [e.model_dump(mode="json") for e in evidence],
            "hypotheses": [h.model_dump(mode="json") for h in hypotheses],
            "assumptions": patches[-1].assumptions if patches else [],
            "predicted_effects": patches[-1].predicted_effects if patches else [],
            "patch_attempts": [p.model_dump(mode="json") for p in patches],
            "verification_results": verification_results,
            "critic_findings": critic_findings,
            "repair_decisions": [
                e.model_dump(mode="json") for e in events
                if e.event_type == "state_change" and e.state.value == "revising"
            ],
            "final_patch": patches[-1].model_dump(mode="json") if patches else None,
            "final_status": decision.status.value if decision else run.state.value,
            "events": [e.model_dump(mode="json") for e in events],
        }

    def export_to_jsonl(self, run_ids: list[str], output_path: Path) -> int:
        """Export multiple runs as JSONL. Returns count of exported trajectories."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(output_path, "w") as f:
            for run_id in run_ids:
                trajectory = self.export_run(run_id)
                if trajectory:
                    f.write(json.dumps(trajectory, default=str) + "\n")
                    count += 1
        return count
