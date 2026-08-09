"""REST API routes for VSRS."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from vsrs.api.deps import get_config, get_store
from vsrs.api.models import (
    BenchmarkListResponse,
    ConfigResponse,
    ConfigValidationResponse,
    ErrorResponse,
    EvidenceResponse,
    ExportResponse,
    HistoryResponse,
    PatchResponse,
    ProvenanceResponse,
    ReportResponse,
    ReviewResponse,
    RunListResponse,
    RunRequest,
    RunResponse,
    TaskResponse,
    VerificationResponse,
)
from vsrs.core.config import VSRSConfig
from vsrs.core.ids import generate_id, generate_run_id, generate_task_id
from vsrs.core.schemas import (
    RepositorySnapshot,
    RiskLevel,
    Task,
    TaskType,
)
from vsrs.core.store import Store
from vsrs.eval.tasks import BenchmarkSet
from vsrs.provenance import ProvenanceStore
from vsrs.training.export import TrajectoryExporter

router = APIRouter()


def _require_run(store: Store, run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run


# --- Runs ---


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Page size"),
    store: Store = Depends(get_store),
) -> RunListResponse:
    """List all runs with pagination."""
    runs = store.list_all_runs(limit=limit, offset=offset)
    total = store.count_runs()
    return RunListResponse(
        runs=[
            {
                "run_id": r.id,
                "task_id": r.task_id,
                "state": r.state.value,
                "started_at": str(r.started_at),
                "attempt_no": r.attempt_no,
                "max_attempts": r.max_attempts,
                "finished_at": str(r.finished_at) if r.finished_at else None,
                "updated_at": str(r.updated_at) if r.updated_at else None,
            }
            for r in runs
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.post("/runs", response_model=RunResponse)
def create_run(
    req: RunRequest,
    store: Store = Depends(get_store),
    config: VSRSConfig = Depends(get_config),
) -> RunResponse:
    """Start a new task run and execute the pipeline."""
    import subprocess
    from pathlib import Path

    repo_path = Path(req.repo_path)
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail=f"Repository not found: {req.repo_path}")

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_path, capture_output=True, text=True
    )
    commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"

    repo_snapshot = RepositorySnapshot(
        id=generate_id("repo"),
        root=str(repo_path.resolve()),
        commit_hash=commit_hash,
    )

    task = Task(
        id=generate_task_id(),
        repo_snapshot_id=repo_snapshot.id,
        type=TaskType(req.task_type),
        instruction=req.task_instruction,
        acceptance_criteria=req.acceptance_criteria,
        risk_level=RiskLevel(req.risk),
    )

    run_id = generate_run_id()
    from vsrs.core.schemas import TaskRun, TaskState
    run = TaskRun(
        id=run_id,
        task_id=task.id,
        repo_snapshot_id=repo_snapshot.id,
        state=TaskState.intake,
    )

    store.save_repository(repo_snapshot)
    store.save_task(task)
    store.save_run(run)

    # Execute pipeline
    from vsrs.orchestrator import Orchestrator, OrchestratorConfig
    from vsrs.api.websocket import manager as ws_manager

    orch = Orchestrator(
        OrchestratorConfig(),
        store=store,
        vsrs_config=config,
        ws_manager=ws_manager,
    )
    pipeline_result = orch.run(task, repo_path, repo_snapshot, run_id=run_id)
    store.save_run(pipeline_result.run)

    return RunResponse(
        run_id=pipeline_result.run.id,
        task_id=task.id,
        state=pipeline_result.run.state.value,
        started_at=str(pipeline_result.run.started_at),
        attempt_no=pipeline_result.run.attempt_no,
        max_attempts=pipeline_result.run.max_attempts,
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str, store: Store = Depends(get_store)) -> RunResponse:
    """Get run status."""
    run = _require_run(store, run_id)
    return RunResponse(
        run_id=run.id,
        task_id=run.task_id,
        state=run.state.value,
        started_at=str(run.started_at),
        attempt_no=run.attempt_no,
        max_attempts=run.max_attempts,
    )


@router.delete("/runs/{run_id}")
def delete_run(run_id: str, store: Store = Depends(get_store)) -> dict:
    """Delete a run and its associated data."""
    run = _require_run(store, run_id)
    store.delete_run(run_id)
    return {"deleted": True, "run_id": run_id}


@router.get("/runs/{run_id}/events")
def get_run_events(run_id: str, store: Store = Depends(get_store)) -> dict:
    """Get events for a run."""
    _require_run(store, run_id)
    events = store.get_events_for_run(run_id)
    return {"events": [e.model_dump(mode="json") for e in events], "total": len(events)}


@router.get("/runs/{run_id}/task", response_model=TaskResponse)
def get_run_task(run_id: str, store: Store = Depends(get_store)) -> TaskResponse:
    """Get the task for a run."""
    run = _require_run(store, run_id)
    task = store.get_task(run.task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {run.task_id}")
    return TaskResponse(
        id=task.id,
        type=task.type.value,
        risk_level=task.risk_level.value,
        instruction=task.instruction,
        acceptance_criteria=task.acceptance_criteria,
        required_gates=task.required_gates,
    )


@router.get("/runs/{run_id}/evidence", response_model=EvidenceResponse)
def get_run_evidence(run_id: str, store: Store = Depends(get_store)) -> EvidenceResponse:
    """Get evidence items for a run."""
    run = _require_run(store, run_id)
    items = store.get_evidence_for_task(run.task_id)
    return EvidenceResponse(items=[e.model_dump(mode="json") for e in items])


@router.get("/runs/{run_id}/diff", response_model=PatchResponse)
def get_run_diff(run_id: str, store: Store = Depends(get_store)) -> PatchResponse:
    """Get the latest patch diff for a run."""
    run = _require_run(store, run_id)
    patches = store.get_patches_for_task(run.task_id)
    if not patches:
        raise HTTPException(status_code=404, detail="No patches recorded")
    latest = patches[-1]
    return PatchResponse(
        id=latest.id,
        attempt_no=latest.attempt_no,
        base_commit=latest.base_commit,
        diff=latest.diff,
        changed_files=latest.changed_files,
        assumptions=latest.assumptions,
    )


@router.get("/runs/{run_id}/verify", response_model=VerificationResponse)
def get_run_verification(run_id: str, store: Store = Depends(get_store)) -> VerificationResponse:
    """Get verification report for a run."""
    run = _require_run(store, run_id)
    patches = store.get_patches_for_task(run.task_id)
    if not patches:
        raise HTTPException(status_code=404, detail="No patches recorded")
    latest = patches[-1]
    reports = store.get_verification_reports(latest.id)
    if not reports:
        raise HTTPException(status_code=404, detail="No verification reports")
    latest_report = reports[-1]
    return VerificationResponse(
        checks=[c.model_dump(mode="json") for c in latest_report.checks],
        required_passed=latest_report.required_passed,
        final_status=latest_report.final_status.value,
        blockers=latest_report.blockers,
        unresolved_unknowns=latest_report.unresolved_unknowns,
    )


@router.get("/runs/{run_id}/review", response_model=ReviewResponse)
def get_run_review(run_id: str, store: Store = Depends(get_store)) -> ReviewResponse:
    """Get critic findings and final decision for a run."""
    run = _require_run(store, run_id)
    patches = store.get_patches_for_task(run.task_id)
    findings: list[dict[str, Any]] = []
    if patches:
        latest = patches[-1]
        raw_findings = store.get_findings_for_patch(latest.id)
        findings = [f.model_dump(mode="json") for f in raw_findings]

    decision = store.get_final_decision(run.task_id)
    return ReviewResponse(
        findings=findings,
        final_decision=decision.model_dump(mode="json") if decision else None,
    )


@router.get("/runs/{run_id}/provenance", response_model=ProvenanceResponse)
def get_run_provenance(
    run_id: str,
    format: str = Query("tree", description="Output format: tree, summary"),
    store: Store = Depends(get_store),
) -> ProvenanceResponse:
    """Get provenance graph for a run."""
    run = _require_run(store, run_id)
    prov = ProvenanceStore(store)

    if format == "summary":
        summary = prov.summary("run", run_id)
        return ProvenanceResponse(
            edges=[],
            summary={
                "total_edges": summary.total_edges,
                "total_nodes": summary.total_nodes,
                "node_types": summary.node_types,
                "relation_types": summary.relation_types,
                "max_depth": summary.max_depth,
            },
        )
    else:
        edges = prov.trace("run", run_id)
        return ProvenanceResponse(edges=[e.model_dump() for e in edges])


@router.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_run_report(run_id: str, store: Store = Depends(get_store)) -> str:
    """Generate a markdown report for a run."""
    run = _require_run(store, run_id)
    task = store.get_task(run.task_id)
    evidence_items = store.get_evidence_for_task(run.task_id)
    patches = store.get_patches_for_task(run.task_id)
    events = store.get_events_for_run(run_id)
    decision = store.get_final_decision(run.task_id)

    prov = ProvenanceStore(store)
    graph_summary = prov.summary("run", run_id)

    lines: list[str] = []
    lines.append(f"# VSRS Run Report: {run_id}")
    lines.append(f"\n## Task\n")
    if task:
        lines.append(f"- **ID:** {task.id}")
        lines.append(f"- **Type:** {task.type.value}")
        lines.append(f"- **Instruction:** {task.instruction[:200]}")
    lines.append(f"\n## Run\n")
    lines.append(f"- **State:** {run.state.value}")
    lines.append(f"- **Attempts:** {run.attempt_no}/{run.max_attempts}")
    lines.append(f"\n## Evidence\n")
    lines.append(f"- **Items:** {len(evidence_items)}")
    lines.append(f"\n## Patches\n")
    lines.append(f"- **Total attempts:** {len(patches)}")
    lines.append(f"\n## Events\n")
    lines.append(f"- **Total events:** {len(events)}")
    lines.append(f"\n## Provenance\n")
    lines.append(f"- **Edges:** {graph_summary.total_edges}")
    lines.append(f"- **Nodes:** {graph_summary.total_nodes}")
    lines.append(f"\n## Final Decision\n")
    if decision:
        lines.append(f"- **Status:** {decision.status.value}")
        if decision.summary:
            lines.append(f"- **Summary:** {decision.summary}")
    else:
        lines.append("- No final decision recorded.")

    return "\n".join(lines)


@router.get("/runs/{run_id}/export", response_model=ExportResponse)
def export_run(run_id: str, store: Store = Depends(get_store)) -> ExportResponse:
    """Export a run as a training trajectory."""
    run = _require_run(store, run_id)
    exporter = TrajectoryExporter(store)
    trajectory = exporter.export_run(run_id)
    if not trajectory:
        raise HTTPException(status_code=500, detail="Failed to export trajectory")
    return ExportResponse(trajectory=trajectory)


# --- Tasks ---


@router.get("/tasks/{task_id}/history", response_model=HistoryResponse)
def get_task_history(task_id: str, store: Store = Depends(get_store)) -> HistoryResponse:
    """Get run history for a task."""
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    runs = store.get_runs_for_task(task_id)
    return HistoryResponse(
        task_id=task_id,
        runs=[r.model_dump(mode="json") for r in runs],
    )


# --- Config ---


@router.get("/config", response_model=ConfigResponse)
def get_config_endpoint(config: VSRSConfig = Depends(get_config)) -> ConfigResponse:
    """Get current configuration."""
    return ConfigResponse(config=config.to_dict())


@router.post("/config/validate", response_model=ConfigValidationResponse)
def validate_config(config: VSRSConfig = Depends(get_config)) -> ConfigValidationResponse:
    """Validate configuration."""
    errors = config.validate()
    return ConfigValidationResponse(valid=len(errors) == 0, errors=errors)


# --- Benchmarks ---


@router.get("/benchmarks", response_model=BenchmarkListResponse)
def list_benchmarks() -> BenchmarkListResponse:
    """List all benchmark tasks."""
    bench = BenchmarkSet.seed()
    tasks = bench.all()
    return BenchmarkListResponse(
        tasks=[
            {
                "id": t.id,
                "name": t.name,
                "type": t.task_type.value,
                "risk": t.risk_level.value,
                "difficulty": t.difficulty,
                "tags": t.tags,
            }
            for t in tasks
        ]
    )


# --- LLM ---


@router.get("/llm/models")
def list_llm_models(config: VSRSConfig = Depends(get_config)) -> dict:
    """List available LLM models from the configured provider."""
    provider = config.model.provider
    if provider in ("stub", "", None):
        return {"provider": "stub", "models": [], "connected": True}
    try:
        from vsrs.llm.client import create_client
        client = create_client(
            provider=provider,
            model=config.model.model_name or None,
            base_url=config.model.base_url,
        )
        if hasattr(client, "list_models"):
            models = client.list_models()
        else:
            models = []
        return {"provider": provider, "models": models, "connected": len(models) > 0}
    except Exception as e:
        return {"provider": provider, "models": [], "connected": False, "error": str(e)}


@router.get("/llm/status")
def llm_status(config: VSRSConfig = Depends(get_config)) -> dict:
    """Get LLM provider status."""
    provider = config.model.provider
    base_url = config.model.base_url
    model_name = config.model.model_name
    return {
        "provider": provider,
        "model": model_name,
        "base_url": base_url,
        "max_tokens": config.model.max_tokens,
        "temperature": config.model.temperature,
    }


# --- Stats ---


@router.get("/stats")
def get_stats(store: Store = Depends(get_store)) -> dict:
    """Get dashboard statistics."""
    total_runs = store.count_runs()
    all_runs = store.list_all_runs(limit=1000, offset=0)
    states: dict[str, int] = {}
    for run in all_runs:
        state = run.state.value
        states[state] = states.get(state, 0) + 1
    verified = states.get("verified", 0)
    rejected = states.get("rejected", 0)
    needs_review = states.get("needs_review", 0)
    failed = states.get("failed", 0)
    return {
        "total_runs": total_runs,
        "states": states,
        "verified": verified,
        "rejected": rejected,
        "needs_review": needs_review,
        "failed": failed,
        "success_rate": round(verified / total_runs * 100, 1) if total_runs > 0 else 0,
    }
