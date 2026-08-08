# Changelog

All notable changes to VSRS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


## [2.4.0] - 2026-08-08

### Added
- Role & rate limit CLI commands
  - `vsrs role list/show/check` — RBAC role management
  - `vsrs ratelimit usage/config/reset` — rate limit management
  - 15 CLI tests
- API pagination on list endpoints
  - `GET /tenants`, `GET /keys`, `GET /audit`, `GET /roles` now support `offset` and `limit` query params
  - Response models include `total`, `offset`, `limit` fields
  - 6 pagination tests


## [2.3.0] - 2026-08-08

### Added
- Rate limiting & RBAC API endpoints
  - `GET /api/v1/rate-limit/usage` — get usage stats per identifier
  - `GET /api/v1/rate-limit/config` — get rate limit configuration
  - `POST /api/v1/rate-limit/reset` — reset rate limits (requires `admin:all`)
  - `GET /api/v1/roles` — list all registered roles
  - `GET /api/v1/roles/{name}` — get role details
  - `POST /api/v1/roles/check-permission` — check if role has permission
  - 15 API tests


## [2.2.0] - 2026-08-08

### Added
- API key & audit management REST endpoints
  - `POST /api/v1/keys` — create API key (requires `key:admin` scope)
  - `GET /api/v1/keys` — list keys with optional user filter
  - `GET /api/v1/keys/count` — count total keys
  - `DELETE /api/v1/keys/{id}` — revoke key (requires `key:admin` scope)
  - `GET /api/v1/audit` — query audit events with filters
  - `GET /api/v1/audit/count` — count total audit events
  - 15 API tests including integration (create key → use it → revoke → verify invalidation)


## [2.1.0] - 2026-08-08

### Added
- API key & audit management CLI
  - `vsrs key create/list/revoke/validate/count`
  - `vsrs audit list/count/export`
  - 12 CLI tests
- API reference documentation
  - Authentication section with scopes table
  - Enterprise endpoints section (tenant, project, SSO, pool)
  - Updated CLI commands table
  - Updated error codes (401, 403, 409, 429)


## [2.0.0] - 2026-08-08

### Added
- API authentication middleware
  - `X-API-Key` header validation via `require_api_key` dependency
  - Scope-based access control via `require_scope` dependency
  - Rate limiting integrated into auth flow (429 with Retry-After header)
  - Audit logging of API key validations
  - Enterprise endpoints protected: admin scopes for tenant/project CRUD,
    `sso:admin` for SSO cleanup, any valid key for read endpoints
  - 20 auth middleware tests (no key, invalid key, read-only, admin, unprotected)


## [1.9.0] - 2026-08-08

### Added
- Enterprise API endpoints
  - Tenant CRUD: POST/GET/DELETE `/api/v1/tenants`, suspend/reactivate, usage
  - Project CRUD: POST/GET/DELETE `/api/v1/tenants/{id}/projects`
  - SSO: GET `/api/v1/sso/providers`, `/sessions`, `/users`; POST `/cleanup`
  - Pool: GET `/api/v1/pool/stats`
  - Pydantic request/response models for all endpoints
  - 404 handling for TenantNotFoundError
  - 24 API tests


## [1.8.0] - 2026-08-08

### Added
- Enterprise CLI commands
  - `vsrs tenant create/list/show/suspend/reactivate/delete`
  - `vsrs sso list-providers/list-sessions/cleanup/list-users`
  - `vsrs pool stats`
  - TenantNotFoundError handling with graceful error messages
  - 17 CLI tests


## [1.7.0] - 2026-08-08

### Added
- Documentation & integration polish
  - User guide: 3 new sections (multi-tenant, SSO, worker pool & auto-scaling)
  - Updated TOC, install instructions (tree-sitter optional dep), API endpoints (WebSocket)
  - Integration tests: 14 cross-module tests covering tenant+pool, SSO+enterprise,
    tenant+SSO, pool+queue, and full end-to-end enterprise workflow
  - 1191 total tests


## [1.6.0] - 2026-08-08

