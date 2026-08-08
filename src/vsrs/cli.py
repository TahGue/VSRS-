"""CLI entry point for VSRS.

Implements Section 18.1: CLI-first interface.
Commands: run, status, evidence, diff, verify, export, benchmark
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from vsrs.core.config import VSRSConfig
from vsrs.core.ids import generate_run_id, generate_task_id, generate_id
from vsrs.core.logging import setup_logging
from vsrs.core.schemas import RepositorySnapshot, Task, TaskRun, TaskState, TaskType, RiskLevel, FinalStatus
from vsrs.core.state import TaskStateMachine
from vsrs.core.store import Store
from vsrs.eval.tasks import BenchmarkSet
from vsrs.provenance import EvidenceGraph, ProvenanceStore

app = typer.Typer(
    name="vsrs",
    help="Verified Software Reasoning System - evidence-grounded coding reasoning",
    no_args_is_help=True,
)
benchmark_app = typer.Typer(help="Benchmark task management")
app.add_typer(benchmark_app, name="benchmark")

console = Console()


def _get_config() -> VSRSConfig:
    config = VSRSConfig.default()
    config.ensure_dirs()
    setup_logging(level=config.log_level, log_dir=config.log_dir)
    return config


def _get_store(config: VSRSConfig) -> Store:
    return Store(config.database.url)


@app.command()
def run(
    repo: Path = typer.Option(..., "--repo", "-r", help="Path to the repository"),
    task: Path = typer.Option(..., "--task", "-t", help="Path to task definition file (JSON or Markdown)"),
    task_type: str = typer.Option("bugfix", "--type", help="Task type: bugfix, feature, refactor, test, security, migration"),
    risk: str = typer.Option("low", "--risk", help="Risk level: low, medium, high"),
) -> None:
    """Start a new task run on a repository."""

    config = _get_config()

    # Load task definition
    if task.suffix == ".json":
        with open(task) as f:
            task_data = json.load(f)
        instruction = task_data.get("instruction", task_data.get("description", ""))
        acceptance_criteria = task_data.get("acceptance_criteria", [])
    else:
        instruction = task.read_text()
        acceptance_criteria = []

    # Create repository snapshot
    import subprocess
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    )
    commit_hash = result.stdout.strip() if result.returncode == 0 else "unknown"

    repo_snapshot = RepositorySnapshot(
        id=generate_id("repo"),
        root=str(repo.resolve()),
        commit_hash=commit_hash,
    )

    # Create task
    task_obj = Task(
        id=generate_task_id(),
        repo_snapshot_id=repo_snapshot.id,
        type=TaskType(task_type),
        instruction=instruction,
        acceptance_criteria=acceptance_criteria,
        risk_level=RiskLevel(risk),
    )

    # Create run
    run_id = generate_run_id()
    run = TaskRun(
        id=run_id,
        task_id=task_obj.id,
        repo_snapshot_id=repo_snapshot.id,
        state=TaskState.intake,
    )

    # Persist
    with _get_store(config) as store:
        store.save_repository(repo_snapshot)
        store.save_task(task_obj)
        store.save_run(run)

    console.print(Panel(
        f"[bold green]Task run created[/bold green]\n\n"
        f"Run ID: [cyan]{run_id}[/cyan]\n"
        f"Task ID: [cyan]{task_obj.id}[/cyan]\n"
        f"Repository: {repo}\n"
        f"Commit: {commit_hash[:8]}\n"
        f"Type: {task_type}\n"
        f"Risk: {risk}\n"
        f"State: [yellow]intake[/yellow]",
        title="VSRS Run Started",
    ))

    # Execute pipeline
    from vsrs.orchestrator import Orchestrator, OrchestratorConfig

    console.print("\n[dim]Starting pipeline execution...[/dim]")
    orch = Orchestrator(OrchestratorConfig())
    try:
        pipeline_result = orch.run(task_obj, Path(repo), repo_snapshot, run_id=run_id)

        # Update persisted run with final state
        with _get_store(config) as store:
            store.save_run(pipeline_result.run)

        final_state = pipeline_result.run.state.value
        succeeded = pipeline_result.succeeded

        if succeeded:
            console.print(f"\n[bold green]Pipeline completed successfully![/bold green]")
            console.print(f"  Final state: [green]{final_state}[/green]")
            console.print(f"  Stages: {len(pipeline_result.stages)}")
            console.print(f"  Duration: {pipeline_result.total_duration:.2f}s")
        else:
            console.print(f"\n[bold yellow]Pipeline finished without success.[/bold yellow]")
            console.print(f"  Final state: [yellow]{final_state}[/yellow]")
            console.print(f"  Stages: {len(pipeline_result.stages)}")
            for s in pipeline_result.stages:
                status_str = "[green]OK[/green]" if s.success else "[red]FAIL[/red]"
                console.print(f"    {status_str} {s.stage} ({s.duration_seconds:.2f}s)")
                if s.error:
                    console.print(f"       [red]Error: {s.error}[/red]")

        console.print(f"\nCheck status with: [dim]vsrs status {run_id}[/dim]")
    except Exception as e:
        console.print(f"\n[bold red]Pipeline error:[/bold red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        console.print(f"\nCheck status with: [dim]vsrs status {run_id}[/dim]")


@app.command()
def status(
    run_id: str = typer.Argument(..., help="Run ID to check"),
) -> None:
    """Check the status of a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        task = store.get_task(run.task_id)
        repo = store.get_repository(run.repo_snapshot_id)

    table = Table(title=f"Run Status: {run_id}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Run ID", run.id)
    table.add_row("Task ID", run.task_id)
    table.add_row("State", f"[{'green' if run.state == 'verified' else 'yellow'}]{run.state.value}[/]")
    table.add_row("Attempt", f"{run.attempt_no} / {run.max_attempts}")
    table.add_row("Started", str(run.started_at))
    table.add_row("Updated", str(run.updated_at))
    table.add_row("Finished", str(run.finished_at) if run.finished_at else "-")

    if task:
        table.add_row("Type", task.type.value)
        table.add_row("Risk", task.risk_level.value)
        table.add_row("Instruction", task.instruction[:100] + "..." if len(task.instruction) > 100 else task.instruction)

    if repo:
        table.add_row("Repository", repo.root)
        table.add_row("Commit", repo.commit_hash[:12])

    if run.final_decision:
        table.add_row("Final Status", run.final_decision.status.value)
        table.add_row("Summary", run.final_decision.summary[:100] if run.final_decision.summary else "-")

    console.print(table)


