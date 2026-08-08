# VSRS Examples

This directory contains example tasks, configuration files, and usage
scenarios for VSRS.

## Contents

- [`tasks/`](tasks/) — Example task definitions in JSON format
- [`configs/`](configs/) — Example VSRS configuration files
- [`scenarios/`](scenarios/) — End-to-end usage scenarios with expected outputs

## Quick Start

```bash
# Run VSRS on an example task
vsrs run --repo ./my-project --task docs/examples/tasks/empty-password.json

# Run with a custom config
vsrs run --repo ./my-project --task docs/examples/tasks/empty-password.json \
  --config docs/examples/configs/local.yaml

# Run the benchmark suite
vsrs benchmark --set seed --output results.json
```

## Example Tasks

| File | Type | Difficulty | Description |
|------|------|------------|-------------|
| `tasks/empty-password.json` | bugfix | easy | Fix login bug where empty passwords are accepted |
| `tasks/sql-injection.json` | security | hard | Fix SQL injection vulnerability in query builder |
| `tasks/add-rate-limit.json` | feature | medium | Add rate limiting to API endpoints |
| `tasks/extract-utils.json` | refactor | medium | Extract duplicated utility functions into shared module |
| `tasks/add-validation-tests.json` | test | easy | Add tests for input validation logic |

## Example Configs

| File | Description |
|------|-------------|
| `configs/local.yaml` | Local development with stub LLM |
| `configs/openai.yaml` | Production with OpenAI GPT-4o |
| `configs/anthropic.yaml` | Production with Anthropic Claude 3.5 |
| `configs/docker.yaml` | Docker sandbox isolation |
