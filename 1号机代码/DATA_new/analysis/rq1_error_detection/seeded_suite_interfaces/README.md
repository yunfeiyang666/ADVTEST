# RQ1 Seeded Suite Interfaces

This directory is the single entry point for the seeded RQ1 generation chain.
It does not replace the original QATest or QAAskeR code. The wrappers only
connect the frozen seed bank, existing ADVTEST generator, original baseline
adapters, and evaluators into reproducible commands.

## Strict open-QA interface

`strict_suite_interface.py` has four commands:

- `seed-bank`: retain only official NuScenes-QA rows that the seed-filter VLM
  answered correctly.
- `advtest`: generate the ADVTEST structural suite from the frozen frame cache.
- `baselines`: call the original QATest and QAAskeR adapters from the same seed
  bank. QATest keeps its original mutation loop; QAAskeR keeps original
  Q2S -> S2G plus its self-check path.
- `assemble`: copy the three strict suites into one immutable bundle and write
  hashes plus row counts.

For a 6000-question target, pass `--budget 6000`. QAAskeR may need more than
6000 attempts because its original transformer can reject a seed; its attempt
limit is explicit and recorded instead of silently filling with copied rows.

Example:

```powershell
$py = "E:\Project\ADVTEST\.venv310\Scripts\python.exe"
$api = "E:\Project\ADVTEST\1号机代码\DATA_new\analysis\rq1_error_detection\seeded_suite_interfaces\strict_suite_interface.py"

& $py $api baselines `
  --seed-bank E:\...\correct_seed_bank.jsonl `
  --output-dir E:\Project\ADVTEST\scratch\rq1_seeded_6000\strict `
  --budget 6000 --qaasker-max-attempts 36000
```

## Multiple-choice interface

`choice_suite_interface.py convert` derives choice rows from the strict bundle.
It never regenerates questions, images, seed rows, or ground-truth answers.
Every output row preserves `source_question_id`, `source_question`, and a
SHA256-linked source manifest.

For evaluation, use:

- `evaluate-advtest`: direct choice answering for ADVTEST.
- `evaluate-baselines`: free-form answer first, then option mapping for
  QATest/QAAskeR. This preserves their original question-generation protocol
  and avoids treating the option list as an extra mutation input.

The two forms must be reported separately. A choice result is not a replacement
for a strict open-QA result.

## Files delegated to

- `build_seed_bank_from_eval.py`
- `fixed_budget_experiment.py`
- `build_seeded_baseline_suites.py`
- `build_choice_suites.py`
- `run_suite_evaluation.py`
- `run_two_step_choice_evaluation.py`

The interface intentionally records commands and hashes but does not launch a
VLM by itself unless an explicit evaluation command is used.
