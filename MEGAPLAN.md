# VSRS Megaplan: Comprehensive Project Roadmap

This document covers all 15 phases of the VSRS project — completed phases as reference with key deliverables, pending phases with detailed implementation plans, and a future roadmap beyond the initial scope.

---

## Completed Phases (1–10)

### Phase 1: Core Infrastructure ✅

**Status**: Complete | **Tests**: 60+ (schemas, state, store, events, ids, policy)

**Key Deliverables**:
- `core/schemas.py` — Pydantic models: Task, TaskRun, PatchCandidate, VerificationReport, FinalDecision, ProvenanceEdge, ReviewFinding, EvidenceItem, EvidenceContract
- `core/state.py` — TaskStateMachine with 12 states and valid transitions (intake → retrieving → reasoning → patching → verifying → revising → reviewing → verified/rejected/failed/escalated)
- `core/store.py` — SQLite persistence with 10 tables (tasks, task_runs, evidence_items, patch_candidates, verification_reports, review_findings, evidence_contracts, provenance_edges, run_events, final_decisions)
- `core/config.py` — VSRSConfig with YAML discovery, 16 env overrides, validation, serialization
- `core/events.py` — RunEvent append-only event log
- `core/ids.py` — ID generators (run, task, patch, evidence, hypothesis)
- `core/logging.py` — Structured JSON logging with run IDs
- `core/policy.py` — Policy engine for allowed file operations and command execution

### Phase 2: Repository Intelligence ✅

**Status**: Complete | **Tests**: 80+ (repo files, symbols, tests, dependencies, git, retrieval)

**Key Deliverables**:
- `repo/files.py` — FileIndex: tree walk, extension filtering, size analysis
- `repo/symbols.py` — SymbolIndex: AST-based extraction of functions, classes, methods, imports
- `repo/tests.py` — TestIndex: pytest collection, test-to-symbol mapping, fixture detection
- `repo/dependencies.py` — DependencyIndex: import graph, package detection, circular dependency detection
- `repo/git.py` — GitIndex: blame, log, diff, branch info, commit history
- `repo/retrieval.py` — Structural retrieval: by symbol, file, test, dependency with ranking
- `repo/intelligence.py` — RepositoryIntelligence: builds unified RepositoryModel, provides Retriever

### Phase 3: Reasoning Protocol ✅

**Status**: Complete | **Tests**: 40+ (protocol, reasoner, task_parser)

**Key Deliverables**:
- `reasoning/protocol.py` — Schemas: ReasoningOutput, EvidenceSummary, ReasoningHypothesis, PredictedEffects, FalsificationPlan, PatchProposal, RepairOutput
- `reasoning/reasoner.py` — 6-stage reasoning protocol: evidence summary → hypothesis → predicted effects → falsification plan → patch proposal → structured output
- `reasoning/task_parser.py` — Task instruction parsing from Markdown/JSON, acceptance criteria extraction, risk/type inference
- `reasoning/prompts/templates.py` — Prompt templates for all 6 stages + repair prompt, with system prompt establishing reasoning contract

### Phase 4: Patch Generation ✅

**Status**: Complete | **Tests**: 25 (patcher)

**Key Deliverables**:
- `reasoning/patcher.py` — Patcher class: unified diff parsing (with `a/`/`b/` prefix stripping), validation (syntax, path existence), application (git apply), ValidationResult
- PatchCandidate schema with diff, changed_files, assumptions, predicted_effects, base_commit

### Phase 5: Verification ✅

**Status**: Complete | **Tests**: 50+ (sandbox, pytest_adapter, lint, type, security, runner, gates)

**Key Deliverables**:
- `verify/sandbox.py` — Sandbox: git worktree creation, command execution with policy checks, environment sanitization, resource limits, content hashing
- `verify/pytest_adapter.py` — PytestAdapter: runs pytest, parses verbose output (test counts, failures, errors, durations), produces CheckResult
- `verify/lint_adapter.py` — RuffAdapter: runs ruff, parses JSON output, produces CheckResult
- `verify/type_adapter.py` — MypyAdapter: runs mypy, parses output, produces CheckResult
- `verify/security_adapter.py` — BanditAdapter: runs bandit, parses JSON output, produces CheckResult
- `verify/runner.py` — VerificationRunner: orchestrates all checks, evaluates gates, produces VerificationReport
- `verify/gates.py` — Gate evaluation: required vs optional gates, all_required_passed

