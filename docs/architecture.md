# VSRS Architecture

## Overview

VSRS (Verified Software Reasoning System) is a multi-stage pipeline that
takes a software task instruction, retrieves evidence from a repository,
reasons about the change, produces a patch, verifies it, repairs failures,
and reviews the result before producing a final decision.

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           VSRS Pipeline                                 │
│                                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │  1.      │   │  2.      │   │  3.      │   │  4.      │            │
│  │  Intake  │──▶│ Retrieve │──▶│  Reason  │──▶│  Patch   │            │
│  │          │   │          │   │          │   │          │            │
│  │ Parse    │   │ Index &  │   │ Hypothesis│  │ Diff     │            │
│  │ Task     │   │ Retrieve │   │ Predict  │   │ Generate │            │
│  │ Snapshot │   │ Evidence │   │ Falsify  │   │          │            │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘            │
│                                                       │                │
│                                                       ▼                │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │  8.      │   │  7.      │   │  6.      │   │  5.      │            │
│  │  Review  │◀──│  Repair  │◀──│  Verify  │◀──│  Apply   │            │
│  │          │   │          │   │          │   │  Patch   │            │
│  │ Critic   │   │ Failure  │   │ Tests    │   │          │            │
│  │ Decision │   │ Analysis │   │ Checks   │   │          │            │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘            │
│       │                                                                 │
│       ▼                                                                 │
│  ┌──────────────────────────────────────────────┐                      │
│  │  Final Decision: verified / rejected /       │                      │
│  │  needs_review                                │                      │
│  └──────────────────────────────────────────────┘                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Stage Details

### Stage 1: Intake

Parses the task instruction, creates a repository snapshot, and initializes
a `TaskRun` with `intake` state.

- **Input**: Task instruction, repo path, acceptance criteria
- **Output**: `ParsedTask`, `RepositorySnapshot`, `TaskRun`
- **Module**: `vsrs.reasoning.task_parser`, `vsrs.core.schemas`

### Stage 2: Retrieve

Indexes the repository (files, symbols, tests, dependencies) and retrieves
evidence relevant to the task. Evidence is ranked and expanded one hop
through imports, callers, and tests.

- **Input**: `Task`, `RepositorySnapshot`
- **Output**: `RetrievalResult` with `RetrievedEvidence` items
- **Module**: `vsrs.repo.retrieval`, `vsrs.repo.index`
- **Indexes**: `FileIndex`, `SymbolIndex`, `TestIndex`, `DependencyIndex`

### Stage 3: Reason

Forms a hypothesis, predicts effects, creates a falsification plan, and
proposes a patch. In V1 this is deterministic; with LLM integration
(Phase 14), it uses an LLM with structured output validation.

- **Input**: `Task`, `RetrievalResult`
- **Output**: `ReasoningOutput` (hypothesis, predicted effects, falsification plan, patch proposal)
- **Module**: `vsrs.reasoning.reasoner`, `vsrs.llm.reasoner`
- **Protocol**: `vsrs.reasoning.protocol` (Pydantic schemas for structured output)

### Stage 4: Patch

Applies the proposed diff to a sandbox (git worktree or Docker container),
captures the changed files, and records the patch candidate.

- **Input**: `PatchProposal`, `RepositorySnapshot`
- **Output**: `PatchCandidate` with applied diff
- **Module**: `vsrs.reasoning.patcher`, `vsrs.core.sandbox`

### Stage 5: Verify

Runs verification checks: syntax, build, existing tests, new targeted tests,
type checking, linting, static analysis, security scanning. Produces a
structured `VerificationReport`.

- **Input**: `PatchCandidate`
- **Output**: `VerificationReport` with `CheckResult` items
- **Module**: `vsrs.verify`, `vsrs.verify.pytest_adapter`
- **Gates**: Required (syntax, build, existing_tests, new_targeted_tests) and optional (type_check, lint, static_analysis, security_scan)

### Stage 6: Repair

If verification fails, categorizes failures into structured `FailureSummary`
items (not raw logs) and feeds them back to the repair reasoner. The repair
loop runs up to `max_repair_attempts` times.

- **Input**: `RepairInput` (prior patch, failures, assumptions)
- **Output**: `RepairOutput` (corrected patch, failure analysis)
- **Module**: `vsrs.repair.repair_reasoner`, `vsrs.llm.reasoner`

### Stage 7: Review

An independent critic reviews the verified patch for minimality, test
adequacy, grounding, and overreach. Produces `ReviewFinding` items and a
`FinalDecision`.

- **Input**: `PatchCandidate`, `VerificationReport`
- **Output**: `ReviewFinding` items, `FinalDecision`
- **Module**: `vsrs.review.critic`

## Provenance Graph

Every stage records edges in a provenance graph, creating an audit trail
from task to final decision.

```
Task ──executes──▶ TaskRun
  │                    │
  │                    ├──retrieves──▶ EvidenceItem
  │                    │                   │
  │                    ├──produces───▶ Hypothesis
  │                    │                   │
  │                    ├──generates──▶ PatchCandidate
  │                    │                   │
  │                    ├──verifies───▶ VerificationReport
  │                    │                   │
  │                    └──reviews────▶ ReviewFinding
  │                                        │
  └────────────────────────────────────▶ FinalDecision
```

