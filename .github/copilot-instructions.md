# ADVTEST Workspace Instructions

**Project**: Adaptive VLM Testing Framework for Autonomous Driving  
**Language**: Python  
**Primary Dataset**: NuScenes  
**Key Technologies**: Scene Graphs, Neo4j, Coverage-Driven Testing, Vision Language Models

---

## 📋 Project Overview

ADVTEST is an **automated testing framework** that:

1. **Generates adaptive test questions** for autonomous driving scenes using coverage-driven approaches
2. **Evaluates Vision Language Models (VLMs)** (GPT-4V, LLaVA, MiniCPM, Claude) on scene understanding
3. **Uses scene graphs** (S3C abstraction) to represent spatial-semantic relationships
4. **Tracks test coverage** using hierarchical metrics (L0: objects, L1: relationships, L2: spatial properties)
5. **Generates reports** analyzing VLM performance on long-tail scenarios

### Core Research Questions

- **RQ1**: How well do modern VLMs understand autonomous driving scenes?
- **RQ2**: Which scene types/relationships do VLMs struggle with (long-tail problem)?
- **RQ3**: Can coverage-driven question generation improve test diversity and fault-finding?

---

## 🗂️ Key Directory Structure

### Main Pipelines

| Path | Purpose | Key Files |
|------|---------|-----------|
| `nuscenes_s3c_experiment/` | Scene graph generation & S3C analysis | `step1_data_loading.py`, `step2_scene_graph_generation.py` |
| `nuscenes_s3c_experiment/core_pipeline/` | VQA pipeline & question generation | `config.py`, `run_official_qa_enhanced.py` |
| `nuscenes_s3c_experiment/core_pipeline/qa_generator_v2/` | LLM-driven QA generation | `llm_qa_generator.py`, `integrated_pipeline.py` |
| `nuscenes_s3c_experiment/core_pipeline/coverage_loop/` | Coverage-driven test generation | `loop_controller.py`, `unified_coverage.py` |
| `nuscenes_s3c_experiment/core_pipeline/vqa_pipeline/` | VLM evaluation pipeline | `pipeline.py`, `direction_utils.py`, `neo4j_client.py` |
| `code/` | Analysis & evaluation scripts | `eval_minicpm_*.py`, `analyze_baseline_comparison.py` |
| `data/` | Scene graphs & QA datasets | `*.jsonl` scene graphs, `qa_mini_v2.jsonl` |
| `docs/` | Architecture & design docs | `Demo_Frame_Analysis_and_VLM_Survey.md`, scene graph analysis |

---

## 🚀 Quick Start

### 1. Environment Setup

```bash
# Create virtual environment
cd e:\Project\ADVTEST
python -m venv .venv310
.venv310\Scripts\activate

# Install dependencies
pip install -r nuscenes_s3c_experiment/requirements.txt

# For Neo4j support, also install:
pip install neo4j py2neo
```

### 2. Essential Commands

#### Generate Scene Graphs
```bash
cd nuscenes_s3c_experiment
python step2_scene_graph_generation.py \
  --sample-num 1 \
  --output-dir output/scene_graphs
```

#### Run VQA Pipeline (Single Question)
```bash
cd nuscenes_s3c_experiment/core_pipeline
python -m vqa_pipeline.pipeline \
  --scene-graph output/scene_graphs/scene-0103_frame25_scene_graph.json \
  --question "What is in front of the ego vehicle?" \
  --vqa-model minicpm
```

#### Coverage-Driven Test Generation (Iterative)
```bash
python -m coverage_loop.run_loop \
  --scene-graph output/scene_graphs/scene-0103_frame25_scene_graph.json \
  --target-l0 0.8 \
  --max-iterations 5
```

#### Run Full VLM Evaluation
```bash
python run_official_qa_enhanced.py \
  --vlm-model gpt-4-vision \
  --scene-ids 0103,0104,0105 \
  --sample-size 50
```

---

## 🔑 Key Concepts

### Scene Graphs (S3C Format)

Scene graphs represent autonomous driving scenes as **nodes (objects) + edges (relationships)**:

```json
{
  "nodes": [
    {
      "id": "ego",
      "category": "vehicle.ego",
      "pose": {"ego": [0, 0, 0]},
      "bins": {"distance": "far", "angular": "front"}
    },
    {
      "id": "pedestrian_001",
      "category": "human.pedestrian",
      "pose": {"ego": [60.5, -18.3, 1.1]}
    }
  ],
  "edges": [
    {
      "from": "ego",
      "to": "pedestrian_001",
      "relation_type": "longitudinal",
      "distance": 60.5,
      "bearing_ego": -0.514
    }
  ]
}
```

**Key Properties**:
- **Ego-centric frame**: All positions relative to autonomous vehicle
- **S3C binning**: Objects categorized by distance, direction, angular bins
- **Relations**: Longitudinal (front/back), lateral (left/right), spatial properties

### Coverage Metrics

- **L0**: Object coverage (what objects are tested)
- **L1**: Relationship coverage (what spatial relationships are tested)
- **L2**: Direction/property coverage (specific spatial configurations)