### Added
- Worker pool with resource allocation and auto-scaling
  - ResourceSpec: CPU, memory, GPU, disk with can_fit/subtract/add operations
  - WorkerInfo: runtime state (idle, busy, draining, stopped, unhealthy), capacity, available resources
  - WorkerPool: resource-aware job scheduling, auto-scaling based on queue depth
  - PoolConfig: min/max workers, scale up/down thresholds, health check intervals
  - Health monitoring: heartbeat-based unhealthy worker detection and replacement
  - Graceful shutdown with worker draining
  - Thread-safe with RLock for all operations
  - InsufficientResourcesError when no worker can handle a job
  - Pool stats: worker count, idle/busy/unhealthy counts, total/available capacity
  - 55 tests


## [1.5.0] - 2026-08-08

### Added
- SSO integration (SAML 2.0 and OpenID Connect)
  - SAMLProvider: entity ID, SSO/SLO URLs, X.509 cert, attribute mapping
  - OIDCProvider: issuer URL, client ID/secret, scopes, authorize/token/userinfo URLs
  - SSOSession: token-based sessions with expiration and refresh
  - SSOManager: provider registration, OIDC authorize URL generation,
    JWT token validation (exp, iss, aud checks), SAML response validation,
    automatic user provisioning from IdP attributes
  - Session management: get/logout/refresh/cleanup expired sessions
  - Error hierarchy: SSOError, SSOAuthenticationError, SSOTokenExpiredError, SSOProviderNotFoundError
  - 50 tests


## [1.4.0] - 2026-08-08

### Added
- Multi-tenant project isolation
  - Tenant model with status (active, suspended, deleted) and metadata
  - Project model scoped to tenants with repo root tracking
  - ResourceQuota: max_projects, max_runs_per_day, max_concurrent_runs, max_storage_mb, max_api_keys
  - UsageRecord: daily run tracking, concurrent run counting, storage and API key usage
  - TenantManager: full CRUD for tenants and projects, quota enforcement
  - QuotaExceededError with tenant, resource, limit, and current usage details
  - Usage summary with per-resource used/limit/remaining breakdown
  - Unlimited quota support (-1 limits)
  - 57 tests


## [1.3.0] - 2026-08-08

### Added
- Tree-sitter structural indexing for multi-language repositories
  - TreeSitterIndexer: parses Python, JavaScript, TypeScript, Go, Rust, Java, C, C++, Ruby
  - Node type maps per language for function/class/method/import detection
  - Decorator and docstring extraction for Python
  - Qualified name building with parent class tracking
  - HybridSymbolIndex: uses Python AST for .py files, tree-sitter for others
  - Graceful fallback when tree-sitter is not installed
  - Optional dependency: `pip install vsrs[tree-sitter]`
  - 51 tests


## [1.2.0] - 2026-08-08

### Added
- Real-time WebSocket progress streaming
  - ConnectionManager with pub/sub per run_id, event history with replay
  - Event types: state_change, tool_call, verification_result, patch_generated, review_complete, run_complete
  - WebSocket endpoint at /ws/runs/{run_id} with ping/pong support
  - useWebSocket React hook for dashboard integration
  - LiveProgress component: pipeline stage indicator + event feed
  - ProvenanceGraph component: interactive SVG graph with node selection and legend
  - Integrated into RunDetailPage
  - 32 tests


## [1.1.0] - 2026-08-08

### Added
- Web UI dashboard (React 18 + Vite 5 + React Router 6)
  - Runs page with list and create-new-run form
  - Run detail page with verification checks, diff viewer, task info
  - Benchmarks page for browsing benchmark suites
  - Settings page for viewing configuration
  - Dark theme with GitHub-inspired design
  - API proxy for development, production build output
  - 37 tests

## [1.0.0] - 2026-08-08

### Added
- Enterprise features module
  - Authentication: User, APIKey (hashed), AuthContext, APIKeyManager
  - RBAC: Permission enum (14 permissions), Role with inheritance, RoleManager
  - Audit: AuditEvent, AuditEventType (15 types), AuditLogger with query and export
  - Rate limiting: token bucket + sliding window, per-identifier tracking
  - 71 tests
- VSCode extension (TypeScript)
  - 10 commands, 2 sidebar views, 6 config settings, keybindings
  - API client, task tree provider, status bar, webview results panel
  - Auto-connect, auto-verify on save
  - 35 tests

