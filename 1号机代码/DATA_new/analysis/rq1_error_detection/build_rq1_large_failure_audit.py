import argparse
import csv
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from build_rq1_failure_audit import (
    DEFAULT_RESULTS_DIR,
    first_by_l2_key,
    first_by_signature,
    load_failures,
    sample_for_l2_key,
)


LARGE_REVIEW_FIELDS = [
    "audit_group",
    "bucket",
    "method",
    "l2_key",
    "scene_frame",
    "l2_item",
    "family",
    "question_index",
    "question_id",
    "question",
    "answer",
    "predicted",
    "image_path",
    "auto_valid_failure",
    "auto_issue_type",
    "auto_confidence",
    "auto_notes",
    "manual_valid_failure",
    "manual_issue_type",
    "manual_notes",
]

ISSUE_VALID = "valid_visual_or_structural_error"
ISSUE_GRANULARITY = "answer_granularity_mismatch"
ISSUE_OTHER = "other"


def normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def compact_id(value) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize_text(value))


def answer_id_parts(answer) -> tuple[str, str] | None:
    text = compact_id(answer)
    match = re.fullmatch(r"([a-z]+)(\d+)", text)
    if not match:
        return None
    return match.group(1), match.group(2)


def predicted_contains_id(predicted: str, category: str, number: str) -> bool:
    compact = compact_id(predicted)
    if f"{category}{number}" in compact:
        return True
    return bool(
        re.search(
            rf"\b{re.escape(category)}\s*{re.escape(number)}\b",
            normalize_text(predicted),
        )
    )


def contains_yes(predicted: str) -> bool:
    return bool(re.search(r"\b(yes|true)\b", normalize_text(predicted)))


def contains_no(predicted: str) -> bool:
    return bool(re.search(r"\b(no|false)\b", normalize_text(predicted)))


def candidate_ids_from_l2(l2_item: str) -> list[str]:
    return [part for part in re.split(r"[|:]+", l2_item) if part]


def auto_prefill(sample: Mapping) -> dict:
    answer = sample.get("answer")
    predicted = str(sample.get("predicted") or "")
    question = normalize_text(sample.get("question") or "")
    pred_norm = normalize_text(predicted)
    answer_norm = normalize_text(answer)
    answer_compact = compact_id(answer)
    l2_item = str(sample.get("l2_item") or "")

    if isinstance(answer, bool) or answer_norm in {"true", "false"}:
        expected_true = bool(answer) if isinstance(answer, bool) else answer_norm == "true"
        if expected_true and contains_no(predicted):
            return {
                "auto_valid_failure": "yes",
                "auto_issue_type": ISSUE_VALID,
                "auto_confidence": "high",
                "auto_notes": "Expected true/yes but prediction is negative.",
            }
        if not expected_true and contains_yes(predicted):
            return {
                "auto_valid_failure": "yes",
                "auto_issue_type": ISSUE_VALID,
                "auto_confidence": "high",
                "auto_notes": "Expected false/no but prediction is affirmative.",
            }

    if answer_norm in {"left", "right"}:
        opposite = "right" if answer_norm == "left" else "left"
        if re.search(rf"\b{opposite}\b", pred_norm):
            return {
                "auto_valid_failure": "yes",
                "auto_issue_type": ISSUE_VALID,
                "auto_confidence": "high",
                "auto_notes": f"Expected {answer_norm}; prediction says {opposite}.",
            }

    id_parts = answer_id_parts(answer)
    if id_parts:
        category, number = id_parts
        if predicted_contains_id(predicted, category, number):
            return {
                "auto_valid_failure": "no",
                "auto_issue_type": "lexical_scoring_artifact",
                "auto_confidence": "medium",
                "auto_notes": "Prediction appears to contain the expected instance id.",
            }
        contains_category = re.search(rf"\b{re.escape(category)}s?\b", pred_norm)
        l2_candidates = {compact_id(item) for item in candidate_ids_from_l2(l2_item)}
        predicted_candidate_ids = [
            candidate for candidate in l2_candidates if candidate and candidate in compact_id(predicted)
        ]
        wrong_category = bool(
            re.search(
                r"\b(bus|car|truck|pedestrian|bicycle|barrier|motorcycle|trailer)\b",
                pred_norm,
            )
            and not contains_category
        )
        if wrong_category or predicted_candidate_ids:
            return {
                "auto_valid_failure": "yes",
                "auto_issue_type": ISSUE_VALID,
                "auto_confidence": "medium",
                "auto_notes": "Prediction points to a different object/category or wrong candidate id.",
            }
        if contains_category and (
            question.startswith("what ")
            or question.startswith("identify ")
            or " what is it" in question
            or "what is it?" in question
        ):
            return {
                "auto_valid_failure": "no",
                "auto_issue_type": ISSUE_GRANULARITY,
                "auto_confidence": "medium",
                "auto_notes": "Prediction gives the object category/description but omits the required instance id.",
            }

    if answer_compact and answer_compact not in compact_id(predicted):
        if any(token in question for token in ("nearer", "closer", "shorter distance")):
            return {
                "auto_valid_failure": "yes",
                "auto_issue_type": ISSUE_VALID,
                "auto_confidence": "medium",
                "auto_notes": "Distance-comparison answer is absent and prediction selects a different candidate.",
            }

    return {
        "auto_valid_failure": "uncertain",
        "auto_issue_type": ISSUE_OTHER,
        "auto_confidence": "low",
        "auto_notes": "Heuristic cannot confidently classify this failure; manual review required.",
    }