@app.command()
def evidence(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """View evidence for a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        evidence_items = store.get_evidence_for_task(run.task_id)
        patches = store.get_patches_for_task(run.task_id)

    if not evidence_items and not patches:
        console.print("[yellow]No evidence recorded yet.[/yellow]")
        return

    if evidence_items:
        table = Table(title="Evidence Items")
        table.add_column("ID", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Source", style="white")
        table.add_column("Locator", style="dim")
        table.add_column("State", style="green")

        for ev in evidence_items:
            table.add_row(ev.id, ev.type.value, ev.source, ev.locator, ev.state.value)

        console.print(table)

    if patches:
        console.print(f"\n[bold]Patch Candidates:[/bold] {len(patches)}")
        for p in patches:
            console.print(f"  Attempt {p.attempt_no}: {p.id} ({len(p.changed_files)} files changed)")


@app.command()
def diff(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """View the latest patch diff for a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        patches = store.get_patches_for_task(run.task_id)

    if not patches:
        console.print("[yellow]No patches recorded yet.[/yellow]")
        return

    latest = patches[-1]
    console.print(Panel(
        f"Attempt {latest.attempt_no} | Base: {latest.base_commit[:12]} | ID: {latest.id}",
        title="Patch Diff",
    ))

    if latest.diff:
        syntax = Syntax(latest.diff, "diff", theme="monokai", line_numbers=True)
        console.print(syntax)
    else:
        console.print("[dim]No diff content.[/dim]")

    if latest.changed_files:
        console.print("\n[bold]Changed files:[/bold]")
        for f in latest.changed_files:
            console.print(f"  {f}")

    if latest.assumptions:
        console.print("\n[bold]Assumptions:[/bold]")
        for a in latest.assumptions:
            console.print(f"  - {a}")


@app.command()
def verify(
    run_id: str = typer.Argument(..., help="Run ID"),
    rerun: bool = typer.Option(False, "--rerun", help="Re-run verification"),
) -> None:
    """View or re-run verification for a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        patches = store.get_patches_for_task(run.task_id)

    if not patches:
        console.print("[yellow]No patches to verify.[/yellow]")
        return

    latest = patches[-1]

    with _get_store(config) as store:
        reports = store.get_verification_reports(latest.id)

    if not reports:
        console.print("[yellow]No verification reports yet.[/yellow]")
        if not rerun:
            console.print("Use --rerun to trigger verification.")
        return

    latest_report = reports[-1]

    table = Table(title=f"Verification Report (patch: {latest.id})")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Exit Code", style="dim")
    table.add_column("Duration", style="dim")

    for check in latest_report.checks:
        status_color = "green" if check.status.value == "pass" else "red"
        table.add_row(
            check.check_type,
            f"[{status_color}]{check.status.value}[/]",
            str(check.exit_code) if check.exit_code is not None else "-",
            f"{check.duration_seconds:.2f}s",
        )

    console.print(table)

    console.print(f"\n[bold]Required passed:[/bold] {'✓' if latest_report.required_passed else '✗'}")
    console.print(f"[bold]Final status:[/bold] {latest_report.final_status.value}")

    if latest_report.blockers:
        console.print("\n[bold red]Blockers:[/bold red]")
        for b in latest_report.blockers:
            console.print(f"  - {b}")

    if latest_report.unresolved_unknowns:
        console.print("\n[bold yellow]Unresolved unknowns:[/bold yellow]")
        for u in latest_report.unresolved_unknowns:
            console.print(f"  - {u}")


@app.command()
def export(
    run_id: str = typer.Argument(..., help="Run ID"),
    format: str = typer.Option("training-jsonl", "--format", "-f", help="Export format: training-jsonl, json"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Export a task run as a training trajectory."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        task = store.get_task(run.task_id)
        evidence_items = store.get_evidence_for_task(run.task_id)
        patches = store.get_patches_for_task(run.task_id)
        hypotheses = store.get_hypotheses_for_task(run.task_id)
        events = store.get_events_for_run(run_id)
        decision = store.get_final_decision(run.task_id)

    trajectory = {
        "run_id": run_id,
        "task": task.model_dump(mode="json") if task else None,
        "hypotheses": [h.model_dump(mode="json") for h in hypotheses],
        "evidence": [e.model_dump(mode="json") for e in evidence_items],
        "patch_attempts": [p.model_dump(mode="json") for p in patches],
        "events": [e.model_dump(mode="json") for e in events],
        "final_decision": decision.model_dump(mode="json") if decision else None,
        "final_status": run.state.value,
    }

    if format == "training-jsonl":
        line = json.dumps(trajectory, default=str)
        if output:
            output.write_text(line + "\n")
            console.print(f"[green]Exported to {output}[/green]")
        else:
            console.print(line)
    else:
        if output:
            output.write_text(json.dumps(trajectory, indent=2, default=str))
            console.print(f"[green]Exported to {output}[/green]")
        else:
            console.print(JSON(json.dumps(trajectory, default=str)))


@benchmark_app.command("list")
def benchmark_list() -> None:
    """List all benchmark tasks."""

    bench = BenchmarkSet.seed()
    tasks = bench.all()

    table = Table(title=f"Benchmark Tasks ({len(tasks)} total)")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Type", style="magenta")
    table.add_column("Risk", style="yellow")
    table.add_column("Difficulty", style="green")
    table.add_column("Tags", style="dim")

    for t in tasks:
        table.add_row(
            t.id,
            t.name,
            t.task_type.value,
            t.risk_level.value,
            t.difficulty,
            ", ".join(t.tags),
        )

    console.print(table)


@benchmark_app.command("show")
def benchmark_show(
    task_id: str = typer.Argument(..., help="Benchmark task ID"),
) -> None:
    """Show details of a benchmark task."""

    bench = BenchmarkSet.seed()
    task = bench.get(task_id)
    if not task:
        console.print(f"[red]Benchmark task not found: {task_id}[/red]")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold]{task.name}[/bold]\n\n"
        f"ID: {task.id}\n"
        f"Type: {task.task_type.value}\n"
        f"Risk: {task.risk_level.value}\n"
        f"Difficulty: {task.difficulty}\n"
        f"Tags: {', '.join(task.tags)}\n\n"
        f"[bold]Instruction:[/bold]\n{task.instruction}\n\n"
        f"[bold]Acceptance Criteria:[/bold]\n" +
        "\n".join(f"  - {c}" for c in task.acceptance_criteria) +
        f"\n\n[bold]Required Gates:[/bold] {', '.join(task.required_gates)}\n"
        f"[bold]Hidden Tests:[/bold] {len(task.hidden_tests)}",
        title=f"Benchmark Task: {task.id}",
    ))


@benchmark_app.command("save")
def benchmark_save(
    output_dir: Path = typer.Option(Path("./benchmark_tasks"), "--output", "-o", help="Output directory"),
) -> None:
    """Save seed benchmark tasks to a directory as JSON files."""

    bench = BenchmarkSet.seed()
    bench.save_to_directory(output_dir)
    console.print(f"[green]Saved {len(bench)} benchmark tasks to {output_dir}/[/green]")


@app.command()
def audit_trail(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """View the provenance audit trail for a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        prov = ProvenanceStore(store)
        entries = prov.audit_trail("run", run_id)

    if not entries:
        console.print("[yellow]No provenance edges recorded for this run.[/yellow]")
        return

    console.print(Panel(
        f"[bold]Audit Trail for Run: {run_id}[/bold]\n"
        f"[dim]{len(entries)} edges[/dim]",
        title="Provenance Audit Trail",
    ))

    for entry in entries:
        console.print(entry.describe())


@app.command()
def history(
    task_id: str = typer.Argument(..., help="Task ID"),
) -> None:
    """View run history for a task."""

    config = _get_config()
    with _get_store(config) as store:
        task = store.get_task(task_id)
        if not task:
            console.print(f"[red]Task not found: {task_id}[/red]")
            raise typer.Exit(1)

        runs = store.get_runs_for_task(task_id)

    console.print(Panel(
        f"[bold]Task: {task.instruction[:80]}[/bold]\n"
        f"Type: {task.type.value} | Risk: {task.risk_level.value}\n"
        f"Total runs: {len(runs)}",
        title=f"Run History: {task_id}",
    ))

    if not runs:
        console.print("[yellow]No runs recorded.[/yellow]")
        return

    table = Table(title="Runs")
    table.add_column("Run ID", style="cyan")
    table.add_column("State", style="white")
    table.add_column("Attempt", style="dim")
    table.add_column("Started", style="dim")
    table.add_column("Finished", style="dim")
    table.add_column("Decision", style="green")

    for run in runs:
        state_color = "green" if run.state == "verified" else ("red" if run.state == "rejected" else "yellow")
        decision = run.final_decision.status.value if run.final_decision else "-"
        table.add_row(
            run.id,
            f"[{state_color}]{run.state.value}[/]",
            f"{run.attempt_no}/{run.max_attempts}",
            str(run.started_at),
            str(run.finished_at) if run.finished_at else "-",
            decision,
        )

    console.print(table)


@app.command()
def review(
    run_id: str = typer.Argument(..., help="Run ID"),
) -> None:
    """View critic findings and review decision for a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        patches = store.get_patches_for_task(run.task_id)
        decision = store.get_final_decision(run.task_id)

    if not patches:
        console.print("[yellow]No patches to review.[/yellow]")
        return

    latest = patches[-1]

    with _get_store(config) as store:
        findings = store.get_findings_for_patch(latest.id)

    console.print(Panel(
        f"[bold]Review for Run: {run_id}[/bold]\n"
        f"Patch: {latest.id} (attempt {latest.attempt_no})\n"
        f"Findings: {len(findings)}",
        title="Critic Review",
    ))

    if findings:
        table = Table(title="Findings")
        table.add_column("ID", style="cyan")
        table.add_column("Severity", style="white")
        table.add_column("Category", style="magenta")
        table.add_column("Message", style="white")

        for f in findings:
            sev_color = {
                "blocker": "bold red",
                "major": "red",
                "minor": "yellow",
                "question": "blue",
                "suggestion": "dim",
            }.get(f.severity.value, "white")
            table.add_row(
                f.id,
                f"[{sev_color}]{f.severity.value}[/]",
                f.category,
                f.text[:100],
            )

        console.print(table)
    else:
        console.print("[green]No findings — clean review.[/green]")

    if decision:
        console.print(f"\n[bold]Final Decision:[/bold] {decision.status.value}")
        if decision.blockers:
            console.print("[bold red]Blockers:[/bold red]")
            for b in decision.blockers:
                console.print(f"  - {b}")
        if decision.summary:
            console.print(f"\n[bold]Summary:[/bold]\n{decision.summary}")


@app.command()
def report(
    run_id: str = typer.Argument(..., help="Run ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Generate a summary report for a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

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
        lines.append(f"- **Risk:** {task.risk_level.value}")
        lines.append(f"- **Instruction:** {task.instruction[:200]}")
        if task.acceptance_criteria:
            lines.append(f"- **Acceptance Criteria:**")
            for c in task.acceptance_criteria:
                lines.append(f"  - {c}")

    lines.append(f"\n## Run\n")
    lines.append(f"- **State:** {run.state.value}")
    lines.append(f"- **Attempts:** {run.attempt_no}/{run.max_attempts}")
    lines.append(f"- **Started:** {run.started_at}")
    lines.append(f"- **Finished:** {run.finished_at or '-'}")

    lines.append(f"\n## Evidence\n")
    lines.append(f"- **Items:** {len(evidence_items)}")
    for ev in evidence_items[:10]:
        lines.append(f"  - {ev.type.value}: {ev.locator} ({ev.state.value})")

    lines.append(f"\n## Patches\n")
    lines.append(f"- **Total attempts:** {len(patches)}")
    for p in patches:
        lines.append(f"  - Attempt {p.attempt_no}: {p.id} ({len(p.changed_files)} files)")

    lines.append(f"\n## Events\n")
    lines.append(f"- **Total events:** {len(events)}")
    for e in events[-10:]:
        lines.append(f"  - {e.state}: {e.event_type}")

    lines.append(f"\n## Provenance\n")
    lines.append(f"- **Edges:** {graph_summary.total_edges}")
    lines.append(f"- **Nodes:** {graph_summary.total_nodes}")
    lines.append(f"- **Node types:** {', '.join(f'{k}={v}' for k, v in graph_summary.node_types.items())}")
    lines.append(f"- **Max depth:** {graph_summary.max_depth}")

    lines.append(f"\n## Final Decision\n")
    if decision:
        lines.append(f"- **Status:** {decision.status.value}")
        if decision.blockers:
            lines.append(f"- **Blockers:** {', '.join(decision.blockers)}")
        if decision.summary:
            lines.append(f"- **Summary:** {decision.summary}")
    else:
        lines.append("- No final decision recorded.")

    report_text = "\n".join(lines)

    if output:
        output.write_text(report_text)
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        console.print(report_text)


@app.command()
def provenance(
    run_id: str = typer.Argument(..., help="Run ID"),
    format: str = typer.Option("tree", "--format", "-f", help="Output format: tree, json, summary"),
) -> None:
    """View the provenance graph for a task run."""

    config = _get_config()
    with _get_store(config) as store:
        run = store.get_run(run_id)
        if not run:
            console.print(f"[red]Run not found: {run_id}[/red]")
            raise typer.Exit(1)

        prov = ProvenanceStore(store)

        if format == "summary":
            summary = prov.summary("run", run_id)
            console.print(Panel(
                f"Edges: {summary.total_edges}\n"
                f"Nodes: {summary.total_nodes}\n"
                f"Max depth: {summary.max_depth}\n"
                f"Node types: {', '.join(f'{k}={v}' for k, v in summary.node_types.items())}\n"
                f"Relations: {', '.join(f'{k}={v}' for k, v in summary.relation_types.items())}",
                title=f"Provenance Summary: {run_id}",
            ))
        elif format == "json":
            edges = prov.trace("run", run_id)
            data = [e.model_dump() for e in edges]
            console.print(JSON(json.dumps(data, default=str)))
        else:
            entries = prov.audit_trail("run", run_id)
            if not entries:
                console.print("[yellow]No provenance edges for this run.[/yellow]")
                return
            console.print(Panel(
                f"[bold]Provenance Graph: {run_id}[/bold]\n"
                f"[dim]{len(entries)} edges[/dim]",
                title="Provenance Tree",
            ))
            for entry in entries:
                console.print(entry.describe())


config_app = typer.Typer(help="Configuration management")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
) -> None:
    """Show the current configuration."""

    config = VSRSConfig.load(config_path)
    console.print(Panel(
        config.to_yaml(),
        title="VSRS Configuration",
    ))


@config_app.command("init")
def config_init(
    output: Path = typer.Option(Path("vsrs.yaml"), "--output", "-o", help="Output file path"),
) -> None:
    """Initialize a new configuration file with defaults."""

    config = VSRSConfig()
    config.save_yaml(output)
    console.print(f"[green]Configuration saved to {output}[/green]")


@config_app.command("validate")
def config_validate(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Path to config file"),
) -> None:
    """Validate a configuration file."""

    config = VSRSConfig.load(config_path)
    errors = config.validate()

    if errors:
        console.print("[bold red]Configuration is invalid:[/bold red]")
        for err in errors:
            console.print(f"  [red]- {err}[/red]")
        raise typer.Exit(1)
    else:
        console.print("[green]Configuration is valid.[/green]")


# --- Enterprise CLI ---

tenant_app = typer.Typer(help="Tenant management")
app.add_typer(tenant_app, name="tenant")

sso_app = typer.Typer(help="SSO provider management")
app.add_typer(sso_app, name="sso")

pool_app = typer.Typer(help="Worker pool status")
app.add_typer(pool_app, name="pool")


@tenant_app.command("create")
def tenant_create(
    tenant_id: str = typer.Option(..., "--id", help="Unique tenant ID"),
    name: str = typer.Option(..., "--name", help="Tenant display name"),
    slug: str = typer.Option("", "--slug", help="URL-friendly slug (defaults to id)"),
    max_projects: int = typer.Option(10, "--max-projects", help="Max projects"),
    max_runs_per_day: int = typer.Option(100, "--max-runs-day", help="Max runs per day"),
    max_concurrent_runs: int = typer.Option(5, "--max-concurrent", help="Max concurrent runs"),
    max_storage_mb: int = typer.Option(1024, "--max-storage-mb", help="Max storage in MB"),
    max_api_keys: int = typer.Option(10, "--max-api-keys", help="Max API keys"),
) -> None:
    """Create a new tenant with resource quotas."""

    from vsrs.enterprise import TenantManager, ResourceQuota

    mgr = TenantManager()
    quota = ResourceQuota(
        max_projects=max_projects,
        max_runs_per_day=max_runs_per_day,
        max_concurrent_runs=max_concurrent_runs,
        max_storage_mb=max_storage_mb,
        max_api_keys=max_api_keys,
    )
    tenant = mgr.create_tenant(tenant_id, name, slug or tenant_id, quota=quota)
    console.print(f"[green]Tenant created:[/green] {tenant.id} ({tenant.name})")
    console.print(f"  Status: {tenant.status.value}")
    console.print(f"  Quota: {quota.to_dict()}")


@tenant_app.command("list")
def tenant_list() -> None:
    """List all tenants."""

    from vsrs.enterprise import TenantManager

    mgr = TenantManager()
    tenants = mgr.list_tenants()
    if not tenants:
        console.print("[yellow]No tenants found.[/yellow]")
        return

    table = Table(title="Tenants")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Status", style="green")
    table.add_column("Projects", justify="right")
    table.add_column("Created", style="dim")

    for t in tenants:
        table.add_row(t.id, t.name, t.status.value, str(len(mgr.list_projects(t.id))), t.created_at.isoformat()[:10])

    console.print(table)


@tenant_app.command("show")
def tenant_show(
    tenant_id: str = typer.Argument(..., help="Tenant ID"),
) -> None:
    """Show tenant details and usage."""

    from vsrs.enterprise import TenantManager, TenantNotFoundError

    mgr = TenantManager()
    try:
        tenant = mgr.get_tenant(tenant_id)
    except TenantNotFoundError:
        console.print(f"[red]Tenant not found: {tenant_id}[/red]")
        raise typer.Exit(1)

    console.print(Panel(
        f"ID: {tenant.id}\nName: {tenant.name}\nStatus: {tenant.status.value}\n"
        f"Slug: {tenant.slug}\nCreated: {tenant.created_at.isoformat()}",
        title=f"Tenant: {tenant.name}",
    ))

    usage = mgr.get_usage(tenant_id)
    console.print(f"\n[bold]Usage:[/bold]")
    console.print(f"  Projects: {usage.project_count}")
    console.print(f"  Runs today: {usage.runs_today}")
    console.print(f"  Concurrent runs: {usage.concurrent_runs}")
    console.print(f"  Storage: {usage.storage_used_mb} MB")
    console.print(f"  API keys: {usage.api_key_count}")


@tenant_app.command("suspend")
def tenant_suspend(
    tenant_id: str = typer.Argument(..., help="Tenant ID"),
) -> None:
    """Suspend a tenant."""

    from vsrs.enterprise import TenantManager, TenantNotFoundError

    mgr = TenantManager()
    try:
        mgr.suspend_tenant(tenant_id)
    except TenantNotFoundError:
        console.print(f"[red]Tenant not found: {tenant_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[yellow]Tenant suspended:[/yellow] {tenant_id}")


@tenant_app.command("reactivate")
def tenant_reactivate(
    tenant_id: str = typer.Argument(..., help="Tenant ID"),
) -> None:
    """Reactivate a suspended tenant."""

    from vsrs.enterprise import TenantManager, TenantNotFoundError

    mgr = TenantManager()
    try:
        mgr.reactivate_tenant(tenant_id)
    except TenantNotFoundError:
        console.print(f"[red]Tenant not found: {tenant_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Tenant reactivated:[/green] {tenant_id}")


@tenant_app.command("delete")
def tenant_delete(
    tenant_id: str = typer.Argument(..., help="Tenant ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Delete a tenant and all its projects."""

    if not force:
        confirm = typer.confirm(f"Delete tenant '{tenant_id}' and all its projects?")
        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            raise typer.Exit(0)

    from vsrs.enterprise import TenantManager, TenantNotFoundError

    mgr = TenantManager()
    try:
        mgr.delete_tenant(tenant_id)
    except TenantNotFoundError:
        console.print(f"[red]Tenant not found: {tenant_id}[/red]")
        raise typer.Exit(1)
    console.print(f"[red]Tenant deleted:[/red] {tenant_id}")


@sso_app.command("list-providers")
def sso_list_providers() -> None:
    """List configured SSO providers."""

    from vsrs.enterprise import SSOManager

    mgr = SSOManager()
    providers = mgr.list_providers()
    if not providers:
        console.print("[yellow]No SSO providers configured.[/yellow]")
        return

    table = Table(title="SSO Providers")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Protocol", style="green")

    for p in providers:
        table.add_row(p["id"], p["name"], p["protocol"])

    console.print(table)


@sso_app.command("list-sessions")
def sso_list_sessions() -> None:
    """List active SSO sessions."""

    from vsrs.enterprise import SSOManager

    mgr = SSOManager()
    sessions = mgr.list_active_sessions()
    if not sessions:
        console.print("[yellow]No active SSO sessions.[/yellow]")
        return

    table = Table(title="Active SSO Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("User ID", style="white")
    table.add_column("Provider", style="green")
    table.add_column("Protocol", style="blue")
    table.add_column("Expires", style="dim")

    for s in sessions:
        table.add_row(
            s.id[:16] + "...",
            s.user_id[:16] + "...",
            s.provider_id,
            s.protocol.value,
            s.expires_at.isoformat()[:19] if s.expires_at else "N/A",
        )

    console.print(table)


@sso_app.command("cleanup")
def sso_cleanup() -> None:
    """Remove expired SSO sessions."""

    from vsrs.enterprise import SSOManager

    mgr = SSOManager()
    removed = mgr.cleanup_expired_sessions()
    console.print(f"[green]Removed {removed} expired session(s).[/green]")


@sso_app.command("list-users")
def sso_list_users() -> None:
    """List SSO-provisioned users."""

    from vsrs.enterprise import SSOManager

    mgr = SSOManager()
    users = mgr.list_users()
    if not users:
        console.print("[yellow]No SSO users provisioned.[/yellow]")
        return

    table = Table(title="SSO Users")
    table.add_column("User ID", style="cyan")
    table.add_column("Email", style="white")
    table.add_column("Role", style="green")
    table.add_column("Active", style="blue")

    for u in users:
        table.add_row(u.id[:16] + "...", u.email, u.role, "Yes" if u.active else "No")

    console.print(table)


@pool_app.command("stats")
def pool_stats() -> None:
    """Show worker pool statistics (requires a running pool)."""

    console.print("[yellow]Worker pool stats are available at runtime when a pool is active.[/yellow]")
    console.print("\nTo start a pool programmatically:")
    console.print("""
from vsrs.distributed import WorkerPool, PoolConfig, InMemoryQueue

pool = WorkerPool(InMemoryQueue(), config=PoolConfig(min_workers=2))
pool.start()
print(pool.pool_stats())
pool.stop()
""")


# --- API Key & Audit CLI ---

key_app = typer.Typer(help="API key management")
app.add_typer(key_app, name="key")

audit_app = typer.Typer(help="Audit log management")
app.add_typer(audit_app, name="audit")


@key_app.command("create")
def key_create(
    user_id: str = typer.Option(..., "--user", "-u", help="User ID for this key"),
    name: str = typer.Option("", "--name", "-n", help="Human-readable key name"),
    scopes: str = typer.Option("", "--scopes", "-s", help="Comma-separated scopes (e.g. read,write,admin:all)"),
) -> None:
    """Create a new API key."""

    from vsrs.enterprise import APIKeyManager

    mgr = APIKeyManager()
    scope_list = [s.strip() for s in scopes.split(",") if s.strip()] if scopes else []
    raw_key, api_key = mgr.create_key(user_id=user_id, name=name, scopes=scope_list)
    console.print(f"[green]API key created:[/green] {api_key.id}")
    console.print(f"  User: {api_key.user_id}")
    console.print(f"  Name: {api_key.name}")
    console.print(f"  Scopes: {', '.join(api_key.scopes) if api_key.scopes else '(none)'}")
    console.print(f"\n[bold yellow]Raw key (save this — shown only once):[/bold yellow]")
    console.print(f"  {raw_key}")


@key_app.command("list")
def key_list(
    user_id: str = typer.Option(None, "--user", "-u", help="Filter by user ID"),
) -> None:
    """List API keys."""

    from vsrs.enterprise import APIKeyManager

    mgr = APIKeyManager()
    keys = mgr.list_keys(user_id=user_id)
    if not keys:
        console.print("[yellow]No API keys found.[/yellow]")
        return

    table = Table(title="API Keys")
    table.add_column("ID", style="cyan")
    table.add_column("User", style="white")
    table.add_column("Name", style="green")
    table.add_column("Scopes", style="blue")
    table.add_column("Valid", style="yellow")

    for k in keys:
        table.add_row(
            k.id,
            k.user_id,
            k.name or "(unnamed)",
            ", ".join(k.scopes) if k.scopes else "(none)",
            "Yes" if k.is_valid else "No",
        )

    console.print(table)


@key_app.command("revoke")
def key_revoke(
    key_id: str = typer.Argument(..., help="API key ID to revoke"),
) -> None:
    """Revoke an API key."""

    from vsrs.enterprise import APIKeyManager

    mgr = APIKeyManager()
    revoked = mgr.revoke(key_id)
    if revoked:
        console.print(f"[red]API key revoked:[/red] {key_id}")
    else:
        console.print(f"[yellow]Key not found or already revoked:[/yellow] {key_id}")
        raise typer.Exit(1)


@key_app.command("validate")
def key_validate(
    raw_key: str = typer.Argument(..., help="Raw API key to validate"),
) -> None:
    """Validate an API key."""

    from vsrs.enterprise import APIKeyManager

    mgr = APIKeyManager()
    key = mgr.validate(raw_key)
    if key is None:
        console.print("[red]Invalid or revoked API key.[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Valid API key:[/green] {key.id}")
    console.print(f"  User: {key.user_id}")
    console.print(f"  Name: {key.name}")
    console.print(f"  Scopes: {', '.join(key.scopes) if key.scopes else '(none)'}")


@key_app.command("count")
def key_count() -> None:
    """Count total API keys."""

    from vsrs.enterprise import APIKeyManager

    mgr = APIKeyManager()
    console.print(f"Total API keys: {mgr.count()}")


@audit_app.command("list")
def audit_list(
    event_type: str = typer.Option(None, "--type", "-t", help="Filter by event type"),
    user_id: str = typer.Option(None, "--user", "-u", help="Filter by user ID"),
    resource: str = typer.Option(None, "--resource", "-r", help="Filter by resource"),
    limit: int = typer.Option(20, "--limit", "-l", help="Max events to show"),
) -> None:
    """List audit events with optional filters."""

    from vsrs.enterprise import AuditLogger

    auditor = AuditLogger()
    events = auditor.query(
        event_type=event_type,
        user_id=user_id,
        resource=resource,
        limit=limit,
    )
    if not events:
        console.print("[yellow]No audit events found.[/yellow]")
        return

    table = Table(title=f"Audit Events ({len(events)} shown)")
    table.add_column("Time", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("User", style="white")
    table.add_column("Resource", style="green")
    table.add_column("Success", style="yellow")

    for e in events:
        table.add_row(
            e.timestamp.isoformat()[:19],
            e.event_type,
            e.user_id[:20] if e.user_id else "-",
            e.resource[:30] if e.resource else "-",
            "Yes" if e.success else "No",
        )

    console.print(table)


@audit_app.command("count")
def audit_count() -> None:
    """Count total audit events."""

    from vsrs.enterprise import AuditLogger

    auditor = AuditLogger()
    console.print(f"Total audit events: {auditor.count()}")


@audit_app.command("export")
def audit_export(
    output: Path = typer.Option(Path("audit_export.jsonl"), "--output", "-o", help="Output file path"),
) -> None:
    """Export audit events to JSONL file."""

    from vsrs.enterprise import AuditLogger

    auditor = AuditLogger()
    count = auditor.export_jsonl(output)
    console.print(f"[green]Exported {count} audit events to {output}[/green]")


# --- Role & Rate Limit CLI ---

role_app = typer.Typer(help="RBAC role management")
app.add_typer(role_app, name="role")

ratelimit_app = typer.Typer(help="Rate limit management")
app.add_typer(ratelimit_app, name="ratelimit")


@role_app.command("list")
def role_list() -> None:
    """List all registered roles."""

    from vsrs.enterprise import RoleManager

    mgr = RoleManager()
    roles = mgr.list_roles()
    if not roles:
        console.print("[yellow]No roles found.[/yellow]")
        return

    table = Table(title="Roles")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Permissions", style="green")
    table.add_column("Parent", style="dim")

    for r in roles:
        table.add_row(
            r.name,
            r.description,
            ", ".join(sorted(r.permissions)),
            r.parent or "-",
        )

    console.print(table)


@role_app.command("show")
def role_show(
    name: str = typer.Argument(..., help="Role name"),
) -> None:
    """Show details of a specific role."""

    from vsrs.enterprise import RoleManager

    mgr = RoleManager()
    role = mgr.get(name)
    if role is None:
        console.print(f"[red]Role not found:[/red] {name}")
        raise typer.Exit(1)

    console.print(f"[cyan]Role:[/cyan] {role.name}")
    console.print(f"  Description: {role.description}")
    console.print(f"  Parent: {role.parent or '(none)'}")
    console.print(f"  Permissions ({len(role.permissions)}):")
    for perm in sorted(role.permissions):
        console.print(f"    - {perm}")

    resolved = mgr.resolve_permissions(name)
    if len(resolved) > len(role.permissions):
        console.print(f"  Resolved permissions ({len(resolved)}, including inheritance):")
        for perm in sorted(resolved):
            console.print(f"    - {perm}")


@role_app.command("check")
def role_check(
    role_name: str = typer.Option(..., "--role", "-r", help="Role name"),
    permission: str = typer.Option(..., "--permission", "-p", help="Permission to check"),
) -> None:
    """Check if a role has a specific permission."""

    from vsrs.enterprise import RoleManager

    mgr = RoleManager()
    role = mgr.get(role_name)
    if role is None:
        console.print(f"[red]Role not found:[/red] {role_name}")
        raise typer.Exit(1)

    allowed = mgr.check(role_name, permission)
    if allowed:
        console.print(f"[green]ALLOWED[/green] Role '{role_name}' has permission '{permission}'")
    else:
        console.print(f"[red]DENIED[/red] Role '{role_name}' does not have permission '{permission}'")
        raise typer.Exit(1)


@ratelimit_app.command("usage")
def ratelimit_usage(
    identifier: str = typer.Option("default", "--id", "-i", help="Identifier to check"),
) -> None:
    """Show rate limit usage for an identifier."""

    from vsrs.enterprise import RateLimiter, RateLimitConfig

    limiter = RateLimiter(RateLimitConfig())
    usage = limiter.get_usage(identifier)

    table = Table(title=f"Rate Limit Usage: {identifier}")
    table.add_column("Metric", style="cyan")
    table.add_column("Used", style="white")
    table.add_column("Limit", style="yellow")

    table.add_row("Minute", str(usage["minute_used"]), str(usage["minute_limit"]))
    table.add_row("Hour", str(usage["hour_used"]), str(usage["hour_limit"]))
    table.add_row("Burst remaining", str(usage["burst_remaining"]), str(usage["burst_limit"]))

    console.print(table)


@ratelimit_app.command("config")
def ratelimit_config() -> None:
    """Show rate limit configuration."""

    from vsrs.enterprise import RateLimiter, RateLimitConfig

    limiter = RateLimiter(RateLimitConfig())
    cfg = limiter.config

    console.print(f"[cyan]Requests per minute:[/cyan] {cfg.requests_per_minute}")
    console.print(f"[cyan]Requests per hour:[/cyan] {cfg.requests_per_hour}")
    console.print(f"[cyan]Burst size:[/cyan] {cfg.burst_size}")


@ratelimit_app.command("reset")
def ratelimit_reset(
    identifier: str = typer.Option(None, "--id", "-i", help="Reset only this identifier (default: all)"),
) -> None:
    """Reset rate limit state."""

    from vsrs.enterprise import RateLimiter, RateLimitConfig

    limiter = RateLimiter(RateLimitConfig())
    limiter.reset(identifier)
    if identifier:
        console.print(f"[green]Rate limits reset for:[/green] {identifier}")
    else:
        console.print("[green]All rate limits reset.[/green]")


if __name__ == "__main__":
    app()