- **Module**: `vsrs.provenance.graph`, `vsrs.provenance.store`
- **Edge types**: executes, retrieves, produces, generates, verifies, reviews, repairs

## Data Storage

All entities are persisted in a SQLite database via the `Store` class.

- **Module**: `vsrs.core.store`
- **Tables**: `repository_snapshots`, `tasks`, `task_runs`, `evidence_items`, `hypotheses`, `patch_candidates`, `verification_reports`, `review_findings`, `final_decisions`, `provenance_edges`, `run_events`
- **Config**: `vsrs.core.config.DatabaseConfig` (default: `~/.vsrs/vsrs.db`)

## LLM Integration

The LLM layer provides a unified interface for multiple providers:

```
┌─────────────────────────────────────────────┐
│              LLM Client Interface            │
│                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  OpenAI  │  │ Anthropic│  │   Stub   │  │
│  │  Client  │  │  Client  │  │  Client  │  │
│  └──────────┘  └──────────┘  └──────────┘  │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │         Cost Tracker                 │   │
│  │  (per-model pricing, usage logging)  │   │
│  └──────────────────────────────────────┘   │
│                                              │
│  ┌──────────────────────────────────────┐   │
│  │    Prompt Rendering & Parsing        │   │
│  │  (templates, JSON extraction,        │   │
│  │   Pydantic validation)               │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

- **Module**: `vsrs.llm.client`, `vsrs.llm.cost`, `vsrs.llm.prompts`, `vsrs.llm.reasoner`
- **Providers**: OpenAI (GPT-4o), Anthropic (Claude 3.5), Stub (testing)
- **Fallback**: LLM reasoners fall back to deterministic reasoners on parse failure

## API Server

A FastAPI server exposes all VSRS functionality via REST endpoints.

```
┌─────────────────────────────────────────────┐
│            FastAPI Application               │
│                                              │
│  GET  /health              Health check      │
│  GET  /docs                OpenAPI docs      │
│                                              │
│  POST /api/v1/runs         Create run        │
│  GET  /api/v1/runs/{id}    Get run status    │
│  GET  /api/v1/runs/{id}/task    Get task     │
│  GET  /api/v1/runs/{id}/evidence             │
│  GET  /api/v1/runs/{id}/diff                 │
│  GET  /api/v1/runs/{id}/verify               │
│  GET  /api/v1/runs/{id}/review               │
│  GET  /api/v1/runs/{id}/provenance           │
│  GET  /api/v1/runs/{id}/report               │
│  GET  /api/v1/runs/{id}/export               │
│  GET  /api/v1/tasks/{id}/history             │
│  GET  /api/v1/config        Get config       │
│  POST /api/v1/config/validate                │
│  GET  /api/v1/benchmarks   List benchmarks   │
└─────────────────────────────────────────────┘
```

- **Module**: `vsrs.api.app`, `vsrs.api.routes`, `vsrs.api.models`, `vsrs.api.deps`

## Training Data Export

The training module exports task runs as normalized trajectories for
fine-tuning:

```
TaskRun ──▶ TrajectoryExporter ──▶ JSONL
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              SFT Dataset    Repair Dataset   Preference Dataset
              (verified)     (fail→fix)       (good vs bad)
                    │               │               │
                    └───────┬───────┘               │
                            ▼                       │
                     TrajectoryFilter              │
                     (quality scores)              │
                            │                       │
                            ▼                       │
                     DatasetBuilder ────────────────┘
                     (train/val split, stats)
```

- **Module**: `vsrs.training.export`, `vsrs.training.filters`, `vsrs.training.datasets`

## Evaluation & Benchmarking

```
BenchmarkSet ──▶ BenchmarkRunner ──▶ EvaluationReport
                    │                      │
                    │                      ├── per-task scores
                    │                      ├── aggregate rates
                    │                      ├── category breakdowns
                    │                      └── CSV/JSON export
                    │
                    └── AblationHarness
                        (disable components, compare)
```

- **Module**: `vsrs.eval.runner`, `vsrs.eval.scorer`, `vsrs.eval.reports`, `vsrs.eval.ablations`, `vsrs.eval.tasks`

## Module Reference

| Module | Description |
|--------|-------------|
| `vsrs.core` | Schemas, config, store, IDs, logging, sandbox |
| `vsrs.repo` | Repository indexing and retrieval |
| `vsrs.reasoning` | Reasoning protocol, reasoner, task parser, patcher |
| `vsrs.verify` | Verification pipeline, pytest adapter |
| `vsrs.repair` | Repair reasoner, failure categorization |
| `vsrs.review` | Critic, review findings, final decision |
| `vsrs.provenance` | Evidence graph, provenance store, audit trail |
| `vsrs.api` | FastAPI REST API server |
| `vsrs.llm` | LLM client, cost tracking, prompt rendering, reasoners |
| `vsrs.training` | Trajectory export, filters, dataset builder |
| `vsrs.eval` | Benchmark tasks, scorer, reports, ablations, runner |
| `vsrs.cli` | Command-line interface |
