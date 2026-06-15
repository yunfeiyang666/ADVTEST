import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Mapping


APPROVED_METHODS = (
    "advtest",
    "random",
    "official_qa",
    "qatest_adapted",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def iter_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def select_prefix(path: Path, call_budget: int) -> tuple[list[dict], int]:
    records = []
    calls = 0
    for record in iter_jsonl(path):
        cost = record.get("vlm_call_cost", 1)
        if not isinstance(cost, int) or isinstance(cost, bool) or cost < 1:
            raise ValueError(f"{path} has invalid vlm_call_cost: {cost!r}")
        if calls + cost > call_budget:
            raise ValueError(
                f"{path} cannot reach exactly {call_budget} calls; "
                f"next record costs {cost}"
            )
        records.append(record)
        calls += cost
        if calls == call_budget:
            return records, calls
    raise ValueError(
        f"{path} only provides {calls} calls; {call_budget} required"
    )


def jsonl_bytes(records: Iterable[dict]) -> bytes:
    text = "".join(
        json.dumps(record, ensure_ascii=False) + "\n" for record in records
    )
    return text.encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def assemble_suites(
    sources: Mapping[str, Path],
    output_dir: Path,
    *,
    call_budget: int,
) -> dict:
    if call_budget < 1:
        raise ValueError("call_budget must be positive")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory is not empty: {output_dir}")

    prepared = {}
    for method, raw_path in sources.items():
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(f"Suite source does not exist: {path}")
        records, calls = select_prefix(path, call_budget)
        output_data = jsonl_bytes(records)
        prepared[method] = {
            "source": path,
            "source_sha256": sha256_bytes(path.read_bytes()),
            "records": records,
            "calls": calls,
            "output_data": output_data,
            "output_sha256": sha256_bytes(output_data),
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "call_budget": call_budget,
        "suites": {},
    }
    for method, item in prepared.items():
        output_path = output_dir / f"{method}_suite.jsonl"
        atomic_write(output_path, item["output_data"])
        manifest["suites"][method] = {
            "source_path": str(item["source"].absolute()),
            "source_sha256": item["source_sha256"],
            "output_path": str(output_path.absolute()),
            "output_sha256": item["output_sha256"],
            "questions": len(item["records"]),
            "calls": item["calls"],
        }

    manifest_data = (
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    atomic_write(output_dir / "assembly_manifest.json", manifest_data)
    return manifest


def parse_sources(values: list[str]) -> dict[str, Path]:
    sources = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Source must use METHOD=PATH syntax: {value}")
        method, path = value.split("=", 1)
        if method not in APPROVED_METHODS:
            raise ValueError(f"Unsupported smoke method: {method}")
        sources[method] = Path(path)
    missing = sorted(set(APPROVED_METHODS).difference(sources))
    if missing:
        raise ValueError("Missing smoke sources: " + ", ".join(missing))
    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble mPLUG smoke suites.")
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--call-budget", type=int, required=True)
    args = parser.parse_args()

    manifest = assemble_suites(
        parse_sources(args.source),
        args.output_dir,
        call_budget=args.call_budget,
    )
    print(
        f"[mplug-assemble] suites={len(manifest['suites'])} "
        f"calls={manifest['call_budget']} output={args.output_dir}"
    )


if __name__ == "__main__":
    main()
