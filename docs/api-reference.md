# VSRS API Reference

## Base URL

```
http://localhost:8000
```

## Interactive Docs

- **Swagger UI**: `/docs`
- **ReDoc**: `/redoc`

## Health

### `GET /health`

Returns the health status of the API server.

**Response**:
```json
{
  "status": "ok"
}
```

---

## Runs

### `POST /api/v1/runs`

Create a new task run. Creates a repository snapshot, task, and run record.

**Request Body** (`RunRequest`):
```json
{
  "repo_path": "/path/to/repo",
  "task_instruction": "Fix the empty password bug",
  "task_type": "bugfix",
  "risk": "low",
  "acceptance_criteria": ["empty password must be rejected"]
}
```

**Response** (`RunResponse`):
```json
{
  "run_id": "run_abc123",
  "task_id": "task_xyz789",
  "state": "intake",
  "started_at": "2024-01-01T00:00:00Z",
  "attempt_no": 0,
  "max_attempts": 3
}
```

**Errors**:
- `400`: Repository not found

---

### `GET /api/v1/runs/{run_id}`

Get the status of a specific run.

**Response** (`RunResponse`):
```json
{
  "run_id": "run_abc123",
  "task_id": "task_xyz789",
  "state": "verified",
  "started_at": "2024-01-01T00:00:00Z",
  "attempt_no": 1,
  "max_attempts": 3
}
```

**Errors**:
- `404`: Run not found

---

### `GET /api/v1/runs/{run_id}/task`

Get the task details for a run.

**Response** (`TaskResponse`):
```json
{
  "id": "task_xyz789",
  "type": "bugfix",
  "instruction": "Fix the empty password bug",
  "acceptance_criteria": ["empty password must be rejected"],
  "risk_level": "low",
  "required_gates": ["syntax", "build", "existing_tests"]
}
```

**Errors**:
- `404`: Run or task not found

---

## Evidence

### `GET /api/v1/runs/{run_id}/evidence`

Get all evidence items retrieved for a run's task.

**Response** (`EvidenceListResponse`):
```json
{
  "items": [
    {
      "id": "ev_001",
      "type": "structural",
      "locator": "src/auth.py:10",
      "content": "def validate_password(pw): ..."
    }
  ]
}
```

**Errors**:
- `404`: Run not found

---

## Diff

### `GET /api/v1/runs/{run_id}/diff`

Get the latest patch diff for a run.

**Response** (`DiffResponse`):
```json
{
  "id": "patch_001",
  "diff": "--- a/src/auth.py\n+++ b/src/auth.py\n@@ -1,2 +1,3 @@\n...",
  "changed_files": ["src/auth.py"],
  "changed_symbols": ["validate_password"],
  "attempt_no": 1
}
```

**Errors**:
- `404`: Run or patch not found

---

## Verification

### `GET /api/v1/runs/{run_id}/verify`

Get the verification report for a run.

**Response** (`VerifyResponse`):
```json
{
  "checks": [
    {"check_type": "syntax", "status": "pass", "command": "python -c 'import ast'"},
    {"check_type": "existing_tests", "status": "pass", "command": "pytest"}
  ],
  "required_passed": true,
  "blockers": [],
  "unresolved_unknowns": []
}
```

---

## Review

### `GET /api/v1/runs/{run_id}/review`

Get the critic review findings and final decision for a run.

**Response** (`ReviewResponse`):
```json
{
  "findings": [
    {
      "id": "finding_001",
      "severity": "minor",
      "category": "test_gap",
      "text": "No new targeted test for empty password case"
    }
  ],
  "final_decision": {
    "status": "verified_candidate",
    "blockers": [],
    "summary": "Patch verified with minor finding."
  }
}
```

---

## Provenance

### `GET /api/v1/runs/{run_id}/provenance`

Get the provenance graph for a run.

**Query Parameters**:
- `format`: `tree` (default) or `summary`

**Response (tree)** (`ProvenanceTreeResponse`):
```json
{
  "edges": [
    {"from_id": "run_001", "relation": "executes", "to_id": "task_001"},
    {"from_id": "run_001", "relation": "generates", "to_id": "patch_001"}
  ],
  "summary": null
}
```

**Response (summary)**:
```json
{
  "edges": [],
  "summary": {
    "total_nodes": 5,
    "total_edges": 4,
    "node_types": {"run": 1, "task": 1, "patch": 1, "evidence": 2},
    "edge_types": {"executes": 1, "generates": 1, "retrieves": 2}
  }
}
```

---

## Report

### `GET /api/v1/runs/{run_id}/report`

Generate a markdown report for a run.

**Response**: `text/markdown`

```markdown
# VSRS Run Report

**Run ID**: run_abc123
**Task**: Fix the empty password bug
**Status**: verified
...
```

---

## Export

### `GET /api/v1/runs/{run_id}/export`

Export a run as a training trajectory.

**Response** (`ExportResponse`):
```json
{
  "trajectory": {
    "task": {"id": "task_001", "instruction": "Fix the empty password bug", ...},
    "patch_attempts": [{"id": "patch_001", "diff": "...", ...}],
    "verification_results": [...],
    "final_status": "verified_candidate",
    ...
  }
}
```

---

## Task History

### `GET /api/v1/tasks/{task_id}/history`

Get all runs for a specific task.

**Response** (`HistoryResponse`):
```json
{
  "task_id": "task_001",
  "runs": [
    {"run_id": "run_001", "state": "verified", "attempt_no": 1},
    {"run_id": "run_002", "state": "rejected", "attempt_no": 1}
  ]
}
```

---

## Configuration

### `GET /api/v1/config`

Get the current VSRS configuration.

**Response** (`ConfigResponse`):
```json
{
  "config": {
    "database": {"url": "~/.vsrs/vsrs.db"},
    "model": {"provider": "openai", "model_name": "gpt-4o", "max_tokens": 4096},
    "verification": {"max_repair_attempts": 3, "required_gates": ["syntax", "build", "existing_tests"]},
    "sandbox": {"use_docker": false, "network_disabled": true}
  }
}
```

### `POST /api/v1/config/validate`

Validate the current configuration.

**Response** (`ConfigValidationResponse`):
```json
{
  "valid": true,
  "errors": []
}
```

---

## Benchmarks

### `GET /api/v1/benchmarks`

List all available benchmark tasks.

**Response** (`BenchmarkListResponse`):
```json
{
  "tasks": [
    {
      "id": "bench-001",
      "name": "empty-password-rejection",
      "description": "Fix login bug where an empty password is accepted",
      "task_type": "bugfix",
      "difficulty": "easy",
      "tags": ["auth", "validation", "bugfix"]
    }
  ]
}
```

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `vsrs run` | Run the full pipeline on a task |
| `vsrs status` | Show run status |
| `vsrs evidence` | Show evidence for a run |
| `vsrs diff` | Show the latest patch diff |
| `vsrs verify` | Show verification report |
| `vsrs audit-trail` | Show provenance audit trail |
| `vsrs review` | Show critic review |
| `vsrs report` | Generate markdown report |
| `vsrs provenance` | Show provenance graph |
| `vsrs config` | Show or validate configuration |
| `vsrs benchmark` | Run benchmark suite |

---

## Error Codes

| Code | Description |
|------|-------------|
| `400` | Bad request (invalid input, repo not found) |
| `404` | Resource not found |
| `422` | Validation error (Pydantic) |
| `500` | Internal server error |
