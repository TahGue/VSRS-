"""SQLite persistence layer for VSRS.

Stores all core entities as typed rows with JSON payloads for complex fields.
Implements Section 11: relational storage with typed node/edge tables,
append-only run events, and immutability for failed attempts.

Tables:
- repositories
- tasks
- task_runs
- evidence_items
- hypotheses
- patch_candidates
- verification_reports
- review_findings
- provenance_edges
- run_events
- final_decisions
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from vsrs.core.schemas import (
    CheckResult,
    EvidenceContract,
    EvidenceItem,
    FinalDecision,
    Hypothesis,
    PatchCandidate,
    ProvenanceEdge,
    RepositorySnapshot,
    ReviewFinding,
    RunEvent,
    Task,
    TaskRun,
    VerificationReport,
)


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS repositories (
    id TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    language_profile TEXT NOT NULL DEFAULT 'python',
    config_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    repo_snapshot_id TEXT NOT NULL,
    type TEXT NOT NULL,
    instruction TEXT NOT NULL,
    acceptance_criteria TEXT NOT NULL DEFAULT '[]',
    risk_level TEXT NOT NULL DEFAULT 'low',
    required_gates TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT 'intake',
    created_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (repo_snapshot_id) REFERENCES repositories(id)
);

CREATE TABLE IF NOT EXISTS task_runs (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    repo_snapshot_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'intake',
    attempt_no INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    worktree_path TEXT NOT NULL DEFAULT '',
    final_decision TEXT,
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (repo_snapshot_id) REFERENCES repositories(id)
);

CREATE TABLE IF NOT EXISTS evidence_items (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    type TEXT NOT NULL,
    source TEXT NOT NULL,
    locator TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'unknown',
    timestamp TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS hypotheses (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    statement TEXT NOT NULL,
    unknowns TEXT NOT NULL DEFAULT '[]',
    supporting_evidence_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS patch_candidates (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    attempt_no INTEGER NOT NULL DEFAULT 1,
    base_commit TEXT NOT NULL,
    diff TEXT NOT NULL,
    changed_files TEXT NOT NULL DEFAULT '[]',
    changed_symbols TEXT NOT NULL DEFAULT '[]',
    assumptions TEXT NOT NULL DEFAULT '[]',
    predicted_effects TEXT NOT NULL DEFAULT '[]',
    falsification_checks TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS verification_reports (
    id TEXT PRIMARY KEY,
    patch_id TEXT NOT NULL,
    checks TEXT NOT NULL DEFAULT '[]',
    required_passed INTEGER NOT NULL DEFAULT 0,
    blockers TEXT NOT NULL DEFAULT '[]',
    unresolved_unknowns TEXT NOT NULL DEFAULT '[]',
    final_status TEXT NOT NULL DEFAULT 'needs_review',
    timestamp TEXT NOT NULL,
    FOREIGN KEY (patch_id) REFERENCES patch_candidates(id)
);

CREATE TABLE IF NOT EXISTS review_findings (
    id TEXT PRIMARY KEY,
    patch_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (patch_id) REFERENCES patch_candidates(id)
);

CREATE TABLE IF NOT EXISTS evidence_contracts (
    change_id TEXT PRIMARY KEY,
    requirement_ids TEXT NOT NULL DEFAULT '[]',
    affected_symbols TEXT NOT NULL DEFAULT '[]',
    supporting_evidence TEXT NOT NULL DEFAULT '[]',
    assumptions TEXT NOT NULL DEFAULT '[]',
    expected_behavior_changes TEXT NOT NULL DEFAULT '[]',
    falsification_checks TEXT NOT NULL DEFAULT '[]',
    verification_results TEXT NOT NULL DEFAULT '[]',
    unresolved_questions TEXT NOT NULL DEFAULT '[]',
    final_status TEXT NOT NULL DEFAULT 'needs_review',
    complete INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS provenance_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_type TEXT NOT NULL,
    from_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    state TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    timestamp TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES task_runs(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS final_decisions (
    task_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    blockers TEXT NOT NULL DEFAULT '[]',
    waived_gates TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    provenance_id TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_repo ON tasks(repo_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_runs_task ON task_runs(task_id);
CREATE INDEX IF NOT EXISTS idx_evidence_task ON evidence_items(task_id);
CREATE INDEX IF NOT EXISTS idx_patches_task ON patch_candidates(task_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_provenance_from ON provenance_edges(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_provenance_to ON provenance_edges(to_type, to_id);
"""


