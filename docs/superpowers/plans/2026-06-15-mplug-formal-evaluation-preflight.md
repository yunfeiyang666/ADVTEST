# mPLUG Formal Evaluation Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a strict preflight and fail-fast evaluation path, then run an audited 20-call mPLUG-Owl2 smoke for ADVTEST, Random, Official QA, and QATest-adapted.

**Architecture:** `mplug_preflight.py` validates question/provenance/call capacity and resolves every required real mosaic before the model loads. `assemble_mplug_smoke.py` materializes an immutable four-suite input directory with source hashes. `run_suite_evaluation.py` remains the evaluator entry point but forbids MPLUG-to-Mock fallback and records inference evidence.

**Tech Stack:** Python 3.10 standard library, `unittest`, Pillow, existing evaluator and recorded-run utilities, mPLUG-Owl2 in `.venv310`.

---

### Task 1: Strict suite and image preflight

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/mplug_preflight.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_mplug_preflight.py`

- [x] Write failing tests for a valid prefix and rejection of insufficient call
  capacity, missing question/answer/provenance, duplicate normalized questions,
  missing official source IDs, unresolved scene graphs, and unresolved mosaics.
- [x] Run:

```powershell
cd E:\Project\ADVTEST\1号机代码\DATA_new\analysis\rq1_error_detection
python -m unittest test_mplug_preflight.py -v
```

  Expected: import failure because `mplug_preflight.py` does not exist.
- [x] Implement:

```python
@dataclass(frozen=True)
class PreflightConfig:
    call_budget: int
    outputs_root: Path
    dataroot: Path
    mosaic_dir: Path

def audit_suite(path: Path, config: PreflightConfig) -> dict:
    ...

def run_preflight(suites: Sequence[Path], config: PreflightConfig) -> dict:
    ...
```

  The prefix must consume exactly `call_budget`; call
  `validate_provenance()`, `validate_question_boundary()`, and
  `resolve_image_path()`. Collect all failures before returning, but CLI exit
  non-zero if any failure exists.
- [x] Run focused tests and confirm all pass.
- [x] Commit:

```powershell
git add -- 1号机代码/DATA_new/analysis/rq1_error_detection/mplug_preflight.py 1号机代码/DATA_new/analysis/rq1_error_detection/test_mplug_preflight.py
git commit -m "feat(rq1): add strict mPLUG suite preflight"
```

### Task 2: Fail-fast MPLUG evaluation evidence

**Files:**
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/run_suite_evaluation.py`
- Modify: `1号机代码/DATA_new/analysis/rq1_error_detection/test_run_suite_evaluation.py`

- [x] Write failing tests proving:

```python
with self.assertRaisesRegex(FileNotFoundError, "real mosaic"):
    evaluate_question(vlm, question, "MPLUG", None)
```

  and that a real evaluator result writes `prompt`, `mode`,
  `inference_elapsed_seconds`, `raw_model_output`, and `error`.
- [x] Run the focused test and verify the current MPLUG path incorrectly calls
  `MockVLMEvaluator` when `image_path` is `None`.
- [x] Change `evaluate_question()` so only `MOCK` may run without an image.
  MPLUG must raise on missing images and propagate evaluator exceptions.
- [x] Time each uncached evaluation and write the evidence fields to raw JSONL.
  Use the exact question text as `prompt`; use the returned prediction as
  `raw_model_output`; write `error=null` for successful records.
- [x] Run:

```powershell
python -m unittest test_run_suite_evaluation.py test_evaluator_fail_fast.py -v
python -m unittest discover -p "test_*.py" -v
```

- [x] Commit:

```powershell
git add -- 1号机代码/DATA_new/analysis/rq1_error_detection/run_suite_evaluation.py 1号机代码/DATA_new/analysis/rq1_error_detection/test_run_suite_evaluation.py
git commit -m "fix(rq1): forbid mock fallback in mPLUG evaluation"
```

### Task 3: Deterministic four-suite assembly

