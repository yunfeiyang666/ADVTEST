# Fixed-Budget RQ1 Experiment Design

## Goal

Compare ADVTEST, random selection, QATest, and QAAskeR under the same global
question budget instead of assigning a fixed number of frames to each method.

## Experimental Unit

- Global budget: 1,000 questions per method.
- Shared frame pool: the first 30 frames in
  `rq1_100_eval_frames.json`.
- Shared frame order: every method visits frames in exactly that order.
- Shared denominator: the sum of each pool frame's complete L0, L1, and L2
  universe. Frames not reached by a method contribute zero covered elements.
- Coverage starts empty for this comparison. Existing dataset questions are
  not counted as generated coverage.

## Per-Frame Policy

Each method receives an ordered candidate stream for the current frame:

- ADVTEST: existing generation order.
- Random: deterministic shuffle using the experiment seed and frame index.
- QATest: one deterministic `B=100` selection/mutation pass.
- QAAskeR: one deterministic `B=100` recursive-asking pass.

At least 20 questions are consumed before an adaptive switch is allowed. The
runner moves to the next frame when the first applicable condition is met:

1. The frame reaches 100% L2 coverage.
2. Ten consecutive questions add no new L2 gap.
3. After at least 40 questions, the mean L2 gain of the latest 20 questions is
   below 25% of the mean gain of the first 20 questions.
4. The frame consumes 100 questions.
5. The candidate stream is exhausted.

The global run stops after 1,000 questions or after all 30 frames are exhausted.

## Metrics

For budgets 100, 200, ..., 1,000, report:

- Micro L0/L1/L2 coverage: covered elements divided by the shared global
  universe.
- Macro L0/L1/L2 coverage: mean per-frame coverage over all 30 frames.
- Unique L2 gaps per question.
- Number of visited frames.
- Questions consumed per frame.
- Frame switch reason counts.
- Coverage AUC over the 0-1,000 question budget.

The generated 1,000-question suites are saved so the same frozen suites can be
evaluated by mPLUG-Owl2 and MiniCPM without rerunning selection.

## Outputs

The trial writes to
`1号机代码/DATA_new/analysis/fixed_budget_results/`:

- `fixed_budget_summary.json`
- `fixed_budget_curves.csv`
- `<method>_suite.jsonl`
- `fixed_budget_report.md`

## Failure Handling

Missing frame artifacts fail the run with a clear path. Empty candidate streams
produce a `candidate_exhausted` switch. No VLM is loaded during this experiment.

