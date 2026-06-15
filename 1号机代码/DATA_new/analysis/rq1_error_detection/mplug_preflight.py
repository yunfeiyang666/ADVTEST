import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

from experiment_protocol import validate_provenance, validate_question_boundary
from qatest_adapted import normalize_text
from run_suite_evaluation import get_scene_frame, resolve_image_path


ImageResolver = Callable[[dict, Path, Path, Path], Optional[Path]]


@dataclass(frozen=True)
class PreflightConfig:
    call_budget: int
    outputs_root: Path
    dataroot: Path
    mosaic_dir: Path


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def scene_graph_path(outputs_root: Path, scene_frame: str) -> Path:
    return (
        outputs_root
        / scene_frame
        / "offline"
        / "scene_graphs"
        / f"{scene_frame}_filtered_scene_graph.json"
    )


def _failure(code: str, message: str, question_index: Optional[int] = None) -> dict:
    failure = {"code": code, "message": message}
    if question_index is not None:
        failure["question_index"] = question_index
    return failure


def audit_suite(
    path: Path,
    config: PreflightConfig,
    *,
    image_resolver: ImageResolver = resolve_image_path,
) -> dict:
    failures = []
    if not path.exists():
        failures.append(_failure("missing_suite", f"Suite does not exist: {path}"))
        return _result(path, config, [], 0, failures)

    records = list(iter_jsonl(path))
    prefix = []
    evaluated_calls = 0
    for record in records:
        cost = record.get("vlm_call_cost", 1)
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 1:
            failures.append(
                _failure(
                    "invalid_vlm_call_cost",
                    f"vlm_call_cost must be a positive integer: {cost!r}",
                    len(prefix) + 1,
                )
            )
            break
        if evaluated_calls + cost > config.call_budget:
            failures.append(
                _failure(
                    "call_budget_unreachable",
                    "Next record would exceed the requested call budget.",
                    len(prefix) + 1,
                )
            )
            break
        prefix.append(record)
        evaluated_calls += cost
        if evaluated_calls == config.call_budget:
            break

    if evaluated_calls < config.call_budget:
        failures.append(
            _failure(
                "insufficient_call_capacity",
                f"Suite provides {evaluated_calls} usable calls; "
                f"{config.call_budget} required.",
            )
        )

    normalized_seen = {}
    frames_with_valid_graphs = set()
    for index, record in enumerate(prefix, start=1):
        question = str(record.get("question") or "").strip()
        answer = str(record.get("answer") or "").strip()
        if not question:
            failures.append(_failure("missing_question", "Question is empty.", index))
        if not answer:
            failures.append(_failure("missing_answer", "Answer is empty.", index))

        try:
            validate_provenance(record)
        except ValueError as exc:
            failures.append(_failure("missing_provenance", str(exc), index))
        layer = str(record.get("experiment_layer") or "")
        try:
            validate_question_boundary(record, layer)
        except ValueError as exc:
            failures.append(_failure("boundary_violation", str(exc), index))

        normalized = normalize_text(question)
        if normalized in normalized_seen:
            failures.append(
                _failure(
                    "duplicate_normalized_question",
                    f"Duplicates question {normalized_seen[normalized]}.",
                    index,
                )
            )
        elif normalized:
            normalized_seen[normalized] = index

        if (
            record.get("question_source") == "nuscenes_qa"
            and not str(record.get("source_question_id") or "").strip()
        ):
            failures.append(
                _failure(
                    "missing_official_source_id",
                    "NuScenes-QA-derived record has no source question ID.",
                    index,
                )
            )

        scene_frame = get_scene_frame(record)
        graph_path = scene_graph_path(config.outputs_root, scene_frame)
        if scene_frame == "unknown" or not graph_path.exists():
            failures.append(
                _failure(
                    "missing_scene_graph",
                    f"Real scene graph is unavailable for {scene_frame}.",
                    index,
                )
            )
        else:
            frames_with_valid_graphs.add(scene_frame)

    if len(frames_with_valid_graphs) == len(
        {get_scene_frame(record) for record in prefix}
    ):
        for index, record in enumerate(prefix, start=1):
            image_path = image_resolver(
                record,
                config.outputs_root,
                config.mosaic_dir,
                config.dataroot,
            )
            if image_path is None or not Path(image_path).is_file():
                failures.append(
                    _failure(
                        "missing_real_mosaic",
                        f"Real mosaic is unavailable for {get_scene_frame(record)}.",
                        index,
                    )
                )

    return _result(path, config, prefix, evaluated_calls, failures)


def _result(
    path: Path,
    config: PreflightConfig,
    prefix: Sequence[dict],
    evaluated_calls: int,
    failures: Sequence[dict],
) -> dict:
    return {
        "suite": str(path),
        "suite_sha256": sha256_file(path) if path.exists() else None,
        "requested_calls": config.call_budget,
        "evaluated_questions": len(prefix),
        "evaluated_calls": evaluated_calls,
        "unique_frames": len({get_scene_frame(record) for record in prefix}),
        "passed": not failures,
        "failure_codes": sorted({failure["code"] for failure in failures}),
        "failures": list(failures),
    }


def run_preflight(
    suites: Sequence[Path],
    config: PreflightConfig,
) -> dict:
    results = [audit_suite(path, config) for path in suites]
    return {
        "passed": all(result["passed"] for result in results),
        "call_budget": config.call_budget,
        "suites": results,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight real mPLUG suites.")
    parser.add_argument("--suite", type=Path, action="append", required=True)
    parser.add_argument("--call-budget", type=int, required=True)
    parser.add_argument("--outputs-root", type=Path, required=True)
    parser.add_argument("--dataroot", type=Path, required=True)
    parser.add_argument("--mosaic-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = PreflightConfig(
        call_budget=args.call_budget,
        outputs_root=args.outputs_root,
        dataroot=args.dataroot,
        mosaic_dir=args.mosaic_dir,
    )
    payload = run_preflight(args.suite, config)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[mplug-preflight] suites={len(payload['suites'])} "
        f"passed={payload['passed']} output={args.output}"
    )
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