def scene_frame_from_key(l2_key: str) -> str:
    return l2_key.split("::", 1)[0] if "::" in l2_key else "unknown"


def select_from_family(
    family: str,
    pool: list[str],
    selected: list[str],
    selected_set: set[str],
    scene_counts: Counter,
    *,
    desired: int,
    max_per_scene: int,
) -> None:
    for key in pool:
        if len(selected) >= desired:
            break
        if key in selected_set:
            continue
        scene = scene_frame_from_key(key)
        if scene_counts[scene] >= max_per_scene:
            continue
        selected.append(key)
        selected_set.add(key)
        scene_counts[scene] += 1


def stratified_scene_capped_keys(
    keys: Iterable[str],
    index: Mapping[str, Mapping],
    *,
    target: int,
    min_per_family: int,
    max_per_scene: int,
    seed: int,
) -> list[str]:
    rng = random.Random(seed)
    groups = defaultdict(list)
    for key in sorted(keys):
        groups[str(index[key].get("family") or "unknown")].append(key)
    for family_keys in groups.values():
        rng.shuffle(family_keys)

    selected: list[str] = []
    selected_set: set[str] = set()
    scene_counts: Counter = Counter()

    for family in sorted(groups):
        available = len(groups[family])
        quota = min(min_per_family, available)
        select_from_family(
            family,
            groups[family],
            selected,
            selected_set,
            scene_counts,
            desired=len(selected) + quota,
            max_per_scene=max_per_scene,
        )

    family_order = sorted(groups)
    while len(selected) < target:
        progressed = False
        for family in family_order:
            before = len(selected)
            select_from_family(
                family,
                groups[family],
                selected,
                selected_set,
                scene_counts,
                desired=len(selected) + 1,
                max_per_scene=max_per_scene,
            )
            progressed = progressed or len(selected) > before
            if len(selected) >= target:
                break
        if not progressed:
            break

    return selected[:target]


def add_review_row(
    rows: list[dict],
    *,
    audit_group: str,
    bucket: str,
    sample: Mapping,
) -> None:
    auto = auto_prefill(sample)
    rows.append(
        {
            "audit_group": audit_group,
            "bucket": bucket,
            "method": sample["method"],
            "l2_key": sample["l2_key"],
            "scene_frame": sample["scene_frame"],
            "l2_item": sample["l2_item"],
            "family": sample["family"],
            "question_index": sample["question_index"],
            "question_id": sample["question_id"],
            "question": sample["question"],
            "answer": sample["answer"],
            "predicted": sample["predicted"],
            "image_path": sample["image_path"],
            **auto,
            "manual_valid_failure": "",
            "manual_issue_type": "",
            "manual_notes": "",
        }
    )


