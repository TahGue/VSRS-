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

## Completed Phases (16–21)

### Phase 16: Plugin System ✅
- Plugin ABCs: VerifierPlugin, RetrieverPlugin, CriticPlugin
- PluginRegistry with entry point discovery
- Built-in plugins: FileSizeVerifier, ImportCheckerVerifier, GitLogRetriever, MinimalityCritic, SecurityCritic
- 42 tests

### Phase 17: Multi-Language Support ✅
- LanguageAdapter ABC: syntax_check, build, run_tests, lint, type_check
- LanguageRegistry with detection from files and repos
- Adapters: Python, Go, Rust, TypeScript, Java
- MultiLanguageVerificationRunner for pipeline integration
- 59 tests

### Phase 18: Distributed Execution ✅
- TaskQueue ABC: submit, fetch, complete, cancel, list_jobs
- InMemoryQueue (thread-safe, priority-ordered)
- RedisQueue (JSON serialization, BRPOP/LPUSH, graceful fallback)
- Worker with background thread, handler registration, stats
- DistributedBenchmarkRunner for parallel benchmark execution
- 40 tests

### Phase 19: Model Fine-Tuning Pipeline ✅
- FineTuningJob with 5 methods (full, lora, qlora, dpo, ppo)
- JobOrchestrator with custom executors
- DatasetVersionManager with content hashing and deduplication
- ModelComparisonHarness for A/B comparison with per-task and aggregate deltas
- 44 tests

### Phase 20: Enterprise Features ✅
- Authentication: User, APIKey (hashed), AuthContext, APIKeyManager
- RBAC: Permission enum (14 permissions), Role with inheritance, RoleManager
- Audit: AuditEvent, AuditEventType (15 types), AuditLogger with query and export
- Rate Limiting: token bucket + sliding window, per-identifier tracking
- 71 tests

### Phase 21: VSCode Extension ✅
- TypeScript extension: 10 commands, 2 sidebar views, 6 config settings
- API client, task tree provider, status bar, webview results panel
- Keybindings, auto-connect, auto-verify on save
- 35 tests

### Phase 22: Web UI Dashboard ✅
- React 18 + Vite 5 + React Router 6 dashboard
- Runs page: list, create new runs with form
- Run detail: run info, task, verification checks, diff viewer with syntax highlighting
- Benchmarks page: browse benchmark suites
- Settings page: view configuration
- Dark theme with GitHub-inspired design
- API proxy for dev, build output for production serving
- 37 tests

### Phase 23: Real-Time WebSocket & Provenance Graph ✅
- WebSocket ConnectionManager with pub/sub per run_id
- Event types: state_change, tool_call, verification_result, patch_generated, review_complete, run_complete
- Event history with replay on connect
- WebSocket endpoint at /ws/runs/{run_id} with ping/pong support
- useWebSocket hook for React dashboard
- LiveProgress component: pipeline stage indicator + event feed
- ProvenanceGraph component: interactive SVG graph with node selection
- Integrated into RunDetailPage
- 32 tests

### Phase 24: Tree-Sitter Structural Indexing ✅
- TreeSitterIndexer: multi-language symbol extraction via tree-sitter
  - Supports Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, Ruby
  - Node type maps per language for function/class/method/import detection
  - Decorator and docstring extraction for Python
  - Qualified name building with parent class tracking
  - Graceful fallback when tree-sitter not installed
- HybridSymbolIndex: uses Python AST for .py files, tree-sitter for others
- Optional dependency: `pip install vsrs[tree-sitter]`
- 51 tests

### Phase 25: Multi-Tenant Project Isolation ✅
- Tenant model with status (active, suspended, deleted) and metadata
- Project model scoped to tenants with repo root tracking
- ResourceQuota: max_projects, max_runs_per_day, max_concurrent_runs, max_storage_mb, max_api_keys
- UsageRecord: daily run tracking, concurrent run counting, storage and API key usage
- TenantManager: full CRUD for tenants and projects, quota enforcement
- QuotaExceededError with tenant, resource, limit, and current usage details
- Usage summary with per-resource used/limit/remaining breakdown
- Unlimited quota support (-1 limits)
- 57 tests

### Phase 26: SSO Integration (SAML, OIDC) ✅
- SAMLProvider: entity ID, SSO/SLO URLs, X.509 cert, attribute mapping
- OIDCProvider: issuer URL, client ID/secret, scopes, authorize/token/userinfo URLs
- SSOSession: token-based sessions with expiration and refresh
- SSOManager: provider registration, OIDC authorize URL generation,
  JWT token validation (exp, iss, aud checks), SAML response validation,
  automatic user provisioning from IdP attributes
- Session management: get/logout/refresh/cleanup expired sessions
- Error hierarchy: SSOError, SSOAuthenticationError, SSOTokenExpiredError, SSOProviderNotFoundError
- 50 tests

### Phase 27: Worker Pool with Resource Allocation and Auto-Scaling ✅
- ResourceSpec: CPU, memory, GPU, disk with can_fit/subtract/add operations
- WorkerInfo: runtime state (idle, busy, draining, stopped, unhealthy), capacity tracking
- WorkerPool: resource-aware job scheduling, auto-scaling based on queue depth
- PoolConfig: min/max workers, scale up/down thresholds, health check intervals
- Health monitoring: heartbeat-based unhealthy worker detection and replacement
- Graceful shutdown with worker draining
- Thread-safe with RLock for all operations
- InsufficientResourcesError when no worker can handle a job
- Pool stats: worker count, idle/busy/unhealthy counts, total/available capacity
- 55 tests