### Neo4j Database Schema

Objects and relationships are queried via Neo4j:
```
(Vehicle)-[FRONT_OF]->(Pedestrian)
(Ego)-[ADJACENT_LANE]->(Vehicle)
(Ego)-[LEFT_OF]->(Bike)
```

---

## 🛠️ Common Development Tasks

### Adding a New VLM Evaluator

1. Create evaluator in `vqa_pipeline/vlm_models/`:
   ```python
   # Example: E:/Project/ADVTEST/vqa_pipeline/vlm_models/gemini_model.py
   from .base_model import BaseVLMModel
   
   class GeminiModel(BaseVLMModel):
       def __init__(self, api_key):
           self.api_key = api_key
       
       def answer_question(self, image_path, question):
           # Call Gemini API
           pass
   ```

2. Register in `vqa_pipeline/config.py`:
   ```python
   VLM_MODELS = {
       "gemini": GeminiModel,
       # ... existing models
   }
   ```

3. Test with:
   ```python
   from vqa_pipeline.pipeline import VQAPipeline
   pipeline = VQAPipeline(vlm_model="gemini")
   ```

### Analyzing Test Results

```python
# See: code/analyze_baseline_comparison.py
from code.analyze_baseline_comparison import compare_models

# Compare VLM performance
results = compare_models(
    model_results=["results_gpt4v.json", "results_minicpm.json"],
    metrics=["accuracy", "long_tail_accuracy", "coverage"]
)
```

### Debugging Coverage Gaps

```bash
# Diagnose coverage for a scene
python nuscenes_s3c_experiment/core_pipeline/check_directions.py \
  --scene-graph output/scene_graphs/scene-0103_frame25_scene_graph.json

# Analyze high-level metrics
python diag_l2.py
```

---

## 🔧 Configuration Files

### Core Configs

| File | Purpose |
|------|---------|
| `nuscenes_s3c_experiment/config.py` | Data paths, scene selection |
| `nuscenes_s3c_experiment/core_pipeline/config.py` | DB, API keys, pipeline settings |
| `nuscenes_s3c_experiment/core_pipeline/vqa_pipeline/config.py` | VQA model configs, prompt templates |
| `nuscenes_s3c_experiment/core_pipeline/qa_generator_v2/config.py` | LLM API settings, generation templates |

### Environment Variables

```bash
# Set API keys
export OPENAI_API_KEY="sk-..."
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="..."

# Optional: Data paths (will auto-resolve if not set)
export NUSCENES_ROOT="/path/to/nuscenes"
export NUSCENES_VERSION="v1.0-mini"
```

---

## 📊 Data Formats

### Scene Graph Files (JSON Lines)

- **Location**: `data/nuscenes_scene_graph_*.jsonl`
- **Size**: ~50 scenes × 40 frames = 2,000+ scene graphs
- **Format**: One complete scene graph JSON per line

### QA Dataset

- **Original**: `data/qa_mini_v2.jsonl` (NuScenes-QA subset)
- **Generated**: `generated_qa/*.json` (coverage-driven generation)
- **Format**:
  ```json
  {
    "scene_id": "0103",
    "frame": 25,
    "question": "What color is the car in front of the ego vehicle?",
    "answer": "white",
    "coverage": {"L0": ["car"], "L1": ["FRONT_OF"], "L2": ["front", "close"]}
  }
  ```

### Results Files

- **Evaluation results**: `output/eval_results_*.json`
- **Coverage analysis**: `output/coverage_analysis_*.json`
- **Performance reports**: `output/reports/*.md`

---

## ⚠️ Common Pitfalls & Solutions

### Issue: Neo4j Connection Failures

```
ERROR: Could not connect to Database Core server driver
```

**Solution**:
```bash
# Ensure Neo4j is running
# Option 1: Start Neo4j service
net start Neo4j

# Option 2: Check connection parameters
python -c "from vqa_pipeline.neo4j_client import Neo4jClient; print('Neo4j OK')"

# Option 3: Clear old imports
python nuscenes_s3c_experiment/core_pipeline/import_single_scene_to_neo4j.py --reset
```

### Issue: "Scene Graph Not Found" Errors

```
ValueError: Scene graph file not found
```

**Solution**:
1. Verify scene IDs are correct (format: `scene-XXXX`)
2. Generate missing graphs: `python step2_scene_graph_generation.py`
3. Check output directory permissions

### Issue: LLM API Rate Limits

```
APIError: Rate limit exceeded
```

**Solution**:
1. Implement retry logic (built-in to `llm_client.py`)
2. Use batch processing with delays
3. Fall back to Claude or local Ollama model
4. See `nuscenes_s3c_experiment/core_pipeline/qa_generator_v2/llm_client.py`

### Issue: Direction Calculations Seem Wrong

