# VSRS Megaplan: Comprehensive Project Roadmap

This document covers all 15 phases of the VSRS project — all phases are complete. Completed phases are documented with key deliverables, and a future roadmap is outlined beyond the initial scope.

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

## Completed Phases (11–15)

### Phase 11: API Server ✅

**Status**: Complete | **Tests**: 30+ (API)

**Key Deliverables**:
- `api/app.py` — FastAPI app factory with CORS, health check
- `api/routes.py` — REST endpoints for runs, evidence, diff, verify, review, provenance, report, export, history, config, benchmarks
- `api/models.py` — Pydantic request/response models
- `api/deps.py` — Dependency injection for Store and Config
- OpenAPI docs auto-generated at /docs

### Phase 12: Training Data Export ✅

**Status**: Complete | **Tests**: 25+ (training)

**Key Deliverables**:
- `training/export.py` — TrajectoryExporter with provenance edges, event timeline, repair decisions, export_all
- `training/filters.py` — TrajectoryFilter with minimality score, evidence quality, repair efficiency, advanced filter options
- `training/datasets.py` — DatasetBuilder with token counting, train/val splits, tool-use dataset, dataset stats
- `training/__init__.py` — Public API exports

### Phase 13: Evaluation & Benchmarking ✅

**Status**: Complete | **Tests**: 41 (eval)

**Key Deliverables**:
- `eval/runner.py` — BenchmarkRunner with TaskRunner protocol, run_all/run_single, JSON/CSV export
- `eval/scorer.py` — ScoreResult with hidden test metrics, grounding error detection, test adequacy, to_dict
- `eval/ablations.py` — AblationHarness with run_all, comparison_table, AblationResult.from_report
- `eval/reports.py` — EvaluationReport with CategoryBreakdown, CSV/JSON export, compare classmethod
- `eval/tasks.py` — BenchmarkSet with seed tasks and hidden acceptance tests

### Phase 14: LLM Integration ✅

**Status**: Complete | **Tests**: 43 (LLM)

**Key Deliverables**:
- `llm/client.py` — Unified LLM client: StubClient, OpenAIClient, AnthropicClient, create_client factory
- `llm/cost.py` — CostTracker and TokenUsage with per-model pricing, cost_by_model, summary, to_dict
- `llm/prompts.py` — Prompt rendering, JSON extraction, structured output parsing, evidence formatting
- `llm/reasoner.py` — LLMReasoner and LLMRepairReasoner with fallback to deterministic reasoners
- `llm/__init__.py` — Public API exports

### Phase 15: Documentation & Polish ✅

**Status**: Complete | **Tests**: 604 total

**Key Deliverables**:
- `LICENSE` — MIT license
- `docs/architecture.md` — Pipeline diagrams, stage details, module reference
- `docs/api-reference.md` — Full REST API reference with all endpoints
- `docs/contributing.md` — Development setup, coding standards, PR process
- `docs/changelog.md` — Versioned changelog (v0.1.0–v0.5.0)
- `docs/examples/` — 5 example tasks, 4 config files, bugfix walkthrough
- `README.md` — Updated badges, documentation links
- `pyproject.toml` — Version 0.5.0, llm/llm-anthropic/all dependency groups
- All TODO comments removed from source files

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
| Source files | 64 Python files |
| Source lines | ~13,700 LOC |
| Test files | 17 test files |
| Test count | 604 tests |
| Modules | 11 (core, repo, reasoning, verify, repair, review, provenance, api, llm, training, eval) |
| CLI commands | 17+ |
| Phases completed | 15 of 15 |
| Dependencies | pydantic, typer, rich, pyyaml |
| Optional deps | fastapi, uvicorn, httpx, openai, anthropic |

---

## Version History

| Version | Phase | Description |
|---------|-------|-------------|
| 0.1.0 | 1–10 | Core pipeline, CLI, provenance, config, deployment |
| 0.2.0 | 11 | API server |
| 0.3.0 | 12 | Training data export |
| 0.4.0 | 13 | Evaluation & benchmarking |
| 0.5.0 | 14–15 | LLM integration, documentation, polish |