### Phase 6: Critic & Review ✅

**Status**: Complete | **Tests**: 20+ (critic)

**Key Deliverables**:
- `reasoning/critic.py` — Critic with 11 automated checks (syntax, test pass, new tests, type check, lint, security, minimality, evidence grounding, assumption coverage, falsification, regression) + ReviewService producing FinalDecision with status (verified_candidate, rejected, needs_review, escalated)
- ReviewFinding schema with severity (blocker, major, minor, question, suggestion), category, evidence_refs

### Phase 7: Orchestrator ✅

**Status**: Complete | **Tests**: 14 (orchestrator) + 20 (repair loop, categorizer, repair reasoner)

**Key Deliverables**:
- `orchestrator.py` — Orchestrator class coordinating full pipeline: intake → retrieve → reason → patch → verify → repair → review. Produces PipelineResult with all stage results, reasoning output, patch, verification report, critic report, and final decision. State machine transitions enforced at each stage.
- `repair/categorizer.py` — FailureCategorizer: categorizes failures (syntax_error, test_failure, type_error, import_error, assertion_error, timeout, other)
- `repair/loop.py` — RepairLoop: iterative repair with max attempts, tracks all attempts, produces RepairResult
- `repair/repair_reasoner.py` — RepairReasoner: analyzes failures and produces corrected patch proposals

### Phase 8: Provenance Graph ✅

**Status**: Complete | **Tests**: 26 (provenance)

**Key Deliverables**:
- `provenance/store.py` — ProvenanceStore: add_edge, add_edges, get_outgoing, get_incoming, get_all_edges, trace (forward BFS), reverse_trace (backward BFS), find_path (BFS path finding), audit_trail (structured entries with depth), get_nodes, get_neighbors, degree, summary (GraphSummary with edge/node/relation counts, max depth), format_audit_trail
- `provenance/graph.py` — EvidenceGraph: 17 link methods (run→task, task→evidence, task→hypothesis, evidence→hypothesis, hypothesis→patch, run→patch, patch→file, patch→verification, verification→check, patch→finding, patch→result, run→decision, requirement→behavior, behavior→symbol, behavior→test, requirement→patch, requirement→evidence), build_from_pipeline (auto-builds graph from PipelineResult), get_audit_trail, get_graph_summary, find_evidence_chain
- `provenance/evidence.py` — Evidence creation utilities for 6 evidence types (structural, executable, config, historical, documentation, inference)

### Phase 9: CLI & Reporting ✅

**Status**: Complete | **Tests**: 24 (CLI)

**Key Deliverables**:
- `cli.py` — 15+ commands: run, status, evidence, diff, verify, export, audit-trail, history, review, report, provenance (tree/json/summary), config show/init/validate, benchmark list/show/save
- Rich terminal output with tables, panels, syntax highlighting
- Report generation: markdown summary with task, run, evidence, patches, events, provenance stats, final decision

### Phase 10: Configuration & Deployment ✅

**Status**: Complete | **Tests**: 32 (config)

**Key Deliverables**:
- Enhanced `core/config.py` — VSRSConfig.load() with file discovery (explicit → VSRS_CONFIG env → ./vsrs.yaml → ~/.vsrs/config.yaml → defaults), 16 env overrides, to_dict/to_yaml/save_yaml serialization, validate() with 7 validation rules
- `Dockerfile` — Python 3.12-slim, git, pip install, volume for /data
- `.dockerignore` — Excludes caches, tests, build artifacts
- `.github/workflows/ci.yml` — Matrix testing (Python 3.12/3.13), ruff, mypy, pytest with coverage, Docker build test
- `vsrs.example.yaml` — Complete annotated example config

---

## Pending Phases (11–15)

### Phase 11: API Server

**Objective**: FastAPI REST API exposing all VSRS functionality with WebSocket for live run updates.

**Files to create/modify**:
- `src/vsrs/api/app.py` — FastAPI app factory with CORS, error handlers, lifespan
- `src/vsrs/api/routes.py` — REST endpoints
- `src/vsrs/api/models.py` — Pydantic request/response models
- `src/vsrs/api/deps.py` — Dependency injection (Store, Orchestrator, Config)
- `src/vsrs/api/websocket.py` — WebSocket handler for live run updates
- `tests/test_api.py` — API tests with TestClient
- `pyproject.toml` — Add fastapi, uvicorn, httpx dependencies