**Note**: All directions are in **Ego Frame** (relative to autonomous vehicle heading):
- Direction: `relative_angle = global_angle - ego_heading`
- This matches driver's intuition (forward/backward relative to car)
- See: `vqa_pipeline/direction_utils.py` for details
- See: [DIRECTION_SYSTEM_UPDATE.md](nuscenes_s3c_experiment/core_pipeline/DIRECTION_SYSTEM_UPDATE.md)

---

## 📚 Documentation Index

### Architecture & Design
- **Scene Graph Generation**: [scene_graph_pipeline_guide.md](docs/scene_graph_pipeline_guide.md)
- **S3C Technical Architecture**: [PPT_S3C技术架构_标准答案.md](docs/PPT_S3C技术架构_标准答案.md)
- **Long-Tail Analysis**: [场景图长尾问题分析.md](docs/场景图长尾问题分析.md)

### VQA Pipeline
- **QA Model Analysis**: [NuScenes_QA_Models_Analysis.md](docs/NuScenes_QA_Models_Analysis.md)
- **VQA Query Processing**: [NuScenes_QA_Answer_Processing_Detailed.py](docs/NuScenes_QA_Answer_Processing_Detailed.py)

### VLM Evaluation
- **VLM Survey**: [Demo_Frame_Analysis_and_VLM_Survey.md](docs/Demo_Frame_Analysis_and_VLM_Survey.md)
- **MiniCPM Results**: [MiniCPM_Evaluation_Complete_Report.md](docs/MiniCPM_Evaluation_Complete_Report.md)

---

## 🎯 Development Workflow

### For Bug Fixes
1. Identify failing test: `python run_official_qa_enhanced.py --debug`
2. Locate issue in pipeline stages (scene graph → query → answer)
3. Fix and test: `pytest nuscenes_s3c_experiment/core_pipeline/tests/`
4. Verify coverage impact

### For New Features
1. Check [nuscenes_s3c_experiment/core_pipeline/DESIGN_v3.md](nuscenes_s3c_experiment/core_pipeline/qa_generator_v2/DESIGN_v3.md)
2. Add to appropriate pipeline module
3. Update coverage metrics if applicable
4. Test end-to-end with sample scene
5. Document in architecture docs

### For Performance Analysis
- Run: `python code/analyze_baseline_comparison.py`
- Results output to `output/analysis/`
- Generate visualizations for RQ2 (long-tail issues)

---

## 🔗 External Resources

- **NuScenes Official**: https://www.nuscenes.org/
- **S3C Paper & Code**: [文献/s3c-main](文献/s3c-main/) (included in workspace)
- **Neo4j Documentation**: https://neo4j.com/docs/
- **OpenAI API**: https://platform.openai.com/docs/api-reference
- **Anthropic Claude API**: https://docs.anthropic.com/

---

## ✅ Verification Checklist

After setting up, verify:

```bash
# 1. Python environment
python --version  # Should be 3.8+

# 2. Key imports
python -c "import nuscenes; import neo4j; import openai; print('Dependencies OK')"

# 3. Scene graph generation
python nuscenes_s3c_experiment/step2_scene_graph_generation.py --sample-num 1

# 4. Neo4j connection (if using)
python -c "from vqa_pipeline.neo4j_client import Neo4jClient; print('Neo4j OK')" 

# 5. VLM API keys configured
python -c "import os; print('API keys:', 'OPENAI' in os.environ, 'ANTHROPIC' in os.environ)"
```

---

## 📝 Notes for AI Agents

### When Implementing Features

1. **Scene Graph Compatibility**: No changes to scene graph JSON format—too many downstream dependencies
2. **Coverage Metrics**: L0/L1/L2 are fixed definitions, validate all changes against [calculate_coverage_precise.py](nuscenes_s3c_experiment/core_pipeline/calculate_coverage_precise.py)
3. **Neo4j Queries**: Always escape object IDs with backticks: `MATCH (n:\`vehicle.car\`) ...`
4. **Direction Calculations**: Always use Ego Frame (relative to vehicle heading), not global angles
5. **API Rate Limits**: Implement retry logic with exponential backoff for LLM calls

### When Debugging

1. **Enable detailed logging**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

2. **Common breakpoints**:
   - Scene graph loading: `step2_scene_graph_generation.py`
   - Neo4j import: `import_single_scene_to_neo4j.py`
   - Question generation: `qa_generator_v2/generator.py`
   - VLM answer evaluation: `vqa_pipeline/pipeline.py`

3. **Inspect intermediate data**:
   ```python
   # Save scene graph
   with open("debug_scene.json", "w") as f:
       json.dump(scene_graph, f, indent=2)
   ```

---

## 🤝 Contributing

### Adding Support for New VLM

1. Implement `BaseVLMModel` interface
2. Add config in `vqa_pipeline/config.py`
3. Test on 5-10 sample questions
4. Report accuracy on long-tail scenarios
5. Update evaluation results

### Improving Coverage Metrics

1. Analyze current gaps: `diag_l2.py`
2. Propose new metric formula
3. Validate against ground truth
4. Update `calculate_coverage_precise.py`
5. Re-evaluate all models

---

**Last Updated**: 2026-04-09  
**Maintainer**: ADVTEST Team
