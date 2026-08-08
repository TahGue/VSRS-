# Contributing to VSRS

Thank you for your interest in contributing to VSRS! This guide covers
development setup, coding standards, testing, and the pull request process.

## Development Setup

### Prerequisites

- Python 3.12+
- Git
- A repository to test against (any Python project with tests)

### Installation

```bash
# Clone the repository
git clone https://github.com/TahGue/VSRS-.git
cd VSRS-

# Install in development mode with all extras
pip install -e ".[dev]"

# For API server support
pip install -e ".[api]"

# For LLM integration
pip install openai  # or: pip install anthropic
```

### Verify Installation

```bash
# Run the test suite
pytest tests/ -q

# Check code style
ruff check src/ tests/

# Type check
mypy src/vsrs/
```

## Project Structure

```
vsrs/
├── src/vsrs/
│   ├── core/           # Schemas, config, store, sandbox, IDs, logging
│   ├── repo/           # Repository indexing and retrieval
│   ├── reasoning/      # Reasoning protocol, reasoner, task parser, patcher
│   ├── verify/         # Verification pipeline, pytest adapter
│   ├── repair/         # Repair reasoner, failure categorization
│   ├── review/         # Critic, review findings, final decision
│   ├── provenance/     # Evidence graph, provenance store
│   ├── api/            # FastAPI REST API server
│   ├── llm/            # LLM client, cost tracking, prompts, reasoners
│   ├── training/       # Trajectory export, filters, datasets
│   ├── eval/           # Benchmark tasks, scorer, reports, ablations
│   └── cli/            # Command-line interface
├── tests/              # Test suite (600+ tests)
├── docs/               # Documentation
├── pyproject.toml      # Project configuration
└── README.md           # Project overview
```

## Coding Standards

### Style

- **Formatter**: Ruff (line length: 100)
- **Type checker**: MyPy (strict mode for core modules)
- **Import style**: `from __future__ import annotations` at top of all files
- **Docstrings**: Google style for all public functions and classes

### Rules

1. **No invented symbols**: Never reference functions, classes, or variables
   that don't exist. This is the core principle of VSRS itself.
2. **Minimal changes**: Keep diffs small and focused. One feature per PR.
3. **Test everything**: Every new function or module must have tests.
4. **No TODO comments in production**: Either implement it or track it as
   an issue. TODOs are acceptable during active development but must be
   resolved before merging.
5. **Structured outputs**: When adding LLM integration, always use Pydantic
   models for validation, never raw strings.

### Running Checks

```bash
# Format check
ruff check src/ tests/

# Type check
mypy src/vsrs/

# Run all tests
pytest tests/ -q

# Run with coverage
pytest tests/ --cov=vsrs --cov-report=term-missing
```

## Testing

### Test Organization

Tests are in `tests/` and follow the naming convention `test_<module>.py`:

- `test_schemas.py` — Core data models
- `test_config.py` — Configuration management
- `test_store.py` — Database storage
- `test_repo_index.py` — Repository indexing
- `test_retrieval.py` — Evidence retrieval
- `test_reasoner.py` — Reasoning pipeline
- `test_patcher.py` — Patch application
- `test_verify.py` — Verification pipeline
- `test_repair.py` — Repair loop
- `test_critic.py` — Critic review
- `test_provenance.py` — Provenance graph
- `test_api.py` — REST API endpoints
- `test_llm.py` — LLM integration
- `test_training.py` — Training data export
- `test_eval.py` — Evaluation and benchmarking
- `test_benchmark.py` — Benchmark tasks
- `test_cli.py` — CLI commands

### Writing Tests

```python
class TestMyFeature:
    def test_basic_functionality(self):
        # Arrange
        data = _make_test_data()

        # Act
        result = my_function(data)

        # Assert
        assert result.status == "ok"

    def test_error_case(self):
        with pytest.raises(ValueError, match="expected error message"):
            my_function(invalid_input)
```

### Test Helpers

- Use factory functions (`_make_*`) for test fixtures
- Use `tmp_path` for filesystem tests
- Use `StubClient` for LLM tests (never call real APIs in tests)
- Use `BenchmarkSet.seed()` for benchmark tests

## Pull Request Process

1. **Create a branch**: `git checkout -b feature/my-feature`
2. **Write tests first**: Design tests before implementing
3. **Implement**: Keep changes minimal and focused
4. **Run checks**: `ruff check`, `mypy`, `pytest`
5. **Commit**: Use conventional commit messages:
   - `feat: add new scoring metric`
   - `fix: handle empty evidence list`
   - `docs: update API reference`
   - `test: add ablation harness tests`
   - `refactor: simplify retrieval ranking`
6. **Push and PR**: Push your branch and open a pull request
7. **Review**: Address feedback from reviewers
8. **Merge**: Once approved and CI passes

### Commit Message Format

```
<type>: <subject>

<body>
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `ci`

## Architecture Decisions

When making significant architecture changes, document the decision in
the PR description with:

- **Context**: Why this change is needed
- **Decision**: What was decided
- **Consequences**: What trade-offs were accepted

See `docs/architecture.md` for the current architecture overview.

## Release Process

1. Update `docs/changelog.md` with the new version
2. Bump version in `pyproject.toml`
3. Tag the release: `git tag v0.X.0`
4. Push tags: `git push --tags`

## Questions?

- Open an issue on [GitHub](https://github.com/TahGue/VSRS-/issues)
- Read the [architecture docs](architecture.md)
- Check the [API reference](api-reference.md)
