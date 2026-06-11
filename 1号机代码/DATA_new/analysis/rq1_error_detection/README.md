# RQ1 Error Detection & VLM SFT Dataset Export Pipeline (Phases 2 & 3)

This directory contains the complete pipeline, baselines, plotting scripts, and dataset exporters for **Phase 2 (RQ1: Error Detection Baselines)** and **Phase 3 (VLM Fine-tuning Dataset Exporter)**.

---

## Directory Overview

```
1号机代码/DATA_new/analysis/rq1_error_detection/
├── frame_sampler.py         # Frame sampling utility (selects 100 representative frames)
├── selectors_qatest.py      # Metamorphic fuzzing typos generator (QATest baseline)
├── selectors_qaasker.py     # Yes/No recursive metamorphic follow-up fuzzer (QAAskeR baseline)
├── selectors.py             # Adapter registering baseline selectors to the main framework
├── evaluator.py             # VLM evaluator interface (Mock, API, Qwen2-VL, and mPLUG-Owl2)
├── run_experiment.py        # Experiment orchestrator runner across all methods
├── plot_results.py          # Results aggregator and plotter
├── export_sft_dataset.py    # LLaVA SFT json dataset compiler and 2x3 labeled grid mosaic renderer
└── deploy_sft_pipeline.sh   # [NEW] Server deployment and execution automation script
```

---

## Phase 2: Running Error Detection Experiment & Plotting

To run the full simulation/evaluator baselines (QATest, QAAskeR, Ours, Random) and generate plots:

1. **Activate local virtual environment**:
   ```bash
   .venv310\Scripts\activate
   ```

2. **Execute the experiment runner**:
   ```bash
   python 1号机代码/DATA_new/analysis/rq1_error_detection/run_experiment.py
   ```
   *(Results will compileDet to `data_cache/rq1_results.json`)*

3. **Plot the failures detected and object involvement**:
   ```bash
   python 1号机代码/DATA_new/analysis/rq1_error_detection/plot_results.py
   ```
   *(Plots will save to `figures/rq1_failures_detected.png` and `figures/rq1_object_involvement.png`)*

---

## Phase 3: Compiling LLaVA SFT Dataset

The exporter (`export_sft_dataset.py`) parses offline scene graphs, compiles VQA pairs, and pre-renders stitched 2x3 labeled grids into standard LLaVA visual instruction tuning JSON format.

### Local Verification (on NuScenes-mini)
Since the local host machine might only have `v1.0-mini` / `v1.0-test` splits, the script will gracefully compile the JSON and save camera mosaics only for frames present locally:
```bash
python 1号机代码/DATA_new/analysis/rq1_error_detection/export_sft_dataset.py \
       --mini_only \
       --limit 10 \
       --out_dir 1号机代码/DATA_new/sft_dataset_test
```

### Server Execution (on Full NuScenes-trainval)
On the GPU server containing the full trainval images and metadata, the exporter will physically stitch all camera feeds and label all targets:
```bash
python 1号机代码/DATA_new/analysis/rq1_error_detection/export_sft_dataset.py \
       --out_dir 1号机代码/DATA_new/sft_dataset
```

---

## GPU Server Deployment Guide

To deploy the entire codebase to the remote server and run VLM inference / SFT export:

1. **Edit the server configuration** at the top of `deploy_sft_pipeline.sh`:
   ```bash
   SERVER_IP="your_server_ip"
   SERVER_USER="your_username"
   SERVER_ROOT="/home/yunyang/ADVTEST"
   ```

2. **Run deployment script**:
   ```bash
   bash 1号机代码/DATA_new/analysis/rq1_error_detection/deploy_sft_pipeline.sh
   ```
   This will:
   - Sync all local files, ignores, code modifications, and scripts to the server.
   - Activate the remote environment automatically.
   - Run the full VLM SFT dataset exporter on all trainval scene graphs.

### VLM Evaluator Setup (mPLUG-Owl2)
On the server, `evaluator.py` automatically injects the mPLUG-Owl2 codebase into its import path. Ensure you have mPLUG repository checked out under `baselines/mPLUG-Owl` and the weights placed under `models/mplug-owl2-llama2-7b`. The evaluator will automatically switch from Mock mode to GPU inference.
