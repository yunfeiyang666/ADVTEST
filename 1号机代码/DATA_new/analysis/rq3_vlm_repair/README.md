# RQ3 VLM Repair

This module builds scene-disjoint fine-tuning data and evaluates whether
ADVTEST-generated questions repair mPLUG-Owl2 more effectively than equal-size
Random and official NuScenes-QA data.

Formal test scenes are frozen in `config.py`. They must never appear in train
or validation manifests.

## Freeze the split

```powershell
E:\Project\ADVTEST\.venv310\Scripts\python.exe prepare_data.py split
```

Generated datasets, images, logs, and checkpoints belong under
`E:\Project\ADVTEST\scratch\rq3_vlm_repair` and must not be committed.

