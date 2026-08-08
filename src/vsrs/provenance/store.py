"""Provenance store: persists evidence and provenance edges (Section 5.2).

Provides graph-aware operations over the provenance edge table:
- Forward and reverse BFS traversal
- Path finding between any two nodes
- Audit trail generation for a task run
- Node queries (all nodes of a type, neighbors, degree)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from vsrs.core.logging import get_logger
from vsrs.core.schemas import ProvenanceEdge
from vsrs.core.store import Store

logger = get_logger("provenance.store")


@dataclass
class AuditEntry:
    """A single entry in an audit trail."""

    node_type: str
    node_id: str
    relation: str
    to_type: str
    to_id: str
    depth: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"{'  ' * self.depth}{self.node_type}:{self.node_id} --{self.relation}--> {self.to_type}:{self.to_id}"


@dataclass
class GraphSummary:
    """Summary statistics of a provenance graph."""

    total_edges: int = 0
    total_nodes: int = 0
    node_types: dict[str, int] = field(default_factory=dict)
    relation_types: dict[str, int] = field(default_factory=dict)
    max_depth: int = 0


class ProvenanceStore:
    """High-level interface for provenance graph operations.

    Wraps the Store's provenance edge methods with graph-aware logic
    including traversal, path finding, and audit trail generation.
    """

    def __init__(self, store: Store) -> None:
        self.store = store

    def add_edge(self, edge: ProvenanceEdge) -> None:
        """Add a provenance edge to the graph."""
        self.store.save_provenance_edge(edge)

    def add_edges(self, edges: list[ProvenanceEdge]) -> None:
        """Add multiple provenance edges."""
        for edge in edges:
            self.store.save_provenance_edge(edge)

    def get_outgoing(self, node_type: str, node_id: str) -> list[ProvenanceEdge]:
        """Get all edges originating from a node."""
        return self.store.get_provenance_edges_from(node_type, node_id)

    def get_incoming(self, node_type: str, node_id: str) -> list[ProvenanceEdge]:
        """Get all edges pointing to a node."""
        return self.store.get_provenance_edges_to(node_type, node_id)

    def get_all_edges(self) -> list[ProvenanceEdge]:
        """Get all provenance edges in the graph."""
        rows = self.store._conn.execute(
            "SELECT * FROM provenance_edges"
        ).fetchall()
        return [ProvenanceEdge(
            from_type=row["from_type"], from_id=row["from_id"],
            relation=row["relation"], to_type=row["to_type"], to_id=row["to_id"],
            metadata=__import__("json").loads(row["metadata"]) if row["metadata"] else {},
        ) for row in rows]

    def trace(self, node_type: str, node_id: str, max_depth: int = 10) -> list[ProvenanceEdge]:
        """Trace the provenance graph forward from a node (BFS).

        Follows outgoing edges breadth-first up to max_depth.
        """
        visited: set[tuple[str, str]] = set()
        edges: list[ProvenanceEdge] = []
        queue: list[tuple[str, str, int]] = [(node_type, node_id, 0)]

        while queue:
            nt, nid, depth = queue.pop(0)
            if depth >= max_depth or (nt, nid) in visited:
                continue
            visited.add((nt, nid))
            for edge in self.get_outgoing(nt, nid):
                edges.append(edge)
                queue.append((edge.to_type, edge.to_id, depth + 1))

        return edges

    def reverse_trace(self, node_type: str, node_id: str, max_depth: int = 10) -> list[ProvenanceEdge]:
        """Trace the provenance graph backward to a node (BFS).

        Follows incoming edges breadth-first up to max_depth.
        """
        visited: set[tuple[str, str]] = set()
        edges: list[ProvenanceEdge] = []
        queue: list[tuple[str, str, int]] = [(node_type, node_id, 0)]

        while queue:
            nt, nid, depth = queue.pop(0)
            if depth >= max_depth or (nt, nid) in visited:
                continue
            visited.add((nt, nid))
            for edge in self.get_incoming(nt, nid):
                edges.append(edge)
                queue.append((edge.from_type, edge.from_id, depth + 1))

        return edges

    def find_path(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        max_depth: int = 10,
    ) -> list[ProvenanceEdge] | None:
        """Find a path between two nodes in the provenance graph (BFS).

        Returns:
            List of edges forming the path, or None if no path exists.
        """
        if from_type == to_type and from_id == to_id:
            return []

        visited: set[tuple[str, str]] = set()
        # Each queue entry: (node_type, node_id, path_so_far)
        queue: list[tuple[str, str, list[ProvenanceEdge]]] = [
            (from_type, from_id, [])
        ]

        while queue:
            nt, nid, path = queue.pop(0)
            if (nt, nid) in visited:
                continue
            visited.add((nt, nid))

            if len(path) >= max_depth:
                continue

            for edge in self.get_outgoing(nt, nid):
                new_path = path + [edge]
                if edge.to_type == to_type and edge.to_id == to_id:
                    return new_path
                queue.append((edge.to_type, edge.to_id, new_path))

        return None

    def audit_trail(self, node_type: str, node_id: str, max_depth: int = 10) -> list[AuditEntry]:
        """Generate a human-readable audit trail from a node.

        Traverses the graph forward and produces structured entries
        with depth information for hierarchical display.
        """
        entries: list[AuditEntry] = []
        visited: set[tuple[str, str]] = set()
        queue: list[tuple[str, str, int]] = [(node_type, node_id, 0)]

        while queue:
            nt, nid, depth = queue.pop(0)
            if depth >= max_depth or (nt, nid) in visited:
                continue
            visited.add((nt, nid))

            for edge in self.get_outgoing(nt, nid):
                entries.append(AuditEntry(
                    node_type=nt,
                    node_id=nid,
                    relation=edge.relation,
                    to_type=edge.to_type,
                    to_id=edge.to_id,
                    depth=depth,
                    metadata=edge.metadata,
                ))
                queue.append((edge.to_type, edge.to_id, depth + 1))

        return entries

    def get_nodes(self, node_type: str) -> list[tuple[str, str]]:
        """Get all nodes of a given type in the graph.

        Returns:
            List of (node_type, node_id) tuples.
        """
        edges = self.get_all_edges()
        nodes: set[tuple[str, str]] = set()
        for edge in edges:
            if edge.from_type == node_type:
                nodes.add((edge.from_type, edge.from_id))
            if edge.to_type == node_type:
                nodes.add((edge.to_type, edge.to_id))
        return sorted(nodes, key=lambda n: n[1])

    def get_neighbors(self, node_type: str, node_id: str) -> list[tuple[str, str]]:
        """Get all neighbor nodes (both incoming and outgoing)."""
        neighbors: set[tuple[str, str]] = set()
        for edge in self.get_outgoing(node_type, node_id):
            neighbors.add((edge.to_type, edge.to_id))
        for edge in self.get_incoming(node_type, node_id):
            neighbors.add((edge.from_type, edge.from_id))
        return sorted(neighbors, key=lambda n: n[1])

    def degree(self, node_type: str, node_id: str) -> int:
        """Get the degree (total edges) of a node."""
        return len(self.get_outgoing(node_type, node_id)) + len(self.get_incoming(node_type, node_id))

    def summary(self, node_type: str | None = None, node_id: str | None = None) -> GraphSummary:
        """Generate summary statistics of the provenance graph.

        If node_type and node_id are provided, summarizes only the
        subgraph reachable from that node.
        """
        if node_type and node_id:
            edges = self.trace(node_type, node_id)
        else:
            edges = self.get_all_edges()

        node_types: dict[str, int] = {}
        relation_types: dict[str, int] = {}
        nodes: set[tuple[str, str]] = set()
        max_depth = 0

        for edge in edges:
            relation_types[edge.relation] = relation_types.get(edge.relation, 0) + 1
            nodes.add((edge.from_type, edge.from_id))
            nodes.add((edge.to_type, edge.to_id))

        for nt, nid in nodes:
            node_types[nt] = node_types.get(nt, 0) + 1

        if node_type and node_id:
            # Compute max depth via BFS
            visited: set[tuple[str, str]] = set()
            queue: list[tuple[str, str, int]] = [(node_type, node_id, 0)]
            while queue:
                nt, nid, depth = queue.pop(0)
                if (nt, nid) in visited:
                    continue
                visited.add((nt, nid))
                max_depth = max(max_depth, depth)
                for edge in self.get_outgoing(nt, nid):
                    queue.append((edge.to_type, edge.to_id, depth + 1))

        return GraphSummary(
            total_edges=len(edges),
            total_nodes=len(nodes),
            node_types=node_types,
            relation_types=relation_types,
            max_depth=max_depth,
        )

    def format_audit_trail(self, entries: list[AuditEntry]) -> str:
        """Format an audit trail as a human-readable string."""
        lines: list[str] = []
        for entry in entries:
            lines.append(entry.describe())
        return "\n".join(lines)
