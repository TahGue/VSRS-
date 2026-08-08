# Changelog

All notable changes to VSRS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- LLM integration with OpenAI, Anthropic, and stub providers
- Cost tracking for LLM API calls
- Prompt rendering and structured output parsing
- LLM-backed reasoner and repair reasoner with fallback

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