## [0.9.0] - 2026-08-08

### Added
- Model fine-tuning pipeline
  - FineTuningJob with 5 methods (full, lora, qlora, dpo, ppo)
  - JobOrchestrator with custom executors
  - DatasetVersionManager with content hashing and deduplication
  - ModelComparisonHarness for A/B comparison with per-task and aggregate deltas
  - 44 tests

## [0.8.0] - 2026-08-08

### Added
- Distributed execution module
  - TaskQueue ABC: submit, fetch, complete, cancel, list_jobs
  - InMemoryQueue (thread-safe, priority-ordered)
  - RedisQueue (JSON serialization, BRPOP/LPUSH, graceful fallback)
  - Worker with background thread, handler registration, stats
  - DistributedBenchmarkRunner for parallel benchmark execution
  - 40 tests

## [0.7.0] - 2026-08-08

### Added
- Multi-language support
  - LanguageAdapter ABC: syntax_check, build, run_tests, lint, type_check
  - LanguageRegistry with detection from files and repos
  - Adapters: Python, Go, Rust, TypeScript, Java
  - MultiLanguageVerificationRunner for pipeline integration
  - 59 tests

## [0.6.0] - 2026-08-08

### Added
- Plugin system
  - Plugin ABCs: VerifierPlugin, RetrieverPlugin, CriticPlugin
  - PluginRegistry with entry point discovery
  - Built-in plugins: FileSizeVerifier, ImportCheckerVerifier, GitLogRetriever, MinimalityCritic, SecurityCritic
  - 42 tests

## [0.5.0] - 2024-01-01

### Added
- Evaluation and benchmarking framework
  - `BenchmarkRunner` for executing benchmark task sets
  - `ScoreResult` with hidden test metrics, grounding errors, test adequacy
  - `EvaluationReport` with per-category breakdowns, CSV/JSON export, comparison
  - `AblationHarness` with comparison tables and configurable experiments
  - `BenchmarkSet` with seed tasks and hidden acceptance tests
- Training data export pipeline
  - `TrajectoryExporter` with provenance edges, event timeline, repair decisions
  - `TrajectoryFilter` with minimality, evidence quality, repair efficiency scores
  - `DatasetBuilder` with token counting, train/val splits, tool-use datasets
- REST API server with FastAPI
  - Endpoints for runs, evidence, diff, verify, review, provenance, reports
  - Configuration management and benchmark listing
  - Pydantic request/response models

## [0.4.0] - 2024-01-01

### Added
- Provenance graph with typed edges and audit trail
- Evidence contract enforcement
- Run event tracking and timeline
- CLI commands: `audit-trail`, `provenance`, `report`

### Changed
- Refactored store to support provenance edges
- Enhanced schemas with provenance references

## [0.3.0] - 2024-01-01

### Added
- Repair loop with structured failure summaries
- Independent critic review with `ReviewFinding` and `FinalDecision`
- Failure categorization (syntax, test_failure, type_error, import_error, etc.)
- CLI commands: `verify`, `review`

### Changed
- Verification pipeline now produces structured `VerificationReport`
- Patch candidates track attempt numbers and assumptions

## [0.2.0] - 2024-01-01

### Added
- Repository indexing: `FileIndex`, `SymbolIndex`, `TestIndex`, `DependencyIndex`
- Evidence retrieval with ranking and one-hop expansion
- Reasoning protocol with 6 stages (parse, evidence, hypothesis, predict, falsify, patch)
- Task parser for extracting structured task metadata
- Patch application via git worktree or Docker sandbox
- CLI commands: `run`, `status`, `evidence`, `diff`

### Changed
- Core schemas expanded with `Task`, `TaskRun`, `PatchCandidate`, `VerificationReport`
- Configuration management with YAML and environment variable support

## [0.1.0] - 2024-01-01

### Added
- Project scaffolding with `pyproject.toml`
- Core data schemas (`EvidenceItem`, `Hypothesis`, `PatchCandidate`, etc.)
- SQLite-based `Store` for persistence
- `Sandbox` abstraction for isolated patch application
- Basic CLI framework
- Initial test suite
- MIT license