def _dumps(value: Any) -> str:
    """Serialize a value to JSON string."""
    return json.dumps(value, default=str)


def _loads_list(value: str) -> list[Any]:
    """Deserialize a JSON list."""
    return json.loads(value) if value else []


def _loads_dict(value: str) -> dict[str, Any]:
    """Deserialize a JSON dict."""
    return json.loads(value) if value else {}


class Store:
    """SQLite-backed persistence for VSRS entities.

    All writes are explicit. Reads return Pydantic models.
    Failed attempts are never overwritten — new attempts are appended.
    """

    def __init__(self, db_path: str) -> None:
        """Initialize the store.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # --- Repository ---

    def save_repository(self, repo: RepositorySnapshot) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO repositories
               (id, root, commit_hash, language_profile, config_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (repo.id, repo.root, repo.commit_hash, repo.language_profile,
             repo.config_hash, repo.created_at.isoformat()),
        )
        self._conn.commit()

    def get_repository(self, repo_id: str) -> RepositorySnapshot | None:
        row = self._conn.execute(
            "SELECT * FROM repositories WHERE id = ?", (repo_id,)
        ).fetchone()
        if not row:
            return None
        return RepositorySnapshot(**dict(row))

    # --- Task ---

    def save_task(self, task: Task) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO tasks
               (id, repo_snapshot_id, type, instruction, acceptance_criteria,
                risk_level, required_gates, state, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (task.id, task.repo_snapshot_id, task.type.value, task.instruction,
             _dumps(task.acceptance_criteria), task.risk_level.value,
             _dumps(task.required_gates), task.state.value,
             task.created_at.isoformat(), _dumps(task.metadata)),
        )
        self._conn.commit()

    def get_task(self, task_id: str) -> Task | None:
        row = self._conn.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return Task(
            id=row["id"],
            repo_snapshot_id=row["repo_snapshot_id"],
            type=row["type"],
            instruction=row["instruction"],
            acceptance_criteria=_loads_list(row["acceptance_criteria"]),
            risk_level=row["risk_level"],
            required_gates=_loads_list(row["required_gates"]),
            state=row["state"],
            created_at=row["created_at"],
            metadata=_loads_dict(row["metadata"]),
        )

    # --- TaskRun ---

    def save_run(self, run: TaskRun) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO task_runs
               (id, task_id, repo_snapshot_id, state, attempt_no, max_attempts,
                started_at, updated_at, finished_at, worktree_path, final_decision)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (run.id, run.task_id, run.repo_snapshot_id, run.state.value,
             run.attempt_no, run.max_attempts, run.started_at.isoformat(),
             run.updated_at.isoformat(),
             run.finished_at.isoformat() if run.finished_at else None,
             run.worktree_path,
             run.final_decision.model_dump_json() if run.final_decision else None),
        )
        self._conn.commit()

    def get_run(self, run_id: str) -> TaskRun | None:
        row = self._conn.execute(
            "SELECT * FROM task_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            return None
        fd = None
        if row["final_decision"]:
            fd = FinalDecision.model_validate_json(row["final_decision"])
        return TaskRun(
            id=row["id"],
            task_id=row["task_id"],
            repo_snapshot_id=row["repo_snapshot_id"],
            state=row["state"],
            attempt_no=row["attempt_no"],
            max_attempts=row["max_attempts"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
            worktree_path=row["worktree_path"],
            final_decision=fd,
        )

    def get_runs_for_task(self, task_id: str) -> list[TaskRun]:
        rows = self._conn.execute(
            "SELECT * FROM task_runs WHERE task_id = ? ORDER BY started_at", (task_id,)
        ).fetchall()
        runs = []
        for row in rows:
            fd = None
            if row["final_decision"]:
                fd = FinalDecision.model_validate_json(row["final_decision"])
            runs.append(TaskRun(
                id=row["id"], task_id=row["task_id"], repo_snapshot_id=row["repo_snapshot_id"],
                state=row["state"], attempt_no=row["attempt_no"], max_attempts=row["max_attempts"],
                started_at=row["started_at"], updated_at=row["updated_at"],
                finished_at=row["finished_at"], worktree_path=row["worktree_path"],
                final_decision=fd,
            ))
        return runs

    def list_all_runs(self, limit: int = 100, offset: int = 0) -> list[TaskRun]:
        """List all runs, most recent first, with pagination."""
        rows = self._conn.execute(
            "SELECT * FROM task_runs ORDER BY started_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        runs = []
        for row in rows:
            fd = None
            if row["final_decision"]:
                fd = FinalDecision.model_validate_json(row["final_decision"])
            runs.append(TaskRun(
                id=row["id"], task_id=row["task_id"], repo_snapshot_id=row["repo_snapshot_id"],
                state=row["state"], attempt_no=row["attempt_no"], max_attempts=row["max_attempts"],
                started_at=row["started_at"], updated_at=row["updated_at"],
                finished_at=row["finished_at"], worktree_path=row["worktree_path"],
                final_decision=fd,
            ))
        return runs

    def count_runs(self) -> int:
        """Count total runs in the store."""
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM task_runs").fetchone()
        return row["cnt"]

    # --- EvidenceItem ---

    def save_evidence(self, item: EvidenceItem, task_id: str) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO evidence_items
               (id, task_id, type, source, locator, content_hash, state, timestamp, content, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.id, task_id, item.type.value, item.source, item.locator,
             item.content_hash, item.state.value, item.timestamp.isoformat(),
             item.content, _dumps(item.metadata)),
        )
        self._conn.commit()

    def get_evidence_for_task(self, task_id: str) -> list[EvidenceItem]:
        rows = self._conn.execute(
            "SELECT * FROM evidence_items WHERE task_id = ? ORDER BY timestamp", (task_id,)
        ).fetchall()
        return [EvidenceItem(
            id=row["id"], type=row["type"], source=row["source"], locator=row["locator"],
            content_hash=row["content_hash"], state=row["state"],
            timestamp=row["timestamp"], content=row["content"],
            metadata=_loads_dict(row["metadata"]),
        ) for row in rows]

    # --- Hypothesis ---

    def save_hypothesis(self, hyp: Hypothesis) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO hypotheses
               (id, task_id, statement, unknowns, supporting_evidence_ids, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (hyp.id, hyp.task_id, hyp.statement, _dumps(hyp.unknowns),
             _dumps(hyp.supporting_evidence_ids), hyp.created_at.isoformat()),
        )
        self._conn.commit()

    def get_hypotheses_for_task(self, task_id: str) -> list[Hypothesis]:
        rows = self._conn.execute(
            "SELECT * FROM hypotheses WHERE task_id = ? ORDER BY created_at", (task_id,)
        ).fetchall()
        return [Hypothesis(
            id=row["id"], task_id=row["task_id"], statement=row["statement"],
            unknowns=_loads_list(row["unknowns"]),
            supporting_evidence_ids=_loads_list(row["supporting_evidence_ids"]),
            created_at=row["created_at"],
        ) for row in rows]

    # --- PatchCandidate ---

    def save_patch(self, patch: PatchCandidate) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO patch_candidates
               (id, task_id, attempt_no, base_commit, diff, changed_files, changed_symbols,
                assumptions, predicted_effects, falsification_checks, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patch.id, patch.task_id, patch.attempt_no, patch.base_commit, patch.diff,
             _dumps(patch.changed_files), _dumps(patch.changed_symbols),
             _dumps(patch.assumptions), _dumps(patch.predicted_effects),
             _dumps(patch.falsification_checks), patch.created_at.isoformat()),
        )
        self._conn.commit()

    def get_patches_for_task(self, task_id: str) -> list[PatchCandidate]:
        rows = self._conn.execute(
            "SELECT * FROM patch_candidates WHERE task_id = ? ORDER BY attempt_no", (task_id,)
        ).fetchall()
        return [PatchCandidate(
            id=row["id"], task_id=row["task_id"], attempt_no=row["attempt_no"],
            base_commit=row["base_commit"], diff=row["diff"],
            changed_files=_loads_list(row["changed_files"]),
            changed_symbols=_loads_list(row["changed_symbols"]),
            assumptions=_loads_list(row["assumptions"]),
            predicted_effects=_loads_list(row["predicted_effects"]),
            falsification_checks=_loads_list(row["falsification_checks"]),
            created_at=row["created_at"],
        ) for row in rows]

    def get_latest_patch(self, task_id: str) -> PatchCandidate | None:
        patches = self.get_patches_for_task(task_id)
        return patches[-1] if patches else None

    # --- VerificationReport ---

    def save_verification_report(self, report: VerificationReport) -> None:
        report_id = f"{report.patch_id}_{report.timestamp.isoformat()}"
        self._conn.execute(
            """INSERT OR REPLACE INTO verification_reports
               (id, patch_id, checks, required_passed, blockers, unresolved_unknowns,
                final_status, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_id, report.patch_id, _dumps([c.model_dump(mode="json") for c in report.checks]),
             int(report.required_passed), _dumps(report.blockers),
             _dumps(report.unresolved_unknowns), report.final_status.value,
             report.timestamp.isoformat()),
        )
        self._conn.commit()

    def get_verification_reports(self, patch_id: str) -> list[VerificationReport]:
        rows = self._conn.execute(
            "SELECT * FROM verification_reports WHERE patch_id = ? ORDER BY timestamp", (patch_id,)
        ).fetchall()
        reports = []
        for row in rows:
            checks = [CheckResult.model_validate(c) for c in _loads_list(row["checks"])]
            reports.append(VerificationReport(
                patch_id=row["patch_id"], checks=checks,
                required_passed=bool(row["required_passed"]),
                blockers=_loads_list(row["blockers"]),
                unresolved_unknowns=_loads_list(row["unresolved_unknowns"]),
                final_status=row["final_status"], timestamp=row["timestamp"],
            ))
        return reports

    # --- ReviewFinding ---

    def save_finding(self, finding: ReviewFinding) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO review_findings
               (id, patch_id, severity, category, evidence_refs, text, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (finding.id, finding.patch_id, finding.severity.value, finding.category,
             _dumps(finding.evidence_refs), finding.text, finding.created_at.isoformat()),
        )
        self._conn.commit()

    def get_findings_for_patch(self, patch_id: str) -> list[ReviewFinding]:
        rows = self._conn.execute(
            "SELECT * FROM review_findings WHERE patch_id = ? ORDER BY created_at", (patch_id,)
        ).fetchall()
        return [ReviewFinding(
            id=row["id"], patch_id=row["patch_id"], severity=row["severity"],
            category=row["category"], evidence_refs=_loads_list(row["evidence_refs"]),
            text=row["text"], created_at=row["created_at"],
        ) for row in rows]

    # --- EvidenceContract ---

    def save_evidence_contract(self, contract: EvidenceContract) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO evidence_contracts
               (change_id, requirement_ids, affected_symbols, supporting_evidence,
                assumptions, expected_behavior_changes, falsification_checks,
                verification_results, unresolved_questions, final_status, complete)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (contract.change_id, _dumps(contract.requirement_ids),
             _dumps(contract.affected_symbols), _dumps(contract.supporting_evidence),
             _dumps(contract.assumptions), _dumps(contract.expected_behavior_changes),
             _dumps(contract.falsification_checks), _dumps(contract.verification_results),
             _dumps(contract.unresolved_questions), contract.final_status.value,
             int(contract.complete)),
        )
        self._conn.commit()

    def get_evidence_contract(self, change_id: str) -> EvidenceContract | None:
        row = self._conn.execute(
            "SELECT * FROM evidence_contracts WHERE change_id = ?", (change_id,)
        ).fetchone()
        if not row:
            return None
        return EvidenceContract(
            change_id=row["change_id"],
            requirement_ids=_loads_list(row["requirement_ids"]),
            affected_symbols=_loads_list(row["affected_symbols"]),
            supporting_evidence=_loads_list(row["supporting_evidence"]),
            assumptions=_loads_list(row["assumptions"]),
            expected_behavior_changes=_loads_list(row["expected_behavior_changes"]),
            falsification_checks=_loads_list(row["falsification_checks"]),
            verification_results=_loads_list(row["verification_results"]),
            unresolved_questions=_loads_list(row["unresolved_questions"]),
            final_status=row["final_status"], complete=bool(row["complete"]),
        )

    # --- ProvenanceEdge ---

    def save_provenance_edge(self, edge: ProvenanceEdge) -> None:
        self._conn.execute(
            """INSERT INTO provenance_edges
               (from_type, from_id, relation, to_type, to_id, metadata)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (edge.from_type, edge.from_id, edge.relation, edge.to_type, edge.to_id,
             _dumps(edge.metadata)),
        )
        self._conn.commit()

    def get_provenance_edges_from(self, from_type: str, from_id: str) -> list[ProvenanceEdge]:
        rows = self._conn.execute(
            "SELECT * FROM provenance_edges WHERE from_type = ? AND from_id = ?",
            (from_type, from_id),
        ).fetchall()
        return [ProvenanceEdge(
            from_type=row["from_type"], from_id=row["from_id"],
            relation=row["relation"], to_type=row["to_type"], to_id=row["to_id"],
            metadata=_loads_dict(row["metadata"]),
        ) for row in rows]

    def get_provenance_edges_to(self, to_type: str, to_id: str) -> list[ProvenanceEdge]:
        rows = self._conn.execute(
            "SELECT * FROM provenance_edges WHERE to_type = ? AND to_id = ?",
            (to_type, to_id),
        ).fetchall()
        return [ProvenanceEdge(
            from_type=row["from_type"], from_id=row["from_id"],
            relation=row["relation"], to_type=row["to_type"], to_id=row["to_id"],
            metadata=_loads_dict(row["metadata"]),
        ) for row in rows]

    # --- RunEvent (append-only) ---

    def save_event(self, event: RunEvent) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO run_events
               (id, run_id, task_id, state, event_type, payload, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event.id, event.run_id, event.task_id, event.state.value,
             event.event_type, _dumps(event.payload), event.timestamp.isoformat()),
        )
        self._conn.commit()

    def get_events_for_run(self, run_id: str) -> list[RunEvent]:
        rows = self._conn.execute(
            "SELECT * FROM run_events WHERE run_id = ? ORDER BY timestamp", (run_id,)
        ).fetchall()
        return [RunEvent(
            id=row["id"], run_id=row["run_id"], task_id=row["task_id"],
            state=row["state"], event_type=row["event_type"],
            payload=_loads_dict(row["payload"]), timestamp=row["timestamp"],
        ) for row in rows]

    # --- FinalDecision ---

    def save_final_decision(self, decision: FinalDecision) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO final_decisions
               (task_id, status, blockers, waived_gates, summary, provenance_id, decided_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (decision.task_id, decision.status.value, _dumps(decision.blockers),
             _dumps(decision.waived_gates), decision.summary, decision.provenance_id,
             decision.decided_at.isoformat()),
        )
        self._conn.commit()

    def get_final_decision(self, task_id: str) -> FinalDecision | None:
        row = self._conn.execute(
            "SELECT * FROM final_decisions WHERE task_id = ?", (task_id,)
        ).fetchone()
        if not row:
            return None
        return FinalDecision(
            task_id=row["task_id"], status=row["status"],
            blockers=_loads_list(row["blockers"]),
            waived_gates=_loads_list(row["waived_gates"]),
            summary=row["summary"], provenance_id=row["provenance_id"],
            decided_at=row["decided_at"],
        )
