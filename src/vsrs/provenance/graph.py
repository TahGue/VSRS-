"""Provenance graph: requirement -> patch -> test -> result (Section 5.2).

Provides convenience methods for creating the standard edge types
defined in Section 5.2, and a method to build a complete provenance
graph from a pipeline result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vsrs.core.logging import get_logger
from vsrs.core.schemas import ProvenanceEdge
from vsrs.provenance.store import GraphSummary, ProvenanceStore

if TYPE_CHECKING:
    from vsrs.orchestrator import PipelineResult
    from vsrs.reasoning.protocol import ReasoningOutput

logger = get_logger("provenance.graph")


class EvidenceGraph:
    """High-level evidence graph builder.

    Provides convenience methods for creating the standard edge types
    defined in Section 5.2 and building a complete provenance graph
    from a pipeline execution.
    """

    def __init__(self, store: ProvenanceStore) -> None:
        self.store = store

    # --- Standard edge creation methods ---

    def link_requirement_to_behavior(self, req_id: str, behavior_desc: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="requirement", from_id=req_id,
            relation="constrains", to_type="behavior", to_id=behavior_desc,
        ))

    def link_behavior_to_symbol(self, behavior_id: str, symbol_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="behavior", from_id=behavior_id,
            relation="implemented_by", to_type="symbol", to_id=symbol_id,
        ))

    def link_behavior_to_test(self, behavior_id: str, test_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="behavior", from_id=behavior_id,
            relation="verified_by", to_type="test", to_id=test_id,
        ))

    def link_requirement_to_patch(self, req_id: str, patch_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="requirement", from_id=req_id,
            relation="motivates", to_type="patch", to_id=patch_id,
        ))

    def link_requirement_to_evidence(self, req_id: str, evidence_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="requirement", from_id=req_id,
            relation="supported_by", to_type="evidence", to_id=evidence_id,
        ))

    def link_patch_to_file(self, patch_id: str, file_path: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="patch", from_id=patch_id,
            relation="modifies", to_type="file", to_id=file_path,
        ))

    def link_patch_to_test_run(self, patch_id: str, run_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="patch", from_id=patch_id,
            relation="verified_by", to_type="test_run", to_id=run_id,
        ))

    def link_patch_to_finding(self, patch_id: str, finding_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="patch", from_id=patch_id,
            relation="criticized_by", to_type="finding", to_id=finding_id,
        ))

    def link_patch_to_result(self, patch_id: str, result: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="patch", from_id=patch_id,
            relation="results_in", to_type="result", to_id=result,
        ))

    def link_task_to_evidence(self, task_id: str, evidence_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="task", from_id=task_id,
            relation="retrieved", to_type="evidence", to_id=evidence_id,
        ))

    def link_task_to_hypothesis(self, task_id: str, hypothesis_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="task", from_id=task_id,
            relation="hypothesized", to_type="hypothesis", to_id=hypothesis_id,
        ))

    def link_hypothesis_to_patch(self, hypothesis_id: str, patch_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="hypothesis", from_id=hypothesis_id,
            relation="produces", to_type="patch", to_id=patch_id,
        ))

    def link_evidence_to_hypothesis(self, evidence_id: str, hypothesis_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="evidence", from_id=evidence_id,
            relation="supports", to_type="hypothesis", to_id=hypothesis_id,
        ))

    def link_patch_to_verification(self, patch_id: str, verification_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="patch", from_id=patch_id,
            relation="checked_by", to_type="verification", to_id=verification_id,
        ))

    def link_verification_to_check(self, verification_id: str, check_type: str, check_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="verification", from_id=verification_id,
            relation="includes", to_type="check", to_id=f"{check_type}:{check_id}",
        ))

    def link_run_to_task(self, run_id: str, task_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="run", from_id=run_id,
            relation="executes", to_type="task", to_id=task_id,
        ))

    def link_run_to_patch(self, run_id: str, patch_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="run", from_id=run_id,
            relation="produced", to_type="patch", to_id=patch_id,
        ))

    def link_run_to_decision(self, run_id: str, decision_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="run", from_id=run_id,
            relation="decided", to_type="decision", to_id=decision_id,
        ))

    def link_task_to_requirement(self, task_id: str, requirement_id: str) -> None:
        self.store.add_edge(ProvenanceEdge(
            from_type="task", from_id=task_id,
            relation="has_requirement", to_type="requirement", to_id=requirement_id,
        ))

    # --- Pipeline integration ---

    def build_from_pipeline(
        self,
        result: "PipelineResult",
        reasoning_output: "ReasoningOutput | None" = None,
    ) -> None:
        """Build a complete provenance graph from a pipeline execution.

        Creates edges linking:
        - run → task
        - task → evidence (from retrieval)
        - task → hypothesis (from reasoning)
        - hypothesis → patch
        - patch → files (modified)
        - patch → verification
        - verification → checks
        - patch → findings (from critic)
        - run → decision
        """
        run_id = result.run.id
        task_id = result.run.task_id

        # run → task
        self.link_run_to_task(run_id, task_id)

        # task → evidence (from reasoning output)
        if reasoning_output and reasoning_output.evidence_summary:
            for locator in reasoning_output.evidence_summary.evidence_locators:
                self.link_task_to_evidence(task_id, locator)

        # task → hypothesis
        if reasoning_output and reasoning_output.hypothesis:
            hyp_id = reasoning_output.hypothesis.statement[:80]
            self.link_task_to_hypothesis(task_id, hyp_id)

            # evidence → hypothesis
            if reasoning_output.evidence_summary:
                for locator in reasoning_output.evidence_summary.evidence_locators:
                    self.link_evidence_to_hypothesis(locator, hyp_id)

        # hypothesis → patch
        if reasoning_output and reasoning_output.hypothesis and result.patch:
            hyp_id = reasoning_output.hypothesis.statement[:80]
            self.link_hypothesis_to_patch(hyp_id, result.patch.id)

        # run → patch
        if result.patch:
            self.link_run_to_patch(run_id, result.patch.id)

            # patch → files
            for file_path in result.patch.changed_files:
                self.link_patch_to_file(result.patch.id, file_path)

        # patch → verification
        if result.patch and result.verification_report:
            verification_id = f"verify_{result.patch.id}"
            self.link_patch_to_verification(result.patch.id, verification_id)

            # verification → checks
            for check in result.verification_report.checks:
                self.link_verification_to_check(
                    verification_id,
                    check.check_type,
                    str(check.exit_code),
                )

        # patch → findings (from critic)
        if result.patch and result.critic_report:
            for finding in result.critic_report.findings:
                self.link_patch_to_finding(result.patch.id, finding.id)

        # patch → result
        if result.patch and result.final_decision:
            self.link_patch_to_result(result.patch.id, result.final_decision.status.value)

        # run → decision
        if result.final_decision:
            self.link_run_to_decision(run_id, f"decision_{task_id}")

        logger.info(
            f"Built provenance graph for run {run_id}: "
            f"{self.store.summary(run_id, run_id).total_edges} edges"
        )

    # --- Query helpers ---

    def get_audit_trail(self, run_id: str) -> str:
        """Get a formatted audit trail for a run."""
        entries = self.store.audit_trail("run", run_id)
        return self.store.format_audit_trail(entries)

    def get_graph_summary(self, node_type: str | None = None, node_id: str | None = None) -> GraphSummary:
        """Get summary statistics of the provenance graph."""
        return self.store.summary(node_type, node_id)

    def find_evidence_chain(self, task_id: str, patch_id: str) -> list[ProvenanceEdge] | None:
        """Find the chain of evidence from task to patch."""
        return self.store.find_path("task", task_id, "patch", patch_id)