**Key endpoints**:
```
POST   /api/v1/runs                    Start a new task run
GET    /api/v1/runs/{run_id}            Get run status
GET    /api/v1/runs/{run_id}/evidence   Get evidence items
GET    /api/v1/runs/{run_id}/diff       Get latest patch diff
GET    /api/v1/runs/{run_id}/verify     Get verification report
GET    /api/v1/runs/{run_id}/review     Get critic findings + decision
GET    /api/v1/runs/{run_id}/provenance Get provenance graph
GET    /api/v1/runs/{run_id}/report     Generate report
GET    /api/v1/runs/{run_id}/export     Export trajectory
GET    /api/v1/tasks/{task_id}/history  Get run history for task
GET    /api/v1/config                   Get current config
POST   /api/v1/config/validate          Validate config
GET    /api/v1/benchmarks               List benchmark tasks
WS     /api/v1/runs/{run_id}/stream     Live run updates
```

**Acceptance criteria**:
- All endpoints return correct JSON responses
- WebSocket streams state changes in real-time
- OpenAPI docs auto-generated at /docs
- 30+ API tests passing

### Phase 12: Training Data Export

**Objective**: Full training data export pipeline with quality filters and dataset builders.

**Files to modify**:
- `src/vsrs/training/export.py` — Enhance TrajectoryExporter with provenance links, event timeline, repair decisions
- `src/vsrs/training/filters.py` — Add advanced filters: minimality threshold, evidence quality score, repair efficiency
- `src/vsrs/training/datasets.py` — Enhance dataset builders with token counting, train/val splits, format validators
- `src/vsrs/training/__init__.py` — Export public API
- `tests/test_training.py` — New tests for export, filters, datasets

**Key features**:
- Export full trajectory with provenance graph edges
- Quality filters: reproducible, verified_positive, verified_negative, unresolved, has_patch, has_evidence, has_verification, minimality_score, evidence_quality
- Dataset builders: SFT (verified-positive), repair (fail-then-success), preference (good vs bad), tool-use (task → correct query)
- Train/validation split with deterministic seeding
- JSONL and HuggingFace datasets format

**Acceptance criteria**:
- Export produces complete trajectory with all stages
- Filters correctly categorize trajectories
- Dataset builders produce valid JSONL
- 25+ tests passing

### Phase 13: Evaluation & Benchmarking

**Objective**: Full benchmark runner with scoring, ablation harness, and evaluation reports.

**Files to modify**:
- `src/vsrs/eval/runner.py` (new) — BenchmarkRunner: runs all benchmark tasks, collects results, generates reports
- `src/vsrs/eval/scorer.py` — Enhance with hidden test execution, regression detection, grounding error detection
- `src/vsrs/eval/ablations.py` — Implement ablation harness that disables components and re-runs
- `src/vsrs/eval/reports.py` — Add comparison reports, per-category breakdowns, CSV/JSON export
- `src/vsrs/eval/tasks.py` — Expand benchmark task set
- `tests/test_eval.py` — New tests for runner, scorer, ablations, reports

**Key metrics**:
- Verified success rate, pass@1, repair success rate
- Regression rate, grounding error rate
- Evidence completeness rate, patch minimality
- Average tool calls, average duration
- Per-category breakdowns (bugfix, feature, refactor, security)
- Ablation comparison table

**Acceptance criteria**:
- BenchmarkRunner executes all tasks and produces EvaluationReport
- Ablation harness correctly disables components
- Reports include aggregate + per-task + per-category metrics
- 20+ tests passing

### Phase 14: LLM Integration

**Objective**: Integrate LLM clients (OpenAI, Anthropic) for reasoning, patch generation, and repair.

**Files to create**:
- `src/vsrs/llm/client.py` — Unified LLM client (OpenAI, Anthropic, local)
- `src/vsrs/llm/openai_client.py` — OpenAI API client
- `src/vsrs/llm/anthropic_client.py` — Anthropic API client
- `src/vsrs/llm/render.py` — Prompt rendering from templates
- `src/vsrs/llm/parse.py` — Structured JSON output parsing with validation
- `src/vsrs/llm/cost.py` — Token/cost tracking
- `src/vsrs/llm/__init__.py` — Public API

**Files to modify**:
- `src/vsrs/reasoning/reasoner.py` — Use LLM client for 6-stage protocol
- `src/vsrs/repair/repair_reasoner.py` — Use LLM client for repair
- `src/vsrs/reasoning/critic.py` — Optional LLM-assisted critic checks
- `src/vsrs/orchestrator.py` — Wire LLM client through pipeline
- `pyproject.toml` — Add openai, anthropic dependencies