### Phase 28: Documentation & Integration Polish ✅
- User guide: 3 new sections (multi-tenant, SSO, worker pool & auto-scaling)
- Updated TOC, install instructions (tree-sitter optional dep), API endpoints (WebSocket)
- Integration tests: 14 cross-module tests covering tenant+pool, SSO+enterprise,
  tenant+SSO, pool+queue, and full end-to-end enterprise workflow
- 1191 total tests

### Phase 29: Enterprise CLI Commands ✅
- `vsrs tenant create/list/show/suspend/reactivate/delete`
- `vsrs sso list-providers/list-sessions/cleanup/list-users`
- `vsrs pool stats`
- TenantNotFoundError handling with graceful error messages
- 17 CLI tests
- 1208 total tests

### Phase 30: Enterprise API Endpoints ✅
- Tenant CRUD: POST/GET/DELETE /api/v1/tenants, suspend/reactivate, usage
- Project CRUD: POST/GET/DELETE /api/v1/tenants/{id}/projects
- SSO: GET /api/v1/sso/providers, /sessions, /users; POST /cleanup
- Pool: GET /api/v1/pool/stats
- Pydantic request/response models for all endpoints
- 404 handling for TenantNotFoundError
- 24 API tests
- 1232 total tests

### Phase 31: API Authentication Middleware ✅
- X-API-Key header validation via require_api_key dependency
- Scope-based access control via require_scope dependency
- Rate limiting integrated into auth flow (429 with Retry-After header)
- Audit logging of API key validations
- Enterprise endpoints protected: admin scopes for tenant/project CRUD,
  sso:admin for SSO cleanup, any valid key for read endpoints
- 20 auth middleware tests (no key, invalid key, read-only, admin, unprotected)
- 1252 total tests

### Phase 32: API Key & Audit CLI + API Reference ✅
- vsrs key create/list/revoke/validate/count
- vsrs audit list/count/export
- 12 CLI tests
- API reference: authentication section, enterprise endpoints, updated error codes
- 1264 total tests

### Phase 33: API Key & Audit Management API ✅
- POST /api/v1/keys (create, requires key:admin scope)
- GET /api/v1/keys (list with optional user filter)
- GET /api/v1/keys/count
- DELETE /api/v1/keys/{id} (revoke, requires key:admin scope)
- GET /api/v1/audit (query with filters)
- GET /api/v1/audit/count
- 15 API tests including integration (create → use → revoke → verify invalidation)
- 1279 total tests

### Phase 34: Rate Limiting & RBAC API Endpoints ✅
- GET /api/v1/rate-limit/usage (per-identifier usage stats)
- GET /api/v1/rate-limit/config (rate limit configuration)
- POST /api/v1/rate-limit/reset (requires admin:all)
- GET /api/v1/roles (list all roles)
- GET /api/v1/roles/{name} (get role details, 404 if not found)
- POST /api/v1/roles/check-permission (check role permission with resolved inheritance)
- 15 API tests
- 1294 total tests

### Phase 35: Role & Rate Limit CLI + API Pagination ✅
- vsrs role list/show/check (RBAC role management)
- vsrs ratelimit usage/config/reset (rate limit management)
- API pagination on GET /tenants, GET /keys, GET /audit, GET /roles (offset, limit, total fields)
- 21 tests (15 CLI + 6 pagination)
- 1315 total tests

## Future Roadmap (Post-35)

All planned phases complete. The VSRS project now includes:
- Core pipeline with provenance tracking
- Repository intelligence with tree-sitter multi-language indexing
- LLM-powered reasoning, verification, repair, and review
- Web dashboard with real-time WebSocket streaming
- VSCode extension
- Enterprise features: RBAC, audit logging, API keys, rate limiting
- Multi-tenant project isolation with resource quotas
- SSO integration (SAML 2.0, OpenID Connect)
- Distributed execution with worker pool auto-scaling
- Training data export, fine-tuning, evaluation, and benchmarking
- Plugin system and multi-language support

---

## Project Statistics

| Metric | Value |
|--------|-------|
| Source files | 95+ Python files |
| Source lines | ~24,000 LOC |
| Test count | 1315 tests |
| Test files | 30 test files |
| Modules | 24 (core, repo, reasoning, verify, repair, review, provenance, api, llm, training, eval, plugins, languages, distributed, finetuning, enterprise, api.websocket, repo.tree_sitter_index, enterprise.tenant, enterprise.sso, distributed.pool, api.enterprise_routes, api.auth) + VSCode extension + Web dashboard |
| CLI commands | 43+ |
| API endpoints | 37+ |
| Phases completed | 35 of 35 |
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
| 0.6.0 | 16 | Plugin system |
| 0.7.0 | 17 | Multi-language support |
| 0.8.0 | 18 | Distributed execution |
| 0.9.0 | 19 | Fine-tuning pipeline |
| 1.0.0 | 20–21 | Enterprise features, VSCode extension |
| 1.1.0 | 22 | Web UI dashboard |
| 1.2.0 | 23 | Real-time WebSocket & provenance graph viewer |
| 1.3.0 | 24 | Tree-sitter structural indexing |
| 1.4.0 | 25 | Multi-tenant project isolation |
| 1.5.0 | 26 | SSO integration (SAML, OIDC) |
| 1.6.0 | 27 | Worker pool with resource allocation and auto-scaling |
| 1.7.0 | 28 | Documentation & integration polish |
| 1.8.0 | 29 | Enterprise CLI commands (tenant, SSO, pool) |
| 1.9.0 | 30 | Enterprise API endpoints |
| 2.0.0 | 31 | API authentication middleware |
| 2.1.0 | 32 | API key & audit CLI, API reference docs |
| 2.2.0 | 33 | API key & audit management REST endpoints |
| 2.3.0 | 34 | Rate limiting & RBAC API endpoints |
| 2.4.0 | 35 | Role & rate limit CLI + API pagination |
