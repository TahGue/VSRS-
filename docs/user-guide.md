# VSRS User Guide

This guide explains how to install, configure, and use the Verified Software Reasoning System (VSRS) end-to-end.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Configuration](#2-configuration)
3. [Quick Start](#3-quick-start)
4. [CLI Commands](#4-cli-commands)
5. [Task Definitions](#5-task-definitions)
6. [Verification Gates](#6-verification-gates)
7. [API Server](#7-api-server)
8. [Web Dashboard](#8-web-dashboard)
9. [VSCode Extension](#9-vscode-extension)
10. [Multi-Language Support](#10-multi-language-support)
11. [Benchmarking & Evaluation](#11-benchmarking--evaluation)
12. [Distributed Execution](#12-distributed-execution)
13. [Fine-Tuning Pipeline](#13-fine-tuning-pipeline)
14. [Enterprise Features](#14-enterprise-features)
15. [Multi-Tenant Project Isolation](#15-multi-tenant-project-isolation)
16. [SSO Integration](#16-sso-integration)
17. [Worker Pool & Auto-Scaling](#17-worker-pool--auto-scaling)
18. [Plugin System](#18-plugin-system)
19. [Troubleshooting](#19-troubleshooting)

---

## 1. Installation

### Prerequisites

- **Python 3.12+**
- **Git** (for repository snapshots)
- **Docker** (optional, for sandboxed verification)

### Install from source

```bash
git clone https://github.com/TahGue/VSRS-.git
cd VSRS-
pip install -e ".[dev]"
```

### Install with optional extras

```bash
# For the API server
pip install -e ".[api]"

# For LLM integration (OpenAI)
pip install -e ".[llm]"

# For LLM integration (Anthropic)
pip install -e ".[llm-anthropic]"

# For tree-sitter multi-language indexing
pip install -e ".[tree-sitter]"

# For everything
pip install -e ".[dev,api,llm,llm-anthropic,tree-sitter]"
```

### Verify installation

```bash
vsrs --help
```

You should see the list of available commands.

---

## 2. Configuration

VSRS uses a YAML configuration file. Generate a default config:

```bash
vsrs config init
```

This creates `~/.vsrs/config.yaml`. Edit it to match your environment.

### Configuration reference

```yaml
# Database for storing runs, tasks, patches, and evidence
database:
  url: ~/.vsrs/vsrs.db

# LLM provider for reasoning and patch generation
model:
  provider: stub          # stub | openai | anthropic
  model_name: gpt-4
  max_tokens: 4096
  temperature: 0.2
  api_key: ${OPENAI_API_KEY}   # or hardcode (not recommended)

# Verification settings
verification:
  max_repair_attempts: 3
  required_gates:           # Gates that MUST pass
    - syntax
    - build
    - existing_tests
  optional_gates:           # Gates that are checked but not blocking
    - type_check
    - lint

# Sandbox for isolated verification
sandbox:
  use_docker: false         # Set true for Docker-based isolation
  worktree_dir: ~/.vsrs/worktrees
  network_disabled: true
  wall_time_limit_seconds: 300
```

### Provider configurations

**Local/Stub** (no API key needed, for testing):
```yaml
model:
  provider: stub
  model_name: stub
```

**OpenAI**:
```yaml
model:
  provider: openai
  model_name: gpt-4
  api_key: ${OPENAI_API_KEY}
```

**Anthropic**:
```yaml
model:
  provider: anthropic
  model_name: claude-3-opus-20240229
  api_key: ${ANTHROPIC_API_KEY}
```

### Validate configuration

```bash
vsrs config validate
```

---

## 3. Quick Start

### Step 1: Create a task definition

Create a file `my-task.json`:

```json
{
  "instruction": "Fix the off-by-one error in the loop at line 42 of utils.py",
  "type": "bugfix",
  "risk": "low",
  "acceptance_criteria": [
    "All existing tests pass",
    "The loop iterates correctly for edge cases"
  ]
}
```

Or use Markdown:

```markdown
Fix the off-by-one error in the loop at line 42 of utils.py.

The loop should handle empty lists correctly.
```

### Step 2: Run the task

```bash
vsrs run --repo ./my-project --task my-task.json
```

VSRS will:
1. Snapshot your repository
2. Retrieve evidence (file contents, tests, git history)
3. Reason about the change
4. Generate a patch
5. Verify it (syntax, build, tests, lint, types)
6. Repair if verification fails (up to 3 attempts)
7. Review the result with a critic

### Step 3: Check the result

```bash
# Check status
vsrs status <RUN_ID>

# View the patch diff
vsrs diff <RUN_ID>

# View verification results
vsrs verify <RUN_ID>

# View the critic review
vsrs review <RUN_ID>

# Generate a full report
vsrs report <RUN_ID> --output report.md

# View the provenance audit trail
vsrs audit-trail <RUN_ID>
```

---

## 4. CLI Commands

### Core commands

| Command | Description |
|---------|-------------|
| `vsrs run --repo <path> --task <file>` | Start a new task run |
| `vsrs status <RUN_ID>` | Check run status |
| `vsrs evidence <RUN_ID>` | View evidence items |
| `vsrs diff <RUN_ID>` | View the latest patch diff |
| `vsrs verify <RUN_ID> [--rerun]` | View or re-run verification |
| `vsrs review <RUN_ID>` | View critic findings and decision |
| `vsrs report <RUN_ID> --output <file>` | Generate a full markdown report |
| `vsrs audit-trail <RUN_ID>` | View provenance audit trail |
| `vsrs provenance <RUN_ID>` | View provenance graph |
| `vsrs history <TASK_ID>` | View task history across runs |
| `vsrs export <RUN_ID> --output <dir>` | Export run data as JSON |

### Benchmark commands

```bash
# List available benchmarks
vsrs benchmark list

# Show a specific benchmark
vsrs benchmark show <benchmark_id>

# Save benchmark results
vsrs benchmark save --output ./benchmark-results/
```

### Config commands

```bash
# Show current configuration
vsrs config show

# Initialize a default config file
vsrs config init

# Validate configuration
vsrs config validate
```

### Enterprise commands

```bash
# Tenant management
vsrs tenant create --id acme --name "Acme Corp" --max-projects 20
vsrs tenant list
vsrs tenant show <tenant_id>
vsrs tenant suspend <tenant_id>
vsrs tenant reactivate <tenant_id>
vsrs tenant delete <tenant_id> --force

# SSO management
vsrs sso list-providers
vsrs sso list-sessions
vsrs sso list-users
vsrs sso cleanup

# Worker pool
vsrs pool stats
```

### Command options

```bash
# Run with specific task type and risk level
vsrs run --repo ./my-project --task task.json --type feature --risk medium

# Run with a markdown task file
vsrs run --repo ./my-project --task task.md

# Re-run verification on an existing run
vsrs verify <RUN_ID> --rerun
```

---

## 5. Task Definitions

Tasks tell VSRS what to do. They can be JSON or Markdown.

### JSON format

```json
{
  "instruction": "Add input validation to the login form",
  "type": "feature",
  "risk": "medium",
  "acceptance_criteria": [
    "Empty username/password shows error message",
    "SQL injection attempts are blocked",
    "Existing login tests still pass"
  ]
}
```

### Markdown format

```markdown
Add input validation to the login form.

The form should reject empty usernames and passwords.
SQL injection attempts should be blocked.
```

### Task types

| Type | Description |
|------|-------------|
| `bugfix` | Fix a bug (default) |
| `feature` | Add new functionality |
| `refactor` | Restructure code without changing behavior |
| `test` | Add or improve tests |
| `security` | Fix a security vulnerability |
| `migration` | Migrate to a new framework/API |

### Risk levels

| Level | Description |
|-------|-------------|
| `low` | Small, isolated change (default) |
| `medium` | Moderate impact, may affect multiple files |
| `high` | Significant change, requires careful review |

---

## 6. Verification Gates

Gates are the checks that a patch must pass to be "verified."

### Built-in gates

| Gate | Description |
|------|-------------|
| `syntax` | Python syntax check (`py_compile`) |
| `build` | Package/build check |
| `existing_tests` | Run existing test suite (`pytest`) |
| `type_check` | Type checking (`mypy`) |
| `lint` | Linting (`ruff`) |
| `bandit` | Security scanning |

### How gates work

1. **Required gates** must all pass for the patch to be verified
2. **Optional gates** are checked but don't block verification
3. If any required gate fails, VSRS enters the repair loop
4. After `max_repair_attempts` failures, the run is marked as failed

### Customizing gates

In your config:

```yaml
verification:
  max_repair_attempts: 5
  required_gates:
    - syntax
    - build
    - existing_tests
    - type_check
  optional_gates:
    - lint
    - bandit
```

---

## 7. API Server

VSRS includes a FastAPI server for programmatic access.

### Start the server

```bash
# Install API dependencies
pip install -e ".[api]"

# Start the server
python -m uvicorn vsrs.api.app:app --port 8000
```

### Interactive docs

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/runs` | Create a new run |
| `GET` | `/api/v1/runs/{run_id}` | Get run status |
| `GET` | `/api/v1/runs/{run_id}/task` | Get task details |
| `GET` | `/api/v1/runs/{run_id}/evidence` | Get evidence items |
| `GET` | `/api/v1/runs/{run_id}/diff` | Get patch diff |
| `GET` | `/api/v1/runs/{run_id}/verify` | Get verification report |
| `GET` | `/api/v1/runs/{run_id}/review` | Get critic review |
| `GET` | `/api/v1/runs/{run_id}/provenance` | Get provenance graph |
| `GET` | `/api/v1/runs/{run_id}/report` | Get full report (markdown) |
| `GET` | `/api/v1/config` | Get configuration |
| `GET` | `/api/v1/benchmarks` | List benchmarks |
| `WS` | `/ws/runs/{run_id}` | Real-time progress streaming |
| `POST` | `/api/v1/tenants` | Create a tenant |
| `GET` | `/api/v1/tenants` | List all tenants |
| `GET` | `/api/v1/tenants/{id}` | Get tenant details |
| `GET` | `/api/v1/tenants/{id}/usage` | Get tenant resource usage |
| `POST` | `/api/v1/tenants/{id}/suspend` | Suspend a tenant |
| `POST` | `/api/v1/tenants/{id}/reactivate` | Reactivate a tenant |
| `DELETE` | `/api/v1/tenants/{id}` | Delete a tenant |
| `POST` | `/api/v1/tenants/{id}/projects` | Create a project |
| `GET` | `/api/v1/tenants/{id}/projects` | List tenant projects |
| `DELETE` | `/api/v1/tenants/{id}/projects/{pid}` | Delete a project |
| `GET` | `/api/v1/sso/providers` | List SSO providers |
| `GET` | `/api/v1/sso/sessions` | List active SSO sessions |
| `GET` | `/api/v1/sso/users` | List SSO-provisioned users |
| `POST` | `/api/v1/sso/cleanup` | Remove expired SSO sessions |
| `GET` | `/api/v1/pool/stats` | Get worker pool statistics |

### Example: Create a run via API

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": "/path/to/my-repo",
    "task_instruction": "Fix the bug in utils.py",
    "task_type": "bugfix"
  }'
```

### Example: Get verification results

```bash
curl http://localhost:8000/api/v1/runs/{run_id}/verify
```

---

## 8. Web Dashboard

VSRS includes a React-based web dashboard for visual run management.

### Development mode

```bash
cd web-dashboard
npm install
npm run dev
```

The dashboard runs on http://localhost:5173 and proxies API requests to `http://localhost:8000`.

### Production build

```bash
cd web-dashboard
npm run build
```

The built files go to `web-dashboard/dist/` and can be served by any static file server.

### Dashboard features

- **Runs page**: List all runs, create new runs with a form
- **Run detail**: View run info, task, verification checks with pass/fail status, diff viewer with syntax highlighting
- **Benchmarks**: Browse available benchmark suites
- **Settings**: View current configuration

---

## 9. VSCode Extension

VSRS includes a VSCode extension for running tasks directly from the editor.

### Setup

1. Start the API server: `python -m uvicorn vsrs.api.app:app --port 8000`
2. Open VSCode settings and configure:
   - `vsrs.serverUrl`: `http://localhost:8000`
   - `vsrs.apiKey`: Your API key (if using enterprise auth)
   - `vsrs.maxAttempts`: Maximum repair attempts (default: 3)
   - `vsrs.requiredGates`: Required verification gates
3. Use `Ctrl+Shift+P` and search for "VSRS" commands

### Keybindings

| Shortcut | Command |
|----------|---------|
| `Ctrl+Shift+V` | Run verification |
| `Ctrl+Shift+R` | Run repair |

### Features

- Sidebar task tree view with status icons
- Status bar showing connection state
- Webview panel with verification results
- Auto-verify on save (configurable)

See `vscode-extension/README.md` for full details.

---

## 10. Multi-Language Support

VSRS supports verification across multiple programming languages.

### Supported languages

| Language | Syntax Check | Build | Tests | Lint | Type Check |
|----------|-------------|-------|-------|------|------------|
| Python | `py_compile` | — | `pytest` | `ruff` | `mypy` |
| Go | `gofmt` | `go build` | `go test` | `go vet` | — |
| Rust | `rustc --parse` | `cargo build` | `cargo test` | `clippy` | — |
| TypeScript | `tsc --noEmit` | `tsc` | `jest` | `eslint` | `tsc` |
| Java | `javac` | `mvn/gradle` | `mvn/gradle test` | `checkstyle` | `javac` |

### How it works

VSRS detects languages from changed files in the patch and runs the appropriate checks for each language. The `MultiLanguageVerificationRunner` coordinates this automatically.

### Adding a new language

Implement the `LanguageAdapter` ABC:

```python
from vsrs.languages.base import LanguageAdapter, LanguageInfo

class MyLanguageAdapter(LanguageAdapter):
    @property
    def info(self) -> LanguageInfo:
        return LanguageInfo(
            name="mylang",
            extensions=[".my"],
            display_name="My Language",
        )

    def syntax_check(self, files, repo_path):
        # Run syntax check
        ...

    def run_tests(self, files, repo_path):
        # Run tests
        ...
```

Register it:

```python
from vsrs.languages import LanguageRegistry
LanguageRegistry.register(MyLanguageAdapter())
```

---

## 11. Benchmarking & Evaluation

### Running benchmarks

```bash
# List available benchmarks
vsrs benchmark list

# Show a specific benchmark
vsrs benchmark show <id>

# Save benchmark results to disk
vsrs benchmark save --output ./results/
```

### Benchmark tasks

Benchmarks are stored as JSON files in a directory. Each file is a `BenchmarkTask`:

```json
{
  "id": "task-001",
  "instruction": "Fix the null pointer dereference in parser.py",
  "type": "bugfix",
  "difficulty": "easy",
  "tags": ["python", "null-pointer"],
  "expected_files": ["src/parser.py"],
  "acceptance_criteria": ["All tests pass"]
}
```

### Evaluation

VSRS evaluates runs using the `Scorer` which computes:

- **verified_success**: Did the patch pass all gates?
- **pass_at_1**: First-attempt success rate
- **regression**: Did the patch break existing tests?
- **grounding_errors**: Did the patch reference non-existent code?
- **repair_needed**: How many repair attempts were needed?

### Programmatic evaluation

```python
from vsrs.eval.scorer import score_task
from vsrs.eval.reports import EvaluationReport

# Score a single task
result = score_task(run, verification_report, patch)

# Aggregate scores into a report
report = EvaluationReport.from_scores([result1, result2, ...])
print(report.summary())
```

---

## 12. Distributed Execution

VSRS supports distributed benchmark execution using a task queue.

### In-memory queue (for testing)

```python
from vsrs.distributed import InMemoryQueue, Worker, DistributedBenchmarkRunner

queue = InMemoryQueue()
worker = Worker(queue)
worker.start()

runner = DistributedBenchmarkRunner(queue, num_workers=4)
results = runner.run_benchmark(benchmark_set)
```

### Redis queue (for production)

```python
from vsrs.distributed import RedisQueue, Worker

queue = RedisQueue(host="localhost", port=6379)
worker = Worker(queue)
worker.start()
```

### Worker management

```python
# Start multiple workers
workers = [Worker(queue) for _ in range(8)]
for w in workers:
    w.start()

# Check stats
for w in workers:
    print(w.stats)

# Stop workers
for w in workers:
    w.stop()
```

### Worker pool with resource allocation

For production use, see [Section 17: Worker Pool & Auto-Scaling](#17-worker-pool--auto-scaling) for resource-aware scheduling, auto-scaling, and health monitoring.

---

## 13. Fine-Tuning Pipeline

VSRS includes tools for fine-tuning LLMs on verification trajectories.

### Export training data

```bash
vsrs export <RUN_ID> --output ./training-data/
```

### Dataset versioning

```python
from vsrs.finetuning import DatasetVersionManager

manager = DatasetVersionManager(storage_dir="./datasets")
version = manager.create_version(
    name="v1-bugfix",
    trajectories=trajectories,
    description="Bugfix trajectories from production runs",
)
```

### Fine-tuning jobs

```python
from vsrs.finetuning import JobOrchestrator, FineTuningMethod

orchestrator = JobOrchestrator()
job = orchestrator.create_job(
    dataset_version_id=version.id,
    method=FineTuningMethod.lora,
    base_model="meta-llama/Llama-2-7b",
    config={"lora_r": 16, "lora_alpha": 32},
)
orchestrator.start_job(job.id)
```

### A/B comparison

```python
from vsrs.finetuning import ModelComparisonHarness

harness = ModelComparisonHarness()
comparison = harness.compare(
    model_a="base-model",
    model_b="fine-tuned-model",
    benchmark_set=benchmark_set,
)
print(comparison.aggregate_delta)
```

---

## 14. Enterprise Features

### Authentication

```python
from vsrs.enterprise import APIKeyManager

manager = APIKeyManager()
key = manager.create_key(user_id="user-1", scopes=["read", "write"])
# key.plaintext_key is shown once — store it securely
```

### Role-based access control

```python
from vsrs.enterprise import RoleManager, Permission

role_manager = RoleManager()
admin_role = role_manager.create_role("admin", permissions=list(Permission))
developer_role = role_manager.create_role(
    "developer",
    permissions=[Permission.RUN_TASK, Permission.VIEW_RESULTS],
)
```

### Audit logging

```python
from vsrs.enterprise import AuditLogger, AuditEventType

logger = AuditLogger()
logger.log(
    event_type=AuditEventType.TASK_STARTED,
    user_id="user-1",
    resource="run/abc-123",
    details={"task_type": "bugfix"},
)
```

### Rate limiting

```python
from vsrs.enterprise import RateLimiter, RateLimitConfig

limiter = RateLimiter(RateLimitConfig(
    requests_per_minute=100,
    strategy="sliding_window",
))
result = limiter.check("client-api-key-123")
if not result.allowed:
    print(f"Rate limited. Retry after {result.retry_after_seconds}s")
```

---

## 15. Multi-Tenant Project Isolation

VSRS supports multi-tenant isolation, allowing multiple teams to share a single VSRS instance with isolated projects and configurable resource quotas.

### Creating tenants

```python
from vsrs.enterprise import TenantManager, ResourceQuota

mgr = TenantManager()

tenant = mgr.create_tenant(
    tenant_id="acme",
    name="Acme Corporation",
    slug="acme",
    quota=ResourceQuota(
        max_projects=20,
        max_runs_per_day=500,
        max_concurrent_runs=10,
        max_storage_mb=10240,
        max_api_keys=20,
    ),
)
```

### Managing projects

```python
# Create a project within a tenant
project = mgr.create_project(
    project_id="web-app",
    tenant_id="acme",
    name="Web Application",
    repo_root="/repos/acme/web-app",
)

# List all projects for a tenant
projects = mgr.list_projects("acme")

# Delete a project
mgr.delete_project("web-app")
```

### Resource quotas

Quotas limit resource consumption per tenant:

| Resource | Default | Description |
|----------|---------|-------------|
| `max_projects` | 10 | Maximum number of projects |
| `max_runs_per_day` | 100 | Maximum runs per day |
| `max_concurrent_runs` | 5 | Maximum concurrent runs |
| `max_storage_mb` | 1024 | Maximum storage in MB |
| `max_api_keys` | 10 | Maximum API keys |

Use `ResourceQuota.unlimited()` for no limits (-1 values).

### Quota enforcement

```python
# Check if a run is allowed
mgr.check_run_allowed("acme")  # Raises QuotaExceededError if over quota

# Record run start/end
mgr.record_run_start("acme")
mgr.record_run_end("acme")

# Check storage
mgr.check_storage_allowed("acme", additional_mb=50)

# Get usage summary
summary = mgr.get_usage_summary("acme")
print(summary["limits"]["runs_today"]["remaining"])
```

### Tenant lifecycle

```python
# Suspend a tenant
mgr.suspend_tenant("acme")

# Reactivate
mgr.reactivate_tenant("acme")

# Delete (removes all projects)
mgr.delete_tenant("acme")
```

---

## 16. SSO Integration

VSRS supports SAML 2.0 and OpenID Connect (OIDC) for enterprise single sign-on.

### Registering providers

**SAML provider**:
```python
from vsrs.enterprise import SSOManager, SAMLProvider

sso = SSOManager()
sso.register_saml_provider(SAMLProvider(
    id="okta",
    name="Okta",
    entity_id="https://okta.com/entity",
    sso_url="https://okta.com/sso",
    slo_url="https://okta.com/slo",
    x509_cert="-----BEGIN CERTIFICATE-----...",
    audience="vsrs",
))
```

**OIDC provider**:
```python
from vsrs.enterprise import SSOManager, OIDCProvider

sso = SSOManager()
sso.register_oidc_provider(OIDCProvider(
    id="google",
    name="Google",
    issuer_url="https://accounts.google.com",
    client_id="your-client-id",
    client_secret="your-secret",
    authorize_url="https://accounts.google.com/o/oauth2/auth",
    token_url="https://oauth2.googleapis.com/token",
    userinfo_url="https://www.googleapis.com/oauth2/v2/userinfo",
    scopes=["openid", "email", "profile"],
))
```

### OIDC authentication flow

```python
# 1. Redirect user to authorize URL
url = sso.get_oidc_authorize_url("google", redirect_uri="https://vsrs.local/callback")

# 2. After callback, validate the ID token and create a session
session = sso.authenticate_oidc("google", id_token="eyJ...", userinfo=userinfo_dict)
print(session.user_id)
print(session.token)  # Use this token for subsequent requests
```

### SAML authentication flow

```python
# 1. Redirect user to SAML SSO URL
url = sso.get_saml_redirect_url("okta", relay_state="return_to=/dashboard")

# 2. After callback, validate the SAML response
session = sso.authenticate_saml("okta", saml_response=base64_encoded_response)
```

### Session management

```python
# Get session by token
session = sso.get_session(token)

# Refresh session (extend by 8 hours)
sso.refresh_session(session.id, extend_hours=8)

# Logout
sso.logout(token)

# Cleanup expired sessions
removed = sso.cleanup_expired_sessions()
```

### Automatic user provisioning

Users are automatically provisioned from IdP attributes on first login. Subsequent logins update the user's profile.

```python
users = sso.list_users()
print(f"{sso.user_count} users provisioned")
```

---

## 17. Worker Pool & Auto-Scaling

VSRS provides a worker pool with resource-aware scheduling and auto-scaling for distributed verification.

### Creating a worker pool

```python
from vsrs.distributed import WorkerPool, PoolConfig, ResourceSpec

pool = WorkerPool(
    queue=InMemoryQueue(),
    config=PoolConfig(
        min_workers=2,
        max_workers=20,
        scale_up_threshold=5,
        scale_down_threshold=0,
        health_check_interval=10.0,
        heartbeat_timeout=60.0,
        default_worker_capacity=ResourceSpec(cpu=4.0, memory_mb=4096),
    ),
)
```

### Adding workers with custom capacity

```python
# Small worker for lightweight tasks
pool.add_worker(
    worker_id="small-1",
    capacity=ResourceSpec(cpu=1.0, memory_mb=512),
    handlers={"test": lambda job: {"result": "ok"}},
)

# Large worker with GPU for heavy verification
pool.add_worker(
    worker_id="gpu-1",
    capacity=ResourceSpec(cpu=8.0, memory_mb=16384, gpu=1),
)
```

### Resource-aware job scheduling

```python
from vsrs.distributed import TaskJob, ResourceSpec

job = TaskJob(id="job-1", task_type="verify", payload={"file": "main.py"})

# Submit with resource requirements
pool.submit_job(job, resources=ResourceSpec(cpu=2.0, memory_mb=2048))

# Process synchronously on a capable worker
result = pool.process_job_on_worker(job, resources=ResourceSpec(cpu=2.0, memory_mb=2048))
```

### Auto-scaling

The pool automatically scales up when queue depth exceeds `scale_up_threshold` and scales down when workers are idle:

```python
# Start the pool with auto-scaling
pool.start()

# The pool maintains min_workers and scales up to max_workers
print(pool.pool_stats())

# Stop gracefully (drains workers)
pool.stop()
```

### Health monitoring

Workers send heartbeats to indicate they're alive. Unhealthy workers are automatically replaced:

```python
# Record a heartbeat
pool.heartbeat("worker-1")

# Pool stats include health info
stats = pool.pool_stats()
print(f"Unhealthy: {stats['unhealthy_count']}")
```

### Pool statistics

```python
stats = pool.pool_stats()
# {
#   "worker_count": 5,
#   "idle_count": 3,
#   "busy_count": 2,
#   "unhealthy_count": 0,
#   "queue_size": 1,
#   "total_capacity": {"cpu": 20.0, "memory_mb": 20480, ...},
#   "total_available": {"cpu": 16.0, "memory_mb": 16384, ...},
# }
```

---

## 18. Plugin System

VSRS supports custom plugins for verification, retrieval, and criticism.

### Built-in plugins

| Plugin | Type | Description |
|--------|------|-------------|
| `FileSizeVerifier` | Verifier | Checks patch doesn't exceed size limit |
| `ImportCheckerVerifier` | Verifier | Validates no new imports break |
| `GitLogRetriever` | Retriever | Retrieves git history as evidence |
| `MinimalityCritic` | Critic | Reviews patch for minimal changes |
| `SecurityCritic` | Critic | Reviews patch for security issues |

### Writing a custom plugin

```python
from vsrs.plugins import VerifierPlugin, PluginRegistry

class MyVerifier(VerifierPlugin):
    @property
    def name(self) -> str:
        return "my-verifier"

    @property
    def check_type(self) -> str:
        return "my_check"

    def verify(self, patch, repo_path):
        # Run your custom check
        return CheckResult(
            check_type="my_check",
            command="my-tool",
            exit_code=0,
            status=CheckStatus.pass_,
            duration_seconds=0.1,
            error_message="",
        )

# Register it
PluginRegistry.register(MyVerifier())
```

### Plugin discovery

Plugins can be discovered via Python entry points:

```toml
# pyproject.toml
[project.entry-points."vsrs.plugins"]
my-verifier = "my_package:MyVerifier"
```

---

## 19. Troubleshooting

### "ModuleNotFoundError: No module named 'vsrs'"

Make sure you installed the package:
```bash
pip install -e .
```

### "Repository not found" when creating a run

Ensure the path exists and is a git repository:
```bash
cd /path/to/your/repo
git status
```

### Verification fails with "No tests found"

VSRS looks for tests in the repository. Ensure you have a `tests/` directory or pytest-compatible test files.

### LLM connection errors

1. Check your API key is set: `echo $OPENAI_API_KEY`
2. Check your config: `vsrs config validate`
3. Try the stub provider for testing: `provider: stub`

### Docker sandbox issues

If `use_docker: true`:
1. Ensure Docker is running: `docker info`
2. Ensure the VSRS image exists or can be built
3. Check worktree directory permissions

### API server won't start

```bash
# Check if port is in use
lsof -i :8000

# Try a different port
python -m uvicorn vsrs.api.app:app --port 8001
```

### Reset the database

```bash
rm ~/.vsrs/vsrs.db
vsrs config init
```

### Getting help

- **Full architecture**: See [docs/architecture.md](architecture.md)
- **API reference**: See [docs/api-reference.md](api-reference.md)
- **Contributing**: See [docs/contributing.md](contributing.md)
- **Examples**: See [docs/examples/](examples/)
- **Megaplan**: See [MEGAPLAN.md](../MEGAPLAN.md)

---

## Summary

VSRS is a complete platform for evidence-grounded code reasoning and verification:

1. **Define a task** (JSON or Markdown)
2. **Run it** (`vsrs run` or via API/dashboard/extension)
3. **VSRS reasons, patches, verifies, repairs, and reviews**
4. **Inspect results** (CLI, API, web dashboard, or VSCode)
5. **Benchmark, evaluate, and fine-tune** your models
6. **Scale** with distributed execution and worker pool auto-scaling
7. **Secure** with enterprise auth, RBAC, audit, rate limiting, multi-tenancy, and SSO
8. **Isolate** teams with multi-tenant project isolation and resource quotas
