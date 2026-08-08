# Verified Software Reasoning System (VSRS)

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 932](https://img.shields.io/badge/tests-932-brightgreen.svg)](#testing)

An evidence-grounded coding reasoning model and verification platform. Generated code is a hypothesis, not a fact — the system earns a "verified" status only through evidence: repository grounding, deterministic checks, executable tests, and an auditable provenance trail.

## Documentation

- [Architecture](docs/architecture.md) — Pipeline diagrams, module reference, data flow
- [API Reference](docs/api-reference.md) — REST API endpoints with examples
- [Contributing Guide](docs/contributing.md) — Development setup, coding standards, PR process
- [Changelog](docs/changelog.md) — Versioned release history
- [Examples](docs/examples/) — Sample tasks, configs, and walkthroughs
- [Megaplan](MEGAPLAN.md) — Project roadmap and phase breakdown

## Core Thesis

Every patch is a hypothesis that must survive falsification. VSRS coordinates a multi-stage pipeline that grounds reasoning in repository evidence, generates minimal patches, verifies them with deterministic tools, and produces a complete provenance graph linking every decision to its supporting evidence.

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev]"

# Run a task on a repository
vsrs run --repo ./my-repo --task task.md

# Check status
vsrs status <RUN_ID>

# View the provenance audit trail
vsrs audit-trail <RUN_ID>

# Generate a full report
vsrs report <RUN_ID> --output report.md
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `vsrs run --repo <path> --task <file>` | Start a new task run on a repository |
| `vsrs status <RUN_ID>` | Check the status of a task run |
| `vsrs evidence <RUN_ID>` | View evidence items for a run |
| `vsrs diff <RUN_ID>` | View the latest patch diff |
| `vsrs verify <RUN_ID> [--rerun]` | View or re-run verification checks |
| `vsrs audit-trail <RUN_ID>` | View the provenance audit trail |
| `vsrs provenance <RUN_ID> [--format tree\|json\|summary]` | View the provenance graph |
| `vsrs history <TASK_ID>` | View all runs for a task |
| `vsrs review <RUN_ID>` | View critic findings and final decision |
| `vsrs report <RUN_ID> [--output FILE]` | Generate a markdown summary report |
| `vsrs export <RUN_ID> [--format json\|training-jsonl]` | Export a run as a training trajectory |
| `vsrs config show` | Show current configuration |
| `vsrs config init [--output FILE]` | Initialize a config file with defaults |
| `vsrs config validate` | Validate configuration |
| `vsrs benchmark list` | List benchmark tasks |
| `vsrs benchmark show <TASK_ID>` | Show benchmark task details |
| `vsrs benchmark save [--output DIR]` | Save benchmark tasks to files |

## Configuration

VSRS discovers configuration in priority order:

1. `--config` flag on CLI commands
2. `VSRS_CONFIG` environment variable
3. `./vsrs.yaml` or `./vsrs.yml` in current directory
4. `~/.vsrs/config.yaml` or `~/.vsrs/config.yml`
5. Built-in defaults (with env overrides)

```bash
# Initialize a config file
vsrs config init --output vsrs.yaml

# Show current config
vsrs config show

# Validate config
vsrs config validate
```

See `vsrs.example.yaml` for all available options.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `VSRS_CONFIG` | Path to config file |
| `VSRS_DB_PATH` | Database path |
| `VSRS_DB_ECHO` | Enable SQL echo logging |
| `VSRS_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `VSRS_LOG_DIR` | Log directory |
| `VSRS_MODEL_PROVIDER` | Model provider (openai, anthropic) |
| `VSRS_MODEL_NAME` | Model name |
| `VSRS_MODEL_API_KEY_ENV` | Env var name for API key |
| `VSRS_MODEL_BASE_URL` | Custom API base URL |
| `VSRS_MODEL_MAX_TOKENS` | Max tokens |
| `VSRS_MODEL_TEMPERATURE` | Temperature (0.0-2.0) |
| `VSRS_SANDBOX_DOCKER` | Use Docker sandbox (true/false) |
| `VSRS_SANDBOX_WORKTREE_DIR` | Worktree directory |
| `VSRS_SANDBOX_NETWORK_DISABLED` | Disable network in sandbox |
| `VSRS_SANDBOX_WALL_TIME` | Wall time limit in seconds |
| `VSRS_MAX_REPAIR_ATTEMPTS` | Max repair attempts (0-10) |

## Architecture

```
Task Intake
    -> Repository Intelligence (file/symbol/test/dependency/git indexing)
    -> Context & Evidence Builder (structural retrieval, evidence contracts)
    -> Primary Reasoning Model (6-stage protocol: evidence -> hypothesis -> effects -> falsification -> patch)
    -> Sandboxed Patch Application (git worktree, unified diff)
    -> Deterministic Verification (pytest, ruff, mypy, bandit)
    -> Critic / Repair Loop (independent review, structured failures, iterative repair)
    -> Evidence & Provenance Graph (audit trail, traceability)
    -> Result (verified candidate OR needs human review)
