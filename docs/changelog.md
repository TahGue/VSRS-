# Changelog

All notable changes to VSRS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


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
