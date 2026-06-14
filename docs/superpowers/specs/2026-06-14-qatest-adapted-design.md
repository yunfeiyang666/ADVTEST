# QATest-Adapted Design

## Goal

Implement a reproducible QATest adaptation for NuScenes-QA that preserves the
original method's iterative linguistic-coverage search while remaining offline,
credential-free, and compatible with the RQ1 experiment protocol.

## Naming

- `qatest_style`: the existing deterministic seven-operator cycle. It remains
  available as a simplified ablation.
- `qatest_adapted`: the new iterative QATest adaptation and the primary external
  baseline.

Neither method may read ADVTEST questions, candidate order, scene-graph gaps, or
L0/L1/L2 coverage state.

## Inputs and Outputs

Input records come only from official NuScenes-QA questions matched to the
shared frame order. Each seed includes:

- official question ID;
- sample token and scene frame;
- original question and answer;
- official template type and hop count;
- source-root identity;
- iteration count and generation count.

Output records preserve the official answer and source identity. They add:

- `mutation_operator`;
- `original_question`;
- `qatest_iteration`;
- `qatest_parent_question`;
- `qatest_rouge1_f1`;
- `qatest_gram_gain`;
- `qatest_sentence_probability`;
- standard cross-paradigm provenance.

The generation adapter is `qatest_adapted_portable`. The provenance field
`uses_coverage_feedback` remains false because it denotes ADVTEST scene-graph
coverage feedback. QATest's own linguistic feedback is represented by the
explicit `qatest_*` fields.

## Portable Operators

The adaptation provides seven deterministic offline operators:

1. keyboard substitution;
2. OCR-like substitution;
3. spelling deletion;
4. synonym replacement from a small versioned local map;
5. adverbial-clause movement;
6. Wh-contraction;
7. double question mark.

Contextual BERT insertion, WMT back translation, and TagMe entity replacement
are disabled because the original implementation uses non-portable model paths
or an online credential.

Operator order is deterministically shuffled from the global seed, iteration,
source ID, and retry index. No process-randomized Python `hash()` values are
used.

## Quality and Duplicate Filtering

Each selected seed receives at most ten mutation attempts per iteration.

A candidate is accepted only when:

- it differs from its parent question;
- its normalized text has not already been emitted;
- it is not an exact duplicate of any question sharing the same source root;
- Rouge-1 F1 against the parent question is strictly greater than `0.5`.

Rouge-1 is implemented locally as token-unigram precision, recall, and F1. This
avoids adding the old `rouge` package solely for one metric.

## Linguistic Feedback

Tokenization uses a deterministic regex tokenizer. POS tags use a portable
coarse heuristic tagger rather than downloading NLTK resources.

The coverage model tracks:

- transitions among coarse POS states, including `START` and `END`;
- unique token n-grams of length one through four.

For every accepted candidate:

- sentence probability is the product of observed transition probabilities,
  with unseen transitions assigned probability zero;
- grammar gain is the number of previously unseen n-grams divided by the
  current covered n-gram count, with an empty model using the candidate n-gram
  count directly.

At the end of an iteration, at most two accepted candidates are returned to the
seed pool:

- the candidate with minimum sentence probability;
- the candidate with maximum grammar gain.

If both criteria select the same candidate, it is inserted once.

## Seed Selection

The generator tracks how many active descendants belong to each official source
root. Batch selection weights each seed by the inverse of that root count,
matching the original QATest intent.

For deterministic reproducibility, weighted sampling without replacement is
implemented with a local `random.Random` instance. The default batch size is
five.

## Budgets and Termination

`generation_budget` counts accepted output questions only.

The generator stops when:

- it emits `generation_budget` records;
- no candidate is accepted for a complete pass over the active seed pool; or
- the configured iteration limit is reached.

It reports:

- accepted question count;
- attempted candidate count;
- rejected-by-quality count;
- rejected-duplicate count;
- operator attempt and acceptance counts;
- iteration count and elapsed time.

Generation consumes no VLM calls. Each emitted question costs one VLM call only
when evaluated.

## Integration

Add `qatest_adapted.py` as an isolated module. Extend
`official_qa_experiment.py` with method names `qatest_style` and
`qatest_adapted`.

For one compatibility cycle, the old CLI name `qatest` aliases
`qatest_style`, but generated provenance must use `qatest_style`. Documentation
and new experiments use explicit names only.

The adapted generator receives already indexed official records and frame
mapping. It does not load scene graphs or ADVTEST outputs.

## Testing

Tests must prove:

- deterministic output for the same seed;
- a candidate below the Rouge threshold is rejected;
- duplicate normalized text is rejected;
- high grammar-gain and low-probability candidates return to the seed pool;
- the generation budget is never exceeded;
- only official source IDs and sample tokens appear;
- external-boundary validation rejects ADVTEST-private fields;
- disabled operators require no model, network, or credentials;
- the old `qatest` alias emits `qatest_style` provenance.

## Formal Experiment

After implementation:

1. run a small deterministic smoke test;
2. generate 1000 `qatest_adapted` questions from the fixed 100-frame cache;
3. record the run through `run_recorded_experiment.py`;
4. compare generation time, attempts, operator distribution, source diversity,
   and duplicate rate against `qatest_style`;
5. do not start real-VLM evaluation until the generated suite audit passes.