```

### Pipeline Stages

| Stage | State | Component | Output |
|-------|-------|-----------|--------|
| Intake | `intake` | Orchestrator | TaskRun, RepositorySnapshot |
| Retrieve | `retrieving` | RepositoryIntelligence | RetrievalResult, EvidenceItems |
| Reason | `reasoning` | Reasoner | ReasoningOutput (evidence summary, hypothesis, effects, falsification, patch proposal) |
| Patch | `patching` | Patcher | PatchCandidate (validated diff) |
| Verify | `verifying` | VerificationRunner | VerificationReport (check results, gate evaluation) |
| Repair | `revising` | RepairLoop | RepairResult (categorized failures, corrected patches) |
| Review | `reviewing` | ReviewService | CriticReport, FinalDecision |

## Module Reference

| Module | Path | Responsibility |
|--------|------|----------------|
| **core** | `src/vsrs/core/` | Schemas, state machine, SQLite store, config, events, IDs, logging, policy |
| **repo** | `src/vsrs/repo/` | File/symbol/test/dependency/git indexing, retrieval, intelligence |
| **reasoning** | `src/vsrs/reasoning/` | Task parser, reasoner, patcher, critic, prompt templates, protocol schemas |
| **verify** | `src/vsrs/verify/` | Sandbox, pytest/lint/type/security adapters, verification runner, gates |
| **repair** | `src/vsrs/repair/` | Failure categorizer, repair loop, repair reasoner |
| **provenance** | `src/vsrs/provenance/` | ProvenanceStore (trace, path, audit), EvidenceGraph, evidence utilities |
| **eval** | `src/vsrs/eval/` | Benchmark tasks, scorer, ablation configs, evaluation reports |
| **training** | `src/vsrs/training/` | Trajectory export, quality filters, dataset builders (SFT, repair, preference) |
| **api** | `src/vsrs/api/` | FastAPI app and routes (stub - Phase 11) |
| **orchestrator** | `src/vsrs/orchestrator.py` | End-to-end pipeline coordinator |
| **cli** | `src/vsrs/cli.py` | CLI entry point with 15+ commands |

## Design Principles

- **P1**: Generated code is a proposal, never labeled correct merely because the model produced it.
- **P2**: Evidence before assertion - important claims must cite retrievable repo facts.
- **P3**: Objective tools outrank model opinion.
- **P4**: Falsifiability - state what would prove the hypothesis wrong.
- **P5**: Minimal change - prefer the smallest sufficient patch.
- **P6**: Separate generation from judgment.
- **P7**: Explicit unknowns - never silently fill in missing information.
- **P8**: Temporal validity - APIs, deps, configs are versioned.
- **P9**: Traceability - every verified conclusion must be traceable.
- **P10**: Human escalation is a valid result.

## Project Structure

```
vsrs/
├── src/vsrs/
│   ├── core/               # State machine, schemas, store, config, events, IDs, logging, policy
│   │   ├── config.py       # VSRSConfig with YAML discovery, env overrides, validation
│   │   ├── events.py       # RunEvent append-only event log
│   │   ├── ids.py          # ID generators (run, task, patch, evidence)
│   │   ├── logging.py      # Structured JSON logging with run IDs
│   │   ├── policy.py       # Policy engine for allowed operations
│   │   ├── schemas.py      # Pydantic models: Task, TaskRun, PatchCandidate, etc.
│   │   ├── state.py        # TaskStateMachine with valid transitions
│   │   └── store.py        # SQLite persistence for all entities
│   ├── repo/               # Repository intelligence
│   │   ├── dependencies.py # Dependency analysis (imports, packages)
│   │   ├── files.py        # File index (tree, extensions, sizes)
│   │   ├── git.py          # Git operations (blame, log, diff)
│   │   ├── intelligence.py # Unified RepositoryModel + retriever
│   │   ├── retrieval.py    # Structural retrieval (symbol, file, test, dependency)
│   │   ├── symbols.py      # Symbol index (AST-based: functions, classes, methods)
│   │   └── tests.py        # Test index (pytest collection, test-to-symbol mapping)
│   ├── reasoning/          # Reasoning protocol
│   │   ├── critic.py       # Critic (11 checks) + ReviewService + FinalDecision
│   │   ├── patcher.py      # Diff parsing, validation, application
│   │   ├── prompts/        # Prompt templates for each reasoning stage
│   │   ├── protocol.py     # ReasoningOutput, EvidenceSummary, Hypothesis, etc.
│   │   ├── reasoner.py     # 6-stage reasoning protocol implementation
│   │   └── task_parser.py  # Task instruction parsing (Markdown/JSON)
│   ├── verify/             # Verification pipeline
│   │   ├── gates.py        # Gate evaluation (required vs optional)
│   │   ├── lint_adapter.py # Ruff lint adapter
│   │   ├── pytest_adapter.py # Pytest adapter with output parsing
│   │   ├── runner.py       # VerificationRunner orchestrating all checks
│   │   ├── sandbox.py      # Git worktree sandbox with command execution
│   │   ├── security_adapter.py # Bandit security adapter
│   │   └── type_adapter.py # Mypy type check adapter
│   ├── repair/             # Repair loop
│   │   ├── categorizer.py  # Failure categorization (syntax, test, type, etc.)
│   │   ├── loop.py         # RepairLoop with max attempts
│   │   └── repair_reasoner.py # Repair-specific reasoning
│   ├── provenance/         # Provenance graph
│   │   ├── evidence.py     # Evidence creation utilities
│   │   ├── graph.py        # EvidenceGraph with 17 link types + build_from_pipeline
│   │   └── store.py        # ProvenanceStore (trace, reverse trace, path, audit, summary)
│   ├── eval/               # Evaluation
│   │   ├── ablations.py    # Ablation experiment configs
│   │   ├── reports.py      # EvaluationReport with aggregate metrics
│   │   ├── scorer.py       # ScoreResult with verified success, pass@1, regression
│   │   └── tasks.py        # BenchmarkTask definitions with hidden tests
│   ├── training/           # Training data
│   │   ├── datasets.py     # DatasetBuilder (SFT, repair, preference)
│   │   ├── export.py       # TrajectoryExporter (JSONL)
│   │   └── filters.py      # TrajectoryFilter (quality, categorization)
│   ├── api/                # FastAPI (stub - Phase 11)
│   ├── orchestrator.py     # End-to-end pipeline coordinator
│   └── cli.py              # CLI with 15+ commands
├── tests/                  # 457 tests across 22 test files
├── .github/workflows/ci.yml # GitHub Actions CI
├── Dockerfile              # Docker image
├── .dockerignore
├── pyproject.toml          # Project config (setuptools, ruff, mypy, pytest)
├── vsrs.example.yaml       # Example configuration
└── README.md
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/vsrs --cov-report=term-missing

# Run a specific test file
pytest tests/test_orchestrator.py -v

# Run with ruff lint
ruff check src/ tests/
```

**457 tests** across 22 test files covering all modules: core schemas, state machine, store, config, CLI, orchestrator, provenance, reasoning, verification, repair, repo intelligence, eval, and training.

## Docker

```bash
# Build
docker build -t vsrs .

# Run
docker run --rm -v $(pwd)/data:/data vsrs run --repo /my-repo --task task.md

# Check status
docker run --rm -v $(pwd)/data:/data vsrs status <RUN_ID>
```

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR:

- **Matrix**: Python 3.12 and 3.13
- **Lint**: ruff check on `src/` and `tests/`
- **Type check**: mypy on `src/`
- **Tests**: pytest with `--tb=short`
- **Coverage**: pytest with `--cov` report
- **Docker**: builds and tests the Docker image

## Contributing

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass: `pytest tests/ -v`
4. Ensure lint passes: `ruff check src/ tests/`
5. Submit a pull request

## Roadmap

See [MEGAPLAN.md](MEGAPLAN.md) for the comprehensive project plan covering all 15 phases and future roadmap.

## License

MIT