def family_count_for_keys(keys: Sequence[str], index: Mapping[str, Mapping]) -> dict[str, int]:
    return dict(Counter(str(index[key].get("family") or "unknown") for key in keys))


def scene_count_for_keys(keys: Sequence[str]) -> dict[str, int]:
    return dict(Counter(scene_frame_from_key(key) for key in keys))


def wilson_interval(successes: int, total: int, z: float = 1.96) -> dict:
    if total == 0:
        return {"lower": None, "upper": None}
    phat = successes / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return {"lower": max(0.0, center - half), "upper": min(1.0, center + half)}


def auto_ci_for_bucket(rows: Sequence[Mapping], universe_total: int) -> dict:
    total = len(rows)
    successes = sum(row.get("auto_valid_failure") == "yes" for row in rows)
    rate = successes / total if total else 0.0
    interval = wilson_interval(successes, total)
    return {
        "universe_total": universe_total,
        "sample_rows": total,
        "auto_valid_yes": successes,
        "auto_valid_rate": rate,
        "wilson_95_rate_lower": interval["lower"],
        "wilson_95_rate_upper": interval["upper"],
        "estimated_valid_total": universe_total * rate,
        "estimated_valid_total_lower": (
            universe_total * interval["lower"] if interval["lower"] is not None else None
        ),
        "estimated_valid_total_upper": (
            universe_total * interval["upper"] if interval["upper"] is not None else None
        ),
    }


