# Usage Scenario: Fixing a Bug with VSRS

This scenario walks through using VSRS to fix a simple bug end-to-end.

## Setup

```bash
# Install VSRS
pip install -e ".[dev]"

# Verify installation
pytest tests/ -q
```

## Step 1: Create a Task Definition

Create a task JSON file (see `tasks/empty-password.json`):

```json
{
  "instruction": "Fix the login bug where an empty password is accepted",
  "type": "bugfix",
  "risk": "low",
  "acceptance_criteria": [
    "validate_password('') returns False",
    "validate_password(None) returns False",
    "validate_password('valid') returns True"
  ]
}
```

## Step 2: Run VSRS

```bash
# Run with the stub provider (no API key needed)
vsrs run \
  --repo ./my-project \
  --task docs/examples/tasks/empty-password.json \
  --config docs/examples/configs/local.yaml
```

**Expected output**:
```
Run ID: run_abc123
Task: Fix the login bug where an empty password is accepted
State: intake → retrieving → reasoning → patching → verifying → verified
Attempts: 1
Final Status: verified_candidate
```

## Step 3: Check the Status

```bash
vsrs status --run-id run_abc123
```

**Expected output**:
```
Run: run_abc123
State: verified
Attempt: 1/3
Started: 2024-01-01T10:00:00Z
```

## Step 4: View the Evidence

```bash
vsrs evidence --run-id run_abc123
```

**Expected output**:
```
Evidence for run_abc123:
  [1] (symbol) src/auth.py:10
      def validate_password(pw: str) -> bool:
          return bool(pw)
  [2] (test) tests/test_auth.py:5
      def test_valid_password():
          assert validate_password("secret") is True
```

## Step 5: View the Diff

```bash
vsrs diff --run-id run_abc123
```

**Expected output**:
```diff
--- a/src/auth.py
+++ b/src/auth.py
@@ -1,2 +1,4 @@
 def validate_password(pw: str) -> bool:
-    return bool(pw)
+    if not pw:
+        return False
+    return bool(pw)
```

## Step 6: View the Verification Report

```bash
vsrs verify --run-id run_abc123
```

**Expected output**:
```
Verification Report for run_abc123:
  [pass] syntax       python -c 'import ast; ast.parse(open("src/auth.py").read())'
  [pass] build        python -m py_compile src/auth.py
  [pass] existing_tests  pytest tests/test_auth.py -v
  [pass] new_targeted_tests  pytest tests/test_empty_password.py -v

Required gates: ALL PASSED
Blockers: none
```

## Step 7: View the Audit Trail

```bash
vsrs audit-trail --run-id run_abc123
```

**Expected output**:
```
Audit Trail for run_abc123:
  run_abc123 --executes--> task_xyz789
  run_abc123 --retrieves--> ev_001 (src/auth.py:10)
  run_abc123 --retrieves--> ev_002 (tests/test_auth.py:5)
  run_abc123 --produces--> hyp_001 (validate_password does not check empty)
  run_abc123 --generates--> patch_001 (attempt 1)
  run_abc123 --verifies--> report_001 (all gates passed)
  run_abc123 --reviews--> finding_001 (minor: no None test)
  run_abc123 --decides--> verified_candidate
```

## Step 8: Generate a Report

```bash
vsrs report --run-id run_abc123 --output report.md
```

## Step 9: Export as Training Data

```bash
vsrs run --run-id run_abc123 --export trajectory.jsonl
```

## Using with LLM

To use a real LLM instead of the stub:

```bash
# Set API key
export OPENAI_API_KEY=sk-...

# Run with OpenAI
vsrs run \
  --repo ./my-project \
  --task docs/examples/tasks/empty-password.json \
  --config docs/examples/configs/openai.yaml
```

The LLM will generate the actual patch diff, hypothesis, and falsification
plan. If the LLM output fails to parse, VSRS falls back to the deterministic
reasoner.
