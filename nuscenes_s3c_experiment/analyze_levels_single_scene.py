import json
import re
from pathlib import Path
from collections import Counter

# -------- Config: pick one frame to inspect --------
SCENE_NAME = "scene-0553"
FRAME_IDX = 8

BASE = Path("output/coverage_analysis/vqa_results")
QA_PATH = BASE / f"{SCENE_NAME}_frame{FRAME_IDX}_official_qa.json"

REL_PATTERN = re.compile(r"\(\w+[^)]*\)-\[[^\]]*\]->\(\w+[^)]*\)")
STATUS_EQ_PATTERN = re.compile(r"\b(\w+)\.status\s*=\s*(\w+)\.status\b")


def classify_level(cypher: str) -> str:
    """Classify a question into L0/L1/L2 based on Cypher structure.

    Heuristic rules (from discussion):
      - L0: no relationship patterns and no cross-object status equality.
      - L1: exactly one relationship pattern and no cross-object status equality.
      - L2: otherwise (>=2 relationships, or any status equality/comparison).
    """
    if not cypher:
        return "L0"

    rels = REL_PATTERN.findall(cypher)
    rel_count = len(rels)

    has_status_eq = bool(STATUS_EQ_PATTERN.search(cypher)) or "same_status" in cypher

    # L2: multi-relational or explicit cross-object comparison
    if rel_count >= 2 or has_status_eq:
        return "L2"

    # L0: no explicit relationships
    if rel_count == 0:
        return "L0"

    # Otherwise single relation without comparison -> L1
    return "L1"


def main() -> None:
    if not QA_PATH.exists():
        raise FileNotFoundError(f"Official QA file not found: {QA_PATH}")

    with QA_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    print(f"Scene: {SCENE_NAME}_frame{FRAME_IDX}")
    print(f"Total questions: {len(results)}\n")

    level_counts = Counter()

    for idx, item in enumerate(results, 1):
        q = item.get("question", "").strip()
        cypher = (item.get("cypher_query") or item.get("cypher") or "").strip()
        lvl = classify_level(cypher)
        level_counts[lvl] += 1

        print(f"Q{idx:02d} [{lvl}]: {q}")

    print("\nSummary:")
    for lvl in ("L0", "L1", "L2"):
        print(f"  {lvl}: {level_counts[lvl]} questions")


if __name__ == "__main__":
    main()