**Key features**:
- Provider-agnostic LLM client with retry, timeout, streaming
- Prompt template rendering with evidence formatting
- Structured output parsing: JSON → Pydantic schema validation
- Token/cost tracking per stage and per run
- Fallback to stub mode when no API key configured
- Configurable model, temperature, max_tokens

**Acceptance criteria**:
- LLM client works with OpenAI and Anthropic APIs
- Structured output parsing validates against protocol schemas
- Cost tracking reports tokens and estimated cost per run
- Stub mode works without API key (existing behavior)
- 30+ tests passing (with mocked API responses)

### Phase 15: Documentation & Polish

**Objective**: Complete documentation, architecture diagrams, contributor guide, and final polish.

**Files to create**:
- `docs/architecture.md` — Detailed architecture document with diagrams
- `docs/api-reference.md` — Full API reference (once Phase 11 complete)
- `docs/contributing.md` — Contributor guide with development setup, coding standards, PR process
- `docs/changelog.md` — Versioned changelog
- `docs/examples/` — Example task definitions, config files, and usage scenarios
- `LICENSE` — MIT license file

**Files to modify**:
- `README.md` — Final polish, badge updates, link to docs
- `pyproject.toml` — Version bump, optional dependencies groups
- All source files — Remove TODO comments, clean up docstrings

**Key deliverables**:
- Architecture diagram (Mermaid or ASCII) showing pipeline flow
- API reference with all endpoints, request/response schemas
- Contributor guide: setup, test, lint, type check, PR process
- Example gallery: 5+ example tasks with expected outputs
- Changelog with semantic versioning

**Acceptance criteria**:
- All TODO comments resolved or tracked as issues
- Documentation covers all modules and CLI commands
- Examples are runnable and produce expected results
- 100% test coverage on core modules

---

## Future Roadmap (Post-15)

### Plugin System
- Custom verifier plugins (register new check types)
- Custom retriever plugins (alternative indexing strategies)
- Custom critic checks (domain-specific review rules)
- Plugin discovery via entry points

### Multi-Language Support
- Go: AST parsing, go test, go vet, staticcheck
- Rust: cargo, clippy, rust-analyzer
- Java: Maven/Gradle, JUnit, Checkstyle, SpotBugs
- TypeScript: tsc, eslint, jest
- Language-agnostic: tree-sitter for structural indexing

### Web UI Dashboard
- React/Next.js dashboard for run management
- Real-time pipeline visualization
- Provenance graph interactive viewer
- Diff viewer with syntax highlighting
- Benchmark results dashboard

### Distributed Execution
- Celery/RQ task queue for parallel benchmark runs
- Redis-backed run state coordination
- Horizontal scaling of verification workers
- Job priority and resource allocation

### Model Fine-Tuning Pipeline
- Automated trajectory collection from production runs
- Dataset versioning and deduplication
- Fine-tuning job orchestration (LoRA, QLoRA)
- Evaluation harness for fine-tuned models
- A/B comparison between base and fine-tuned models

### VSCode Extension
- Inline task creation from editor context
- Live run status in status bar
- Diff preview in editor
- Provenance graph sidebar view
- Quick actions: run, verify, review from editor

### Enterprise Features
- Authentication and authorization (OAuth, API keys)
- Multi-tenant project isolation
- Audit log retention policies
- SSO integration (SAML, OIDC)
- Role-based access control (admin, developer, viewer)

---

## Project Statistics

| Metric | Value |
|--------|-------|
| Source files | 49 Python files |
| Source lines | ~11,000 LOC |
| Test files | 22 test files |
| Test count | 457 tests |
| Modules | 10 (core, repo, reasoning, verify, repair, provenance, eval, training, api, orchestrator) |
| CLI commands | 17+ |
| Phases completed | 10 of 15 |
| Dependencies | pydantic, typer, rich, pyyaml |

---

## Version History

| Version | Phase | Description |
|---------|-------|-------------|
| 0.1.0 | 1–10 | Core pipeline, CLI, provenance, config, deployment |
| 0.2.0 | 11–12 | API server, training data export |
| 0.3.0 | 13 | Evaluation & benchmarking |
| 0.4.0 | 14 | LLM integration |
| 1.0.0 | 15 | Documentation, polish, stable release |