def build_large_audit(
    advtest_raw: Path,
    random_raw: Path,
    *,
    exclusive_samples_per_bucket: int,
    shared_pairs: int,
    min_per_family: int,
    max_per_scene: int,
    seed: int,
) -> dict:
    adv_records = load_failures(advtest_raw)
    random_records = load_failures(random_raw)
    adv_l2_index = first_by_l2_key(adv_records)
    random_l2_index = first_by_l2_key(random_records)
    adv_l2 = set(adv_l2_index)
    random_l2 = set(random_l2_index)

    adv_only = adv_l2 - random_l2
    random_only = random_l2 - adv_l2
    shared = adv_l2 & random_l2

    adv_only_keys = stratified_scene_capped_keys(
        adv_only,
        adv_l2_index,
        target=exclusive_samples_per_bucket,
        min_per_family=min_per_family,
        max_per_scene=max_per_scene,
        seed=seed,
    )
    random_only_keys = stratified_scene_capped_keys(
        random_only,
        random_l2_index,
        target=exclusive_samples_per_bucket,
        min_per_family=min_per_family,
        max_per_scene=max_per_scene,
        seed=seed + 1,
    )
    shared_keys = stratified_scene_capped_keys(
        shared,
        adv_l2_index,
        target=shared_pairs,
        min_per_family=min_per_family,
        max_per_scene=max_per_scene,
        seed=seed + 2,
    )

    rows: list[dict] = []
    for index, key in enumerate(adv_only_keys, start=1):
        add_review_row(
            rows,
            audit_group=f"advtest_only_l2_{index:03d}",
            bucket="advtest_only_l2",
            sample=sample_for_l2_key(adv_l2_index[key], key),
        )
    for index, key in enumerate(random_only_keys, start=1):
        add_review_row(
            rows,
            audit_group=f"random_only_l2_{index:03d}",
            bucket="random_only_l2",
            sample=sample_for_l2_key(random_l2_index[key], key),
        )
    for index, key in enumerate(shared_keys, start=1):
        group = f"shared_l2_{index:03d}"
        add_review_row(
            rows,
            audit_group=group,
            bucket="shared_l2_advtest",
            sample=sample_for_l2_key(adv_l2_index[key], key),
        )
        add_review_row(
            rows,
            audit_group=group,
            bucket="shared_l2_random",
            sample=sample_for_l2_key(random_l2_index[key], key),
        )

    by_bucket = defaultdict(list)
    for row in rows:
        by_bucket[row["bucket"]].append(row)

    universe = {
        "advtest_failed_unique_l2": len(adv_l2),
        "random_failed_unique_l2": len(random_l2),
        "advtest_only_l2": len(adv_only),
        "random_only_l2": len(random_only),
        "shared_l2": len(shared),
        "advtest_unique_failure_signatures": len(first_by_signature(adv_records)),
        "random_unique_failure_signatures": len(first_by_signature(random_records)),
    }
    effective_ci = {
        "label_source": "auto_prefill_heuristic_not_final_human_review",
        "confidence_method": "Wilson 95% interval over sampled rows",
        "buckets": {
            "advtest_only_l2": auto_ci_for_bucket(
                by_bucket["advtest_only_l2"], universe["advtest_only_l2"]
            ),
            "random_only_l2": auto_ci_for_bucket(
                by_bucket["random_only_l2"], universe["random_only_l2"]
            ),
            "shared_l2_advtest": auto_ci_for_bucket(
                by_bucket["shared_l2_advtest"], universe["shared_l2"]
            ),
            "shared_l2_random": auto_ci_for_bucket(
                by_bucket["shared_l2_random"], universe["shared_l2"]
            ),
        },
    }
    adv_est = effective_ci["buckets"]["advtest_only_l2"]["estimated_valid_total"]
    random_est = effective_ci["buckets"]["random_only_l2"]["estimated_valid_total"]
    effective_ci["advtest_only_minus_random_only_estimated_valid_total"] = (
        adv_est - random_est
    )

    manifest = {
        "schema_version": 1,
        "seed": seed,
        "sampling_policy": {
            "exclusive_samples_per_bucket": exclusive_samples_per_bucket,
            "shared_pairs": shared_pairs,
            "min_per_family": min_per_family,
            "max_per_scene": max_per_scene,
            "family_strategy": (
                "Take up to min_per_family from every available family first, "
                "then fill remaining slots under the scene cap."
            ),
        },
        "source_paths": {
            "advtest": str(advtest_raw),
            "random": str(random_raw),
        },
        "universe": universe,
        "selected": {
            "advtest_only_l2": {
                "count": len(adv_only_keys),
                "family_counts": family_count_for_keys(adv_only_keys, adv_l2_index),
                "scene_counts": scene_count_for_keys(adv_only_keys),
            },
            "random_only_l2": {
                "count": len(random_only_keys),
                "family_counts": family_count_for_keys(random_only_keys, random_l2_index),
                "scene_counts": scene_count_for_keys(random_only_keys),
            },
            "shared_l2_pairs": {
                "count": len(shared_keys),
                "family_counts": family_count_for_keys(shared_keys, adv_l2_index),
                "scene_counts": scene_count_for_keys(shared_keys),
            },
        },
    }

    return {
        "manifest": manifest,
        "review_rows": rows,
        "effective_ci": effective_ci,
    }


