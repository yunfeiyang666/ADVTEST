import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Sequence

from qatest_adapted import normalize_text


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def jsonl_bytes(records: Iterable[dict]) -> bytes:
    return "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records
    ).encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def sanitize_suite(records: Sequence[dict], *, call_budget: int) -> dict:
    if call_budget < 1:
        raise ValueError("call_budget must be positive")

    selected = []
    duplicate_keys = set()
    seen = set()
    calls = 0
    consumed = 0

    for record in records:
        consumed += 1
        cost = record.get("vlm_call_cost", 1)
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 1:
            raise ValueError(f"Invalid vlm_call_cost: {cost!r}")
        key = (
            str(record.get("scene_frame") or "unknown"),
            normalize_text(str(record.get("question") or "")),
        )
        if key in seen:
            duplicate_keys.add(key)
            continue
        if calls + cost > call_budget:
            raise ValueError(
                f"Cannot consume exact budget {call_budget}; next cost is {cost}"
            )
        seen.add(key)
        selected.append(dict(record))
        calls += cost
        if calls == call_budget:
            break

    if calls != call_budget:
        raise ValueError(
            f"Suite only provides {calls} unique calls; {call_budget} required"
        )

    return {
        "records": selected,
        "questions": len(selected),
        "calls": calls,
        "input_records_consumed": consumed,
        "skipped_duplicate_questions": len(duplicate_keys),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create an exact-call mPLUG suite after same-frame text dedupe."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--call-budget", type=int, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    source_data = args.source.read_bytes()
    result = sanitize_suite(
        list(iter_jsonl(args.source)),
        call_budget=args.call_budget,
    )
    output_data = jsonl_bytes(result["records"])
    atomic_write(args.output, output_data)
    manifest = {
        "schema_version": 1,
        "source_path": str(args.source.absolute()),
        "source_sha256": sha256_bytes(source_data),
        "output_path": str(args.output.absolute()),
        "output_sha256": sha256_bytes(output_data),
        "call_budget": args.call_budget,
        "questions": result["questions"],
        "calls": result["calls"],
        "input_records_consumed": result["input_records_consumed"],
        "skipped_duplicate_questions": result["skipped_duplicate_questions"],
    }
    atomic_write(
        args.manifest,
        (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
            "utf-8"
        ),
    )
    print(
        f"[suite-sanitize] questions={manifest['questions']} "
        f"skipped={manifest['skipped_duplicate_questions']} "
        f"output={args.output}"
    )


if __name__ == "__main__":
    main()
