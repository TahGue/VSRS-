"""Tests for the provenance graph (Phase 8)."""

import subprocess
from pathlib import Path

import pytest

from vsrs.core.schemas import (
    CheckResult,
    CheckStatus,
    FinalDecision,
    FinalStatus,
    FindingSeverity,
    PatchCandidate,
    ProvenanceEdge,
    ReviewFinding,
    RiskLevel,
    Task,
    TaskRun,
    TaskState,
    TaskType,
    VerificationReport,
)
from vsrs.core.store import Store
from vsrs.orchestrator import Orchestrator, OrchestratorConfig, PipelineResult
from vsrs.provenance import AuditEntry, EvidenceGraph, GraphSummary, ProvenanceStore


def _create_test_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "auth.py").write_text(
        "def validate_password(pw: str) -> bool:\n    return bool(pw)\n"
    )
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "__init__.py").write_text("")
    (repo / "tests" / "test_auth.py").write_text(
        "from src.auth import validate_password\n\n"
        "def test_valid():\n    assert validate_password('secret')\n"
    )
    (repo / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\npythonpath = ["."]\n'
    )
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, capture_output=True)
    return repo


def _make_task() -> Task:
    return Task(
        id="task_001",
        repo_snapshot_id="repo_001",
        type=TaskType.bugfix,
        instruction="Fix the empty password bug in auth validate_password",
        acceptance_criteria=["reject empty password"],
        risk_level=RiskLevel.low,
        required_gates=["syntax", "existing_tests"],
    )


