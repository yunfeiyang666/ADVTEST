"""
Artifact layout for the clean v7 pipeline.

This module only manages file names/paths. It does not implement old pipeline
logic and does not reintroduce L2A/L2B.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


@dataclass(frozen=True)
class V7ArtifactPaths:
    root: Path
    scene_id: str = "global"
    frame_id: str = "all"

    @property
    def frame_key(self) -> str:
        return f"{self.scene_id}_frame{self.frame_id}"


    @property
    def frame_dir(self) -> Path:
        return self.root / self.frame_key

    @property
    def offline_dir(self) -> Path:
        return self.frame_dir / "offline"

    @property
    def generation_dir(self) -> Path:
        return self.frame_dir / "generation"

    @property
    def reports_dir(self) -> Path:
        return self.frame_dir / "reports"

    @property
    def filtered_scene_graph(self) -> Path:
        return self.offline_dir / "scene_graphs" / f"{self.frame_key}_filtered_scene_graph.json"

    @property
    def initial_coverage_file(self) -> Path:
        return self.offline_dir / "initial_coverage" / f"{self.frame_key}_initial_coverage.jsonl"

    @property
    def generated_jsonl(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_generated.jsonl"

    @property
    def generated_csv(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_generated.csv"

    # ── Round-specific outputs ──
    @property
    def round1_jsonl(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_round1.jsonl"

    @property
    def round1_csv(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_round1.csv"

    @property
    def round2_jsonl(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_round2.jsonl"

    @property
    def round2_csv(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_round2.csv"

    @property
    def all_jsonl(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_all.jsonl"

    @property
    def all_csv(self) -> Path:
        return self.generation_dir / "qa" / f"{self.frame_key}_all.csv"

    @property
    def summary_csv(self) -> Path:
        return self.reports_dir / f"{self.frame_key}_summary.csv"


    @property
    def coverage_state_file(self) -> Path:
        return self.generation_dir / "coverage_state" / f"{self.frame_key}_coverage_state.json"

    @property
    def summary_file(self) -> Path:
        return self.reports_dir / f"{self.frame_key}_summary.json"

    @property
    def manifest_file(self) -> Path:
        return self.frame_dir / "manifest.json"

    def as_dict(self) -> Dict[str, str]:
        return {
            "generated_csv": str(self.generated_csv),
            "summary_csv": str(self.summary_csv),

            "filtered_scene_graph": str(self.filtered_scene_graph),
            "initial_coverage_file": str(self.initial_coverage_file),
            "generated_jsonl": str(self.generated_jsonl),
            "coverage_state_file": str(self.coverage_state_file),
            "summary_file": str(self.summary_file),
            "manifest_file": str(self.manifest_file),
        }


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")



def write_coverage_state(path: Path, coverage) -> None:
    write_json(
        path,
        {
            "schema": "v7_l2_coverage_state",
            "L0": sorted(coverage.l0),
            "L1": sorted(coverage.l1),
            "L2": sorted(coverage.l2),
            "totals": {"L0": len(coverage.l0), "L1": len(coverage.l1), "L2": len(coverage.l2)},
        },
    )


def write_manifest(paths: V7ArtifactPaths, *, summary: Optional[Dict[str, Any]] = None) -> None:
    payload: Dict[str, Any] = {"schema": "v7_artifact_manifest", "paths": paths.as_dict()}
    if summary is not None:
        payload["summary"] = summary
    write_json(paths.manifest_file, payload)