def write_csv(path: Path, rows: Sequence[Mapping], fields: Sequence[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def count_rows_by_field(rows: Sequence[Mapping], field: str) -> dict[str, int]:
    return dict(Counter(str(row.get(field) or "unknown") for row in rows))


def write_readme(output_dir: Path, payload: Mapping) -> None:
    manifest = payload["manifest"]
    ci = payload["effective_ci"]
    lines = [
        "# RQ1 Large Failure Audit",
        "",
        "This package expands the 48-row sanity-check audit into a larger, "
        "stratified review set for ADVTEST vs Random failed L2 coverage.",
        "",
        "## Sampling",
        "",
        f"- Seed: `{manifest['seed']}`",
        f"- ADVTEST-only samples: `{manifest['selected']['advtest_only_l2']['count']}`",
        f"- Random-only samples: `{manifest['selected']['random_only_l2']['count']}`",
        f"- Shared L2 pairs: `{manifest['selected']['shared_l2_pairs']['count']}` "
        f"({manifest['selected']['shared_l2_pairs']['count'] * 2} review rows)",
        f"- Max rows per scene per bucket: `{manifest['sampling_policy']['max_per_scene']}`",
        "",
        "Rare families are selected first up to the requested minimum; because "
        "some rare families have fewer than the requested minimum in the source "
        "universe, all available rare-family rows are retained.",
        "",
        "## Auto-Prefill",
        "",
        "The CSV includes heuristic `auto_*` columns to speed human review. "
        "They are not final labels. Human reviewers should fill "
        "`manual_valid_failure`, `manual_issue_type`, and `manual_notes`.",
        "",
        "## Auto-Prefill CI Preview",
        "",
        "- Label source: "
        f"`{ci['label_source']}`",
        "- ADVTEST-only estimated valid total: "
        f"{ci['buckets']['advtest_only_l2']['estimated_valid_total']:.1f}",
        "- Random-only estimated valid total: "
        f"{ci['buckets']['random_only_l2']['estimated_valid_total']:.1f}",
        "- Difference: "
        f"{ci['advtest_only_minus_random_only_estimated_valid_total']:.1f}",
        "",
        "Use this only as a triage preview until manual review is complete.",
        "",
        "## Files",
        "",
        "- `large_sampling_manifest.json`: universe counts, selected counts, family and scene distributions.",
        "- `auto_prefill_review.csv`: large review sheet with auto-prefill fields and blank manual fields.",
        "- `large_manual_review_samples.csv`: same review sheet under the manual-review-oriented filename.",
        "- `effective_failure_ci.json`: Wilson intervals from auto-prefill labels; replace with manual labels after review.",
        "- `large_review_summary.md`: human-readable generation summary.",
        "",
    ]
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_large_audit(output_dir: Path, payload: Mapping) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "large_sampling_manifest.json").write_text(
        json.dumps(payload["manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "effective_failure_ci.json").write_text(
        json.dumps(payload["effective_ci"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    write_csv(
        output_dir / "auto_prefill_review.csv",
        payload["review_rows"],
        LARGE_REVIEW_FIELDS,
    )
    write_csv(
        output_dir / "large_manual_review_samples.csv",
        payload["review_rows"],
        LARGE_REVIEW_FIELDS,
    )
    summary = {
        "rows": len(payload["review_rows"]),
        "by_bucket": count_rows_by_field(payload["review_rows"], "bucket"),
        "by_auto_valid_failure": count_rows_by_field(
            payload["review_rows"], "auto_valid_failure"
        ),
        "by_auto_issue_type": count_rows_by_field(
            payload["review_rows"], "auto_issue_type"
        ),
    }
    (output_dir / "large_review_summary.md").write_text(
        "# RQ1 Large Review Summary\n\n"
        f"- Rows: {summary['rows']}\n"
        f"- By bucket: `{summary['by_bucket']}`\n"
        f"- By auto validity: `{summary['by_auto_valid_failure']}`\n"
        f"- By auto issue type: `{summary['by_auto_issue_type']}`\n",
        encoding="utf-8",
    )
    write_readme(output_dir, payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a larger stratified RQ1 failure audit set."
    )
    parser.add_argument(
        "--advtest-raw",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "advtest_suite_raw_results.jsonl",
    )
    parser.add_argument(
        "--random-raw",
        type=Path,
        default=DEFAULT_RESULTS_DIR / "random_suite_raw_results.jsonl",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("experiments/rq1_failure_audit_large"),
    )
    parser.add_argument("--exclusive-samples-per-bucket", type=int, default=100)
    parser.add_argument("--shared-pairs", type=int, default=100)
    parser.add_argument("--min-per-family", type=int, default=10)
    parser.add_argument("--max-per-scene", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260616)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = build_large_audit(
        args.advtest_raw,
        args.random_raw,
        exclusive_samples_per_bucket=args.exclusive_samples_per_bucket,
        shared_pairs=args.shared_pairs,
        min_per_family=args.min_per_family,
        max_per_scene=args.max_per_scene,
        seed=args.seed,
    )
    write_large_audit(args.output_dir, payload)
    print(
        f"[rq1-large-audit] rows={len(payload['review_rows'])} "
        f"output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