class TestProvenanceStore:
    def test_add_and_get_edge(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            edge = ProvenanceEdge(
                from_type="requirement", from_id="req_001",
                relation="motivates", to_type="patch", to_id="patch_001",
            )
            prov.add_edge(edge)

            outgoing = prov.get_outgoing("requirement", "req_001")
            assert len(outgoing) == 1
            assert outgoing[0].relation == "motivates"

            incoming = prov.get_incoming("patch", "patch_001")
            assert len(incoming) == 1

    def test_add_multiple_edges(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            edges = [
                ProvenanceEdge(from_type="task", from_id="t1", relation="r1", to_type="patch", to_id="p1"),
                ProvenanceEdge(from_type="task", from_id="t1", relation="r2", to_type="evidence", to_id="e1"),
            ]
            prov.add_edges(edges)

            outgoing = prov.get_outgoing("task", "t1")
            assert len(outgoing) == 2

    def test_trace_forward(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="produces", to_type="patch", to_id="p1"))
            prov.add_edge(ProvenanceEdge(from_type="patch", from_id="p1", relation="modifies", to_type="file", to_id="f1"))
            prov.add_edge(ProvenanceEdge(from_type="file", from_id="f1", relation="contains", to_type="symbol", to_id="s1"))

            edges = prov.trace("task", "t1")
            assert len(edges) == 3
            relations = [e.relation for e in edges]
            assert "produces" in relations
            assert "modifies" in relations
            assert "contains" in relations

    def test_trace_max_depth(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="a", from_id="1", relation="r", to_type="b", to_id="1"))
            prov.add_edge(ProvenanceEdge(from_type="b", from_id="1", relation="r", to_type="c", to_id="1"))
            prov.add_edge(ProvenanceEdge(from_type="c", from_id="1", relation="r", to_type="d", to_id="1"))

            edges = prov.trace("a", "1", max_depth=2)
            assert len(edges) == 2  # only first two edges

    def test_reverse_trace(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="produces", to_type="patch", to_id="p1"))
            prov.add_edge(ProvenanceEdge(from_type="patch", from_id="p1", relation="modifies", to_type="file", to_id="f1"))

            edges = prov.reverse_trace("file", "f1")
            assert len(edges) == 2
            assert edges[0].relation == "modifies"
            assert edges[1].relation == "produces"

    def test_find_path_direct(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="produces", to_type="patch", to_id="p1"))

            path = prov.find_path("task", "t1", "patch", "p1")
            assert path is not None
            assert len(path) == 1
            assert path[0].relation == "produces"

    def test_find_path_multi_hop(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="retrieved", to_type="evidence", to_id="e1"))
            prov.add_edge(ProvenanceEdge(from_type="evidence", from_id="e1", relation="supports", to_type="hypothesis", to_id="h1"))
            prov.add_edge(ProvenanceEdge(from_type="hypothesis", from_id="h1", relation="produces", to_type="patch", to_id="p1"))

            path = prov.find_path("task", "t1", "patch", "p1")
            assert path is not None
            assert len(path) == 3

    def test_find_path_no_path(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="r", to_type="patch", to_id="p1"))

            path = prov.find_path("task", "t1", "file", "f1")
            assert path is None

    def test_find_path_same_node(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            path = prov.find_path("task", "t1", "task", "t1")
            assert path == []

    def test_audit_trail(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="run", from_id="r1", relation="executes", to_type="task", to_id="t1"))
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="produces", to_type="patch", to_id="p1"))

            entries = prov.audit_trail("run", "r1")
            assert len(entries) == 2
            assert entries[0].depth == 0
            assert entries[0].relation == "executes"
            assert entries[1].depth == 1
            assert entries[1].relation == "produces"

    def test_audit_trail_describe(self, tmp_path):
        entry = AuditEntry(
            node_type="run", node_id="r1",
            relation="executes", to_type="task", to_id="t1",
            depth=0,
        )
        desc = entry.describe()
        assert "run:r1" in desc
        assert "executes" in desc
        assert "task:t1" in desc

    def test_format_audit_trail(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="run", from_id="r1", relation="executes", to_type="task", to_id="t1"))

            entries = prov.audit_trail("run", "r1")
            formatted = prov.format_audit_trail(entries)
            assert "run:r1" in formatted
            assert "task:t1" in formatted

    def test_get_nodes(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="r", to_type="patch", to_id="p1"))
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t2", relation="r", to_type="patch", to_id="p2"))

            tasks = prov.get_nodes("task")
            assert len(tasks) == 2
            patches = prov.get_nodes("patch")
            assert len(patches) == 2

    def test_get_neighbors(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="r1", to_type="patch", to_id="p1"))
            prov.add_edge(ProvenanceEdge(from_type="evidence", from_id="e1", relation="r2", to_type="task", to_id="t1"))

            neighbors = prov.get_neighbors("task", "t1")
            assert len(neighbors) == 2
            assert ("patch", "p1") in neighbors
            assert ("evidence", "e1") in neighbors

    def test_degree(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="r1", to_type="patch", to_id="p1"))
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="r2", to_type="evidence", to_id="e1"))
            prov.add_edge(ProvenanceEdge(from_type="run", from_id="r1", relation="r3", to_type="task", to_id="t1"))

            assert prov.degree("task", "t1") == 3

    def test_summary_full_graph(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="produces", to_type="patch", to_id="p1"))
            prov.add_edge(ProvenanceEdge(from_type="patch", from_id="p1", relation="modifies", to_type="file", to_id="f1"))

            summary = prov.summary()
            assert summary.total_edges == 2
            assert summary.total_nodes == 3
            assert "task" in summary.node_types
            assert "produces" in summary.relation_types

    def test_summary_subgraph(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="task", from_id="t1", relation="produces", to_type="patch", to_id="p1"))
            prov.add_edge(ProvenanceEdge(from_type="patch", from_id="p1", relation="modifies", to_type="file", to_id="f1"))
            prov.add_edge(ProvenanceEdge(from_type="other", from_id="o1", relation="r", to_type="node", to_id="n1"))

            summary = prov.summary("task", "t1")
            assert summary.total_edges == 2  # only reachable from task:t1
            assert summary.max_depth >= 1

    def test_get_all_edges(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            prov.add_edge(ProvenanceEdge(from_type="a", from_id="1", relation="r", to_type="b", to_id="1"))
            prov.add_edge(ProvenanceEdge(from_type="c", from_id="1", relation="r", to_type="d", to_id="1"))

            all_edges = prov.get_all_edges()
            assert len(all_edges) == 2


class TestEvidenceGraph:
    def test_link_methods(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.link_run_to_task("r1", "t1")
            graph.link_task_to_evidence("t1", "e1")
            graph.link_task_to_hypothesis("t1", "h1")
            graph.link_evidence_to_hypothesis("e1", "h1")
            graph.link_hypothesis_to_patch("h1", "p1")
            graph.link_run_to_patch("r1", "p1")
            graph.link_patch_to_file("p1", "src/auth.py")
            graph.link_patch_to_verification("p1", "verify_p1")
            graph.link_verification_to_check("verify_p1", "syntax", "0")
            graph.link_patch_to_finding("p1", "f1")
            graph.link_patch_to_result("p1", "verified_candidate")
            graph.link_run_to_decision("r1", "decision_t1")

            # Verify chain
            path = prov.find_path("run", "r1", "file", "src/auth.py")
            assert path is not None
            assert len(path) >= 2

    def test_build_from_pipeline(self, tmp_path):
        repo = _create_test_repo(tmp_path)
        task = _make_task()
        orchestrator = Orchestrator(
            config=OrchestratorConfig(run_lint=False, run_type_check=False, run_security=False),
        )

        result = orchestrator.run(task, repo)

        with Store(tmp_path / "prov.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.build_from_pipeline(result, result.reasoning_output)

            # Verify run → task edge
            outgoing = prov.get_outgoing("run", result.run.id)
            assert len(outgoing) > 0

            # Verify audit trail
            entries = prov.audit_trail("run", result.run.id)
            assert len(entries) > 0

    def test_get_audit_trail(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.link_run_to_task("r1", "t1")
            graph.link_task_to_evidence("t1", "e1")

            trail = graph.get_audit_trail("r1")
            assert "run:r1" in trail
            assert "task:t1" in trail

    def test_get_graph_summary(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.link_run_to_task("r1", "t1")
            graph.link_task_to_evidence("t1", "e1")

            summary = graph.get_graph_summary()
            assert summary.total_edges == 2

    def test_find_evidence_chain(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.link_task_to_evidence("t1", "e1")
            graph.link_evidence_to_hypothesis("e1", "h1")
            graph.link_hypothesis_to_patch("h1", "p1")

            chain = graph.find_evidence_chain("t1", "p1")
            assert chain is not None
            assert len(chain) == 3

    def test_find_evidence_chain_no_chain(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.link_run_to_task("r1", "t1")

            chain = graph.find_evidence_chain("t1", "p1")
            assert chain is None

    def test_link_requirement_to_patch(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.link_requirement_to_patch("req_001", "patch_001")

            outgoing = prov.get_outgoing("requirement", "req_001")
            assert len(outgoing) == 1
            assert outgoing[0].relation == "motivates"

    def test_link_behavior_chain(self, tmp_path):
        with Store(tmp_path / "test.db") as store:
            prov = ProvenanceStore(store)
            graph = EvidenceGraph(prov)

            graph.link_requirement_to_behavior("req_001", "reject_empty_password")
            graph.link_behavior_to_symbol("reject_empty_password", "validate_password")
            graph.link_behavior_to_test("reject_empty_password", "test_empty_password")

            # Verify chain from requirement to test
            path = prov.find_path("requirement", "req_001", "test", "test_empty_password")
            assert path is not None
            assert len(path) == 2
