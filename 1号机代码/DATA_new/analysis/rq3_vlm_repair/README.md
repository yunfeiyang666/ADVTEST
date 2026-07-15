# RQ3 VLM Repair

This module builds scene-disjoint fine-tuning data and evaluates whether
ADVTEST-generated questions repair mPLUG-Owl2 more effectively than equal-size
Random and official NuScenes-QA data.

The complete command-by-command workflow, server pilot order, checkpoint
selection rule, statistical reporting commands, and unfilled human-review
workflow are documented in [RUNBOOK.md](RUNBOOK.md).

Formal test scenes are frozen in `config.py`. They must never appear in train
or validation manifests.

## Freeze the split

```powershell
E:\Project\ADVTEST\.venv310\Scripts\python.exe prepare_data.py split
```

## Prepare paired training data

Install the lightweight data dependencies once:

```powershell
E:\Project\ADVTEST\.venv310\Scripts\python.exe -m pip install -r requirements.txt
```

Build the three 10,000-question source datasets. ADVTEST and Random share the
same frames, per-frame question counts, family quotas, candidate space, and
labeled image protocol.

```powershell
E:\Project\ADVTEST\.venv310\Scripts\python.exe prepare_data.py build --kind main
```

Render each frame once and export aligned open/choice SFT records:

```powershell
E:\Project\ADVTEST\.venv310\Scripts\python.exe prepare_data.py export `
  --source advtest_10k=E:\Project\ADVTEST\scratch\rq3_vlm_repair\data\source_datasets\sources\advtest_10k_source.jsonl `
  --source random_10k=E:\Project\ADVTEST\scratch\rq3_vlm_repair\data\source_datasets\sources\random_10k_source.jsonl `
  --source official_qa_10k=E:\Project\ADVTEST\scratch\rq3_vlm_repair\data\source_datasets\sources\official_qa_10k_source.jsonl
```

`build --kind validation` creates the fixed 600-structural plus 400-official
validation set. `validate` checks the JSON schema, exact quotas, unique IDs, image decoding and
SHA256 values, open/choice alignment, and frozen-scene leakage. Use
`build --kind hard-candidates`, evaluate its choice questions with the frozen
base model, then pass the real raw predictions to `screen-hard` to create the
hard subset. The hard selector never uses model predictions as training GT.

For a fast end-to-end data check, add `--smoke --frame-pool-size 30` to
`build`, then validate with `--expected-count 12 --structural --smoke`.

Generated datasets, images, logs, and checkpoints belong under
`E:\Project\ADVTEST\scratch\rq3_vlm_repair` and must not be committed.
