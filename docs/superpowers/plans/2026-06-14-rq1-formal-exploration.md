# RQ1 Formal Exploration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Git-tracked experiment ledger, execute the 100-frame structural sensitivity matrix, and produce a reproducible evidence summary without starting long real-VLM runs.

**Architecture:** A generic subprocess runner owns immutable run directories and sanitized manifests. A separate structural-matrix orchestrator invokes existing generation scripts through that runner, then reads their JSON summaries into a compact tracked analysis artifact. Raw suites and logs stay under ignored experiment output directories.

**Tech Stack:** Python 3 standard library, `unittest`, existing RQ1 generation scripts, Git.

---

### Task 1: Add the experiment manifest model

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/experiment_tracking.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_experiment_tracking.py`

- [x] **Step 1: Write failing manifest tests**

Add tests that require:

```python
manifest = build_manifest(
    run_id="structural-cap50-seed42",
    purpose="Measure structural coverage",
    command=["python", "fixed_budget_experiment.py"],
    workspace_root=Path("E:/Project/ADVTEST"),
    input_files=[frame_cache],
    parameters={"generation_budget": 1000, "max_questions": 50},
)
```

Assertions:

```python
self.assertEqual(manifest["schema_version"], 1)
self.assertEqual(manifest["status"], "prepared")
self.assertEqual(manifest["parameters"]["generation_budget"], 1000)
self.assertEqual(len(manifest["inputs"][0]["sha256"]), 64)
self.assertNotIn("environment", manifest)
```

- [x] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest test_experiment_tracking.py -v
```

Expected: import failure because `experiment_tracking.py` does not exist.

- [x] **Step 3: Implement the minimal manifest functions**

Implement:

```python
def sha256_file(path: Path) -> str: ...
def current_git_state(workspace_root: Path) -> dict: ...
def build_manifest(
    *,
    run_id: str,
    purpose: str,
    command: Sequence[str],
    workspace_root: Path,
    input_files: Sequence[Path],
    parameters: Mapping[str, object],
) -> dict: ...
```

The Git state contains branch, commit, and dirty status only. Do not record
environment variables.

- [x] **Step 4: Run tests and verify GREEN**

Run the focused test command and expect all tests to pass.

- [x] **Step 5: Commit the manifest model**

Commit:

```text
feat(rq1): add reproducible experiment manifests
```

### Task 2: Add the recorded subprocess runner

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/experiment_tracking.py`
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/test_experiment_tracking.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/run_recorded_experiment.py`

- [x] **Step 1: Write failing runner tests**

Use temporary directories and `sys.executable -c` commands to verify:

```python
result = run_recorded_experiment(
    run_dir=run_dir,
    manifest=manifest,
    command=[sys.executable, "-c", "print('ok')"],
    cwd=workspace,
)
```

Require `manifest.json`, `stdout.log`, and `stderr.log`; require status
`completed`, exit code `0`, and non-negative duration. Add a failing-command
test requiring status `failed` and preserved stderr.

- [x] **Step 2: Run tests and verify RED**

Expected: failure because `run_recorded_experiment` is missing.

- [x] **Step 3: Implement subprocess recording and CLI**

The runner writes the prepared manifest before launch, redirects stdout and
stderr, and updates the manifest in a `finally` block. Existing run directories
raise `FileExistsError` unless `overwrite=True`.

CLI:

```powershell
python run_recorded_experiment.py `
  --run-id structural-cap50-seed42 `
  --purpose "100-frame structural sensitivity" `
  --run-root scratch/rq1_formal_exploration/runs `
  --input-file 1号机代码/DATA_new/analysis/data_cache/rq1_100_eval_frames.json `
  --parameter generation_budget=1000 `
  --parameter max_questions=50 `
  -- python fixed_budget_experiment.py ...
```

- [x] **Step 4: Run focused and complete RQ1 tests**

Expected: all tests pass.

- [x] **Step 5: Commit the recorded runner**

Commit:

```text
feat(rq1): record experiment commands and outcomes
```

### Task 3: Add structural sensitivity aggregation

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/structural_sensitivity.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_structural_sensitivity.py`

- [x] **Step 1: Write failing aggregation tests**

Create small in-memory fixed-budget summaries for cap 50 and cap 100. Require:

```python
rows = build_sensitivity_rows(runs)
random_stats = summarize_random(rows)
decision = recommend_frame_cap(rows)
```

Tests require mean, population standard deviation, min, and max for Random;
deterministic methods retain one row per cap; and ADVTEST chooses cap 50 when
both Micro-L2 and AUC improvements are below `0.005`.

- [x] **Step 2: Run tests and verify RED**

Expected: import failure because the module does not exist.

- [x] **Step 3: Implement aggregation and report writing**

Implement JSON/CSV/Markdown outputs containing:

- per-run metrics;
- Random aggregate statistics by cap;
- cap recommendation and measured deltas;
- Official QA and QATest actual capacity.

- [x] **Step 4: Run focused tests and verify GREEN**

Expected: all aggregation tests pass.

- [x] **Step 5: Commit aggregation**

Commit:

```text
feat(rq1): aggregate structural sensitivity evidence
```

### Task 4: Execute the 100-frame matrix

**Files:**
- Create: `experiments/rq1_formal_exploration/README.md`
- Create: `experiments/rq1_formal_exploration/run_index.json`

- [ ] **Step 1: Record the exact matrix**

Structural runs:

```text
cap50-seed42
cap50-seed43
cap50-seed44
cap100-seed42
cap100-seed43
cap100-seed44
```

Each structural run uses 100 frames, generation budget 1000, and candidate
load limit 200. Deterministic methods are retained only from seed 42 during
aggregation; all three Random rows are retained.

External capacity run:

```text
official-capacity1000
```

It builds `official_qa` and `qatest` on the same 100-frame order.

- [ ] **Step 2: Run all commands through the recorded runner**

Every run must finish with manifest status `completed`.

- [ ] **Step 3: Generate the sensitivity summary**

Run `structural_sensitivity.py` over the run directories and write compact
artifacts to `experiments/rq1_formal_exploration/`.

- [ ] **Step 4: Verify results**

Check:

- every structural method reaches suite size 1000;
- Random has three seeds per cap;
- Official QA actual capacity is reported without repetition;
- frame-cache hashes are identical across runs;
- no run manifest records secrets.

- [ ] **Step 5: Commit evidence and operation notes**

Commit:

```text
exp(rq1): record 100-frame structural sensitivity
```

### Task 5: Final regression and handoff

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/README.md`
- Modify: `experiments/rq1_formal_exploration/README.md`

- [ ] **Step 1: Document reproduction commands**

Include exact commands, expected run IDs, output locations, and interpretation
rules.

- [ ] **Step 2: Run verification**

Run:

```powershell
python -m unittest discover -p "test_*.py" -v
python -m py_compile experiment_tracking.py run_recorded_experiment.py structural_sensitivity.py
git diff --check
```

- [ ] **Step 3: Review Git scope**

Confirm only code, tests, plans, tracked summaries, and operation notes are
staged.

- [ ] **Step 4: Commit the handoff**

Commit:

```text
docs(rq1): document formal exploration workflow
```
