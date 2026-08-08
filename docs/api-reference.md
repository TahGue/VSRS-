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

## Authentication

Enterprise API endpoints require a valid API key passed via the `X-API-Key` header.

### Scopes

| Scope | Access |
|-------|--------|
| `admin:all` | Full access to all endpoints |
| `tenant:admin` | Tenant and project CRUD operations |
| `sso:admin` | SSO cleanup operations |
| `read` | Read-only access to GET endpoints |

### Example

```bash
curl -H "X-API-Key: vsrs_your_key_here" \
  http://localhost:8000/api/v1/tenants
```

---

## Enterprise Endpoints

### Tenant Management

#### `POST /api/v1/tenants`

Create a new tenant with resource quotas. **Requires `tenant:admin` scope.**

**Request**:
```json
{
  "tenant_id": "acme",
  "name": "Acme Corp",
  "max_projects": 20,
  "max_runs_per_day": 500
}
```

#### `GET /api/v1/tenants`

List all tenants. **Requires valid API key.**

#### `GET /api/v1/tenants/{id}`

Get tenant details. **Requires valid API key.**

#### `GET /api/v1/tenants/{id}/usage`

Get tenant resource usage. **Requires valid API key.**

#### `POST /api/v1/tenants/{id}/suspend`

Suspend a tenant. **Requires `tenant:admin` scope.**

#### `POST /api/v1/tenants/{id}/reactivate`

Reactivate a suspended tenant. **Requires `tenant:admin` scope.**

#### `DELETE /api/v1/tenants/{id}`

Delete a tenant. **Requires `tenant:admin` scope.**

### Project Management

#### `POST /api/v1/tenants/{id}/projects`

Create a project within a tenant. **Requires `tenant:admin` scope.**

#### `GET /api/v1/tenants/{id}/projects`

List all projects for a tenant. **Requires valid API key.**

#### `DELETE /api/v1/tenants/{id}/projects/{pid}`

Delete a project. **Requires `tenant:admin` scope.**

### SSO Management

#### `GET /api/v1/sso/providers`

List configured SSO providers. **Requires valid API key.**

#### `GET /api/v1/sso/sessions`

List active SSO sessions. **Requires valid API key.**

#### `GET /api/v1/sso/users`

List SSO-provisioned users. **Requires valid API key.**

#### `POST /api/v1/sso/cleanup`

Remove expired SSO sessions. **Requires `sso:admin` scope.**

### Worker Pool

#### `GET /api/v1/pool/stats`

Get worker pool statistics. **Requires valid API key.**

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
| `vsrs tenant create/list/show/suspend/reactivate/delete` | Manage tenants |
| `vsrs sso list-providers/list-sessions/cleanup/list-users` | Manage SSO |
| `vsrs pool stats` | Show worker pool statistics |
| `vsrs key create/list/revoke/validate/count` | Manage API keys |
| `vsrs audit list/count/export` | Query and export audit logs |

---

## Error Codes

| Code | Description |
|------|-------------|
| `400` | Bad request (invalid input, repo not found) |
| `401` | Missing or invalid API key |
| `403` | Insufficient scope or permission |
| `404` | Resource not found |
| `409` | Conflict (duplicate resource) |
| `422` | Validation error (Pydantic) |
| `429` | Rate limit exceeded |
| `500` | Internal server error |
