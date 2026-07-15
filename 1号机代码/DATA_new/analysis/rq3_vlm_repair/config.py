from pathlib import Path


MODULE_DIR = Path(__file__).resolve().parent
DATA_NEW_ROOT = MODULE_DIR.parents[1]
WORKSPACE_ROOT = MODULE_DIR.parents[3]
OUTPUTS_ROOT = DATA_NEW_ROOT / "outputs"
ALL_FRAMES_STATS = OUTPUTS_ROOT / "all_frames_stats.csv"
DATAROOT = DATA_NEW_ROOT / "data"
OFFICIAL_QUESTIONS_PATH = DATAROOT / "NuScenes_val_questions.json"
SCRATCH_ROOT = WORKSPACE_ROOT / "scratch" / "rq3_vlm_repair"
FORMAL_TEST_FRAME_CACHE = (
    WORKSPACE_ROOT
    / "scratch"
    / "rq1_seed_expansion"
    / "runs"
    / "official-frame-cache-target3500"
    / "results"
    / "frame_cache.json"
)

SPLIT_SEED = 20260715
TEST_SCENES = (
    "scene-0003",
    "scene-0012",
    "scene-0013",
    "scene-0014",
    "scene-0015",
    "scene-0016",
    "scene-0017",
    "scene-0018",
)
VALIDATION_SCENES = (
    "scene-0096",
    "scene-0106",
    "scene-0274",
    "scene-0277",
    "scene-0331",
    "scene-0523",
    "scene-0555",
    "scene-0559",
    "scene-0563",
    "scene-0565",
    "scene-0783",
    "scene-0797",
    "scene-0930",
    "scene-1066",
)

TRAINING_QUOTAS = {
    "l0": 1400,
    "l1": 1850,
    "converge": 1900,
    "direction_chain": 800,
    "distance_chain": 1750,
    "viewpoint_transfer": 2300,
}
VALIDATION_STRUCTURAL_QUOTAS = {
    "l0": 100,
    "l1": 100,
    "converge": 100,
    "direction_chain": 100,
    "distance_chain": 100,
    "viewpoint_transfer": 100,
}
VALIDATION_OFFICIAL_QUOTA = 400
HARD_CANDIDATE_QUOTAS = {
    "l0": 5000,
    "l1": 4500,
    "converge": 4500,
    "direction_chain": 9000,
    "distance_chain": 4500,
    "viewpoint_transfer": 4500,
}

EXPECTED_COUNTS = {
    "train_scenes": 128,
    "train_effective_frames": 4961,
    "validation_scenes": 14,
    "validation_effective_frames": 542,
    "test_scenes": 8,
    "test_effective_frames": 264,
    "test_formal_frames": 308,
}