**Files:**
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/assemble_mplug_smoke.py`
- Create: `1号机代码/DATA_new/analysis/rq1_error_detection/test_assemble_mplug_smoke.py`

- [x] Write failing tests requiring the assembler to:
  copy the first call-budget prefix without modifying records, name outputs
  `advtest_suite.jsonl`, `random_suite.jsonl`, `official_qa_suite.jsonl`, and
  `qatest_adapted_suite.jsonl`, and record source/output SHA-256 hashes.
- [x] Run the focused test and verify module import failure.
- [x] Implement an atomic assembler that refuses to overwrite a non-empty
  output directory and writes `assembly_manifest.json`.
- [x] Run focused and full tests.
- [x] Commit:

```powershell
git add -- 1号机代码/DATA_new/analysis/rq1_error_detection/assemble_mplug_smoke.py 1号机代码/DATA_new/analysis/rq1_error_detection/test_assemble_mplug_smoke.py
git commit -m "feat(rq1): assemble audited mPLUG smoke suites"
```

### Task 4: Assemble and preflight the real smoke inputs

**Files:**
- Create locally: `scratch/rq1_mplug_smoke/suites/`
- Create locally: `scratch/rq1_mplug_smoke/preflight/`
- Create: `experiments/rq1_mplug_smoke/preflight_summary.json`
- Create: `experiments/rq1_mplug_smoke/run_index.json`

- [x] Assemble from these exact inputs:

```text
ADVTEST:
scratch/rq1_formal_exploration/runs/structural-cap50-seed42-retry1/results/advtest_suite.jsonl

Random:
scratch/rq1_formal_exploration/runs/structural-cap50-seed42-retry1/results/random_suite.jsonl

Official QA:
scratch/rq1_formal_exploration/runs/official-capacity1000/results/official_qa_suite.jsonl

QATest-adapted:
scratch/rq1_qatest_adapted/runs/qatest-style-vs-adapted-1000/results/qatest_adapted_suite.jsonl
```

- [x] Run the assembler with `--call-budget 20`.
- [x] Run `mplug_preflight.py` against all four output suites with the real
  outputs root and NuScenes dataroot.
- [x] If preflight fails, stop. Record the failing frames and causes; do not
  launch mPLUG.
- [x] If preflight succeeds, copy the compact preflight report and input hashes
  into `experiments/rq1_mplug_smoke/`.
- [x] Commit the preflight evidence without committing mosaics or suite files:

```powershell
git add -- experiments/rq1_mplug_smoke
git commit -m "exp(rq1): preflight mPLUG smoke inputs"
```

### Task 5: Recorded 20-call real mPLUG smoke

**Files:**
- Create locally: `scratch/rq1_mplug_smoke/runs/mplug-four-methods-call20/`
- Create: `experiments/rq1_mplug_smoke/README.md`
- Modify: `experiments/rq1_mplug_smoke/run_index.json`

- [x] Verify before launch:

```powershell
E:\Project\ADVTEST\.venv310\Scripts\python.exe -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
```

  Expected: `NVIDIA GeForce RTX 3070 Laptop GPU`.
- [x] Run through `run_recorded_experiment.py` using `.venv310`, mode `MPLUG`,
  the assembled suite directory, methods `advtest random official_qa
  qatest_adapted`, and `--vlm-call-budget 20`.
- [x] Stop on model-load failure, missing real image, inference exception, CUDA
  OOM, or any suite reporting fewer/more than 20 actual calls.
- [x] Audit raw JSONL files: every row must have `mode=MPLUG`, a non-empty
  `raw_model_output`, `error=null`, and positive inference duration.
- [x] Record metrics, exact command, commit, hashes, elapsed time, failures, and
  limitations in `experiments/rq1_mplug_smoke/README.md` and `run_index.json`.
- [x] Run full regression, JSON parsing, `git diff --check`, and inspect the
  recorded manifest.
- [x] Commit:

```powershell
git add -- experiments/rq1_mplug_smoke
git commit -m "exp(rq1): record strict mPLUG call20 smoke"
```

### Task 6: Gate the 100-call expansion

**Files:**
- Modify: `experiments/rq1_mplug_smoke/README.md`

- [x] Mark the 100-call run eligible only if all four suites completed 20 real
  calls with no fallback, no missing images, and valid raw evidence.
- [x] If eligible, document the exact 100-call command but do not run it in this
  plan without a separate recorded-run checkpoint.
- [x] Run `git status --short` and confirm only unrelated pre-existing
  untracked artifacts remain.
