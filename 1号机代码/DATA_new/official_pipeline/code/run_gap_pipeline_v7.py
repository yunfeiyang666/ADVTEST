"""Clean unified-L2 pipeline entry point. No L2A/L2B, no LLM Cypher."""
from __future__ import annotations

import argparse
import json
import os
import collections
import csv
import random
import hashlib
import time


from pathlib import Path
from datetime import datetime, timezone
from neo4j import GraphDatabase, Query

from typing import Any, Dict, List, cast
from gap_pipeline.l2_artifacts import V7ArtifactPaths, write_coverage_state, write_jsonl, write_manifest


import advtest_env
from gap_pipeline.l2_adapter import plan_to_qa_record
from gap_pipeline.l2_initial_coverage_analyzer import export_initial_coverage
from gap_pipeline.l2_question_realizer import set_variant_seed
from gap_pipeline.postprocess_coverage import postprocess_coverage
from gap_pipeline.l2_offline_scene_graph import export_filtered_scene_graph
from gap_pipeline.l2_geometry import official_dir6_from_angle

from gap_pipeline.l2_cypher_builders import fetch_candidate_ref_directions
from gap_pipeline.l2_dry_run import DryRunInput, L2DryRunner
from gap_pipeline.l2_constraint_planner import L2ConstraintPlanner
from gap_pipeline.l2_gap_selector import L2CoverageState, L2GapSelector, l2_key, l1_key
from gap_pipeline.l2_llm_client import LLMClient
from gap_pipeline.random_full_coverage import (
    CoverageAccumulator,
    StaticRandomSelector,
    load_checkpoint as load_random_checkpoint,
    run_until_full as run_random_until_full,
    write_checkpoint as write_random_checkpoint,
)

from gap_pipeline.l2_table_export import append_qa_csv, write_qa_csv, write_summary_csv

import import_scene_graph_http

from gap_pipeline.l2_result_schema import normalize_and_validate




def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

from gap_pipeline.l2_taxonomy import L2Gap

class BoltNeo4jSession:
    def __init__(self, uri: str, user: str, password: str):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.session = self.driver.session(database=os.environ.get("NEO4J_DATABASE", "neo4j"))

    def run(self, cypher: str, **params):
        timeout = float(os.environ.get("NEO4J_VERIFY_TIMEOUT_SECONDS") or 300)
        return [dict(record) for record in self.session.run(Query(cast(Any, cypher), timeout=timeout), **params)]

    def close(self) -> None:
        self.session.close()
        self.driver.close()


def emit_records(records: List[Dict[str, Any]], output: Path | None) -> None:
    if output is None:
        for r in records:
            print(json.dumps(r, ensure_ascii=False))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def import_scene_graph_bolt(path: Path) -> Dict[str, int]:
    sg = json.loads(path.read_text(encoding="utf-8"))
    nodes = [import_scene_graph_http.flat_node(o) for o in (sg.get("nodes") or sg.get("objects") or [])]
    rels = [import_scene_graph_http.flat_rel(e) for e in (sg.get("edges") or sg.get("relationships") or [])]
    batch_size = int(os.environ.get("NEO4J_IMPORT_BATCH_SIZE") or 100)
    session = make_neo4j_session()
    try:
        print(f"[import_scene_graph_bolt] delete old graph uri={os.environ.get('NEO4J_URI', 'bolt://127.0.0.1:7687')}", flush=True)
        session.run("MATCH (n) DETACH DELETE n")
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            session.run("UNWIND $batch AS props CREATE (o:Object) SET o = props", batch=batch)
            print(f"[import_scene_graph_bolt] nodes {min(i + batch_size, len(nodes))}/{len(nodes)}", flush=True)
        for i in range(0, len(rels), batch_size):
            batch = rels[i:i + batch_size]
            session.run("""
UNWIND $batch AS item
MATCH (a:Object {unique_id:item.source})
MATCH (b:Object {unique_id:item.target})
CREATE (a)-[r:RELATES_TO]->(b)
SET r = item.props
""".strip(), batch=batch)
            print(f"[import_scene_graph_bolt] rels {min(i + batch_size, len(rels))}/{len(rels)}", flush=True)
        objects = session.run("MATCH (n:Object) RETURN count(n) AS objects")[0]["objects"]
        relationships = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS relationships")[0]["relationships"]
        stats = {"objects": int(objects), "relationships": int(relationships)}
        print(json.dumps({"import_scene_graph_bolt": stats}, ensure_ascii=False), flush=True)
        return stats
    finally:
        session.close()


def node_obj(row: Dict[str, Any], prefix: str) -> Dict[str, Any]:
    return {
        "id": row[f"{prefix}_id"], "unique_id": row[f"{prefix}_id"],
        "type": row[f"{prefix}_type"], "status": row.get(f"{prefix}_status") or "",
        "tx": row.get(f"{prefix}_tx"), "ty": row.get(f"{prefix}_ty"),
    }


def fetch_l2_gaps(session) -> List[Dict[str, Any]]:
    cypher = """


MATCH (a:Object)-[:RELATES_TO]->(b:Object)
MATCH (b)-[:RELATES_TO]->(c:Object)
WHERE a.unique_id < c.unique_id
  AND a.unique_id <> b.unique_id AND b.unique_id <> c.unique_id
  AND a.translation_x IS NOT NULL AND b.translation_x IS NOT NULL AND c.translation_x IS NOT NULL
WITH DISTINCT a, b, c
RETURN a.unique_id AS a_id, a.type AS a_type, a.status AS a_status, a.translation_x AS a_tx, a.translation_y AS a_ty,
       b.unique_id AS b_id, b.type AS b_type, b.status AS b_status, b.translation_x AS b_tx, b.translation_y AS b_ty,
       c.unique_id AS c_id, c.type AS c_type, c.status AS c_status, c.translation_x AS c_tx, c.translation_y AS c_ty
"""
    return [dict(r) for r in session.run(cypher)]


def fetch_l2_gaps_in_memory(graph_index: Dict[str, Any]) -> List[Dict[str, Any]]:
    objects = graph_index.get("objects", {})
    out_edges = graph_index.get("out", {})
    
    in_edges = {}
    for src, targets in out_edges.items():
        for tgt in targets:
            in_edges.setdefault(tgt, []).append(src)
            
    gaps = []
    for b_id in sorted(objects):
        b_obj = objects[b_id]
        b_tx, b_ty = object_xy(b_obj)
        if b_tx is None:
            continue
            
        sources = sorted(in_edges.get(b_id, []))
        targets = sorted(out_edges.get(b_id, {}))
        
        for a_id in sources:
            a_obj = objects.get(a_id)
            if not a_obj:
                continue
            a_tx, a_ty = object_xy(a_obj)
            if a_tx is None:
                continue
                
            for c_id in targets:
                if a_id == c_id or a_id == b_id or b_id == c_id:
                    continue
                if a_id >= c_id:
                    continue
                    
                c_obj = objects.get(c_id)
                if not c_obj:
                    continue
                c_tx, c_ty = object_xy(c_obj)
                if c_tx is None:
                    continue
                    
                gaps.append({
                    "a_id": a_id,
                    "a_type": a_obj.get("type") or a_obj.get("category") or "",
                    "a_status": a_obj.get("status") or "",
                    "a_tx": a_tx,
                    "a_ty": a_ty,
                    "b_id": b_id,
                    "b_type": b_obj.get("type") or b_obj.get("category") or "",
                    "b_status": b_obj.get("status") or "",
                    "b_tx": b_tx,
                    "b_ty": b_ty,
                    "c_id": c_id,
                    "c_type": c_obj.get("type") or c_obj.get("category") or "",
                    "c_status": c_obj.get("status") or "",
                    "c_tx": c_tx,
                    "c_ty": c_ty,
                })
    return gaps




def fetch_neo4j_graph_stats(session) -> Dict[str, Any]:
    obj_rows = list(session.run("MATCH (n:Object) RETURN count(n) AS n"))
    rel_rows = list(session.run("MATCH (:Object)-[r:RELATES_TO]->(:Object) RETURN count(r) AS n"))
    return {
        "object_count": int(obj_rows[0].get("n", 0)) if obj_rows else 0,
        "relationship_count": int(rel_rows[0].get("n", 0)) if rel_rows else 0,
    }

def load_frame_from_plan(plan_file: Path, *, frame_index: int = 0) -> Dict[str, Any]:
    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    frames = payload.get("frames", []) if isinstance(payload, dict) else []
    if not frames:
        raise ValueError(f"No frames found in plan file: {plan_file}")
    if frame_index < 0 or frame_index >= len(frames):
        raise IndexError(f"frame_index {frame_index} out of range for {plan_file}")
    frame = dict(frames[frame_index])
    if "scene_id" not in frame or "frame_id" not in frame:
        raise ValueError(f"Frame entry must contain scene_id and frame_id: {frame}")
    return frame


def resolve_scene_graph_path(frame_meta: Dict[str, Any], plan_file: Path | None = None) -> Path:
    raw = frame_meta.get("sg_path") or frame_meta.get("scene_graph") or frame_meta.get("sg_filename") or frame_meta.get("sg_file")
    if not raw:
        raise ValueError(f"Frame metadata missing sg_filename/sg_path: {frame_meta}")
    path = Path(str(raw))
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    if plan_file is not None:
        candidates.append(plan_file.parent / path)
        candidates.append(plan_file.parent.parent / path)
    candidates.extend([
        Path("filtered_scene_graphs") / path.name,
        Path("..") / "filtered_scene_graphs" / path.name,
        Path("code") / "filtered_scene_graphs" / path.name,
        path,
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Scene graph file not found for frame {frame_meta}: tried {[str(c) for c in candidates]}")


def generate_scene_graph_from_legacy(frame_meta: Dict[str, Any], plan_file: Path | None = None) -> Path:
    """Generate a filtered scene graph on-the-fly from NuScenes data.

    Uses the bundled scene_graph_gen/ package which contains:
      - v17_onthefly_sg: NuScenes → raw graph → core_universe_filter → filtered dict
      - generate_selected_scenes_improved: SceneGraphGenerator
      - core_universe_filter: node/edge filtering
      - vqa_pipeline/: direction_utils + status_inference
    """
    scene_id = str(frame_meta.get("scene_id"))
    if frame_meta.get("frame_id") is None:
        raise ValueError(f"Frame metadata missing frame_id: {frame_meta}")
    frame_id = int(frame_meta["frame_id"])

    # Output directory: DATA_new/filtered_scene_graphs/
    if plan_file:
        out_dir = plan_file.parent.parent.parent / "filtered_scene_graphs"
    else:
        out_dir = Path(__file__).resolve().parent.parent.parent / "filtered_scene_graphs"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Add scene_graph_gen/ to sys.path so its internal imports resolve
    import sys
    sg_gen_dir = Path(__file__).resolve().parent / "scene_graph_gen"
    if str(sg_gen_dir) not in sys.path:
        sys.path.insert(0, str(sg_gen_dir))

    from v17_onthefly_sg import build_filtered_sg_onthefly
    payload = build_filtered_sg_onthefly(scene_id, frame_id)
    if not payload:
        raise RuntimeError(f"Scene graph generation failed for {scene_id} frame {frame_id}")

    # Normalize direction fields to v7 schema
    payload = _normalize_v7_scene_graph_direction(payload)
    payload.setdefault("scene_name", scene_id)
    payload.setdefault("frame_id", frame_id)

    # Write to filtered_scene_graphs/
    out_file = out_dir / f"{scene_id}_frame{frame_id}_filtered_scene_graph.json"
    out_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_file.resolve()


def resolve_initial_qa_paths(frame_meta: Dict[str, Any], plan_file: Path | None = None) -> List[Path]:
    raw = frame_meta.get("initial_qa") or frame_meta.get("initial_qa_files") or frame_meta.get("baseline_qa") or frame_meta.get("original_qa") or frame_meta.get("qa_file")
    if not raw:
        return default_initial_qa_paths()
    values = raw if isinstance(raw, list) else [raw]
    resolved: List[Path] = []
    for item in values:
        path = Path(str(item))
        candidates = []
        if path.is_absolute():
            candidates.append(path)
        if plan_file is not None:
            candidates.extend([plan_file.parent / path, plan_file.parent.parent / path])
        candidates.extend([path, Path("..") / path, Path("..") / ".." / path])
        for candidate in candidates:
            if candidate.exists():
                resolved.append(candidate.resolve())
                break
        else:
            raise FileNotFoundError(f"Initial QA file not found for frame {frame_meta}: {item}")
    return resolved



def default_initial_qa_paths() -> List[Path]:
    advtest_env.load_advtest_env()
    raw = read_env_file_value("ADVTEST_INITIAL_QA") or read_env_file_value("ADVTEST_ORIGINAL_QA") or read_env_file_value("ADVTEST_BASELINE_QA") or os.environ.get("ADVTEST_INITIAL_QA") or os.environ.get("ADVTEST_ORIGINAL_QA") or os.environ.get("ADVTEST_BASELINE_QA")
    if not raw:
        return []
    paths: List[Path] = []
    for item in raw.split(";"):
        item = item.strip()
        if item:
            paths.append(Path(item))
    return paths


def object_ids_from_scene_graph(path: Path) -> List[str]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    objs = payload.get("objects") or payload.get("nodes") or []
    return [str(o.get("unique_id") or o.get("id")) for o in objs if o.get("unique_id") or o.get("id")]


def _load_env_file() -> None:
    """Auto-load advtest_runtime.env into os.environ (does NOT overwrite existing vars)."""
    path = Path(__file__).resolve().parent.parent / "advtest_runtime.env"  # official_pipeline/advtest_runtime.env
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:  # do not overwrite explicit env vars
            os.environ[k] = v

_load_env_file()  # auto-load on import


def read_env_file_value(key: str) -> str:
    path = Path(__file__).resolve().parent.parent / "advtest_runtime.env"  # official_pipeline/advtest_runtime.env
    if not path.exists():
        return ""
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return ""


def truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}





def scene_graph_counts(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {"raw_nodes": 0, "raw_edges": 0, "filtered_nodes": 0, "filtered_edges": 0}
    payload = json.loads(path.read_text(encoding="utf-8"))
    stats = payload.get("statistics") or {}
    return {
        "raw_nodes": int(stats.get("total_objects") or stats.get("raw_nodes") or 0),
        "raw_edges": int(stats.get("total_relationships") or stats.get("raw_edges") or 0),
        "filtered_nodes": len(payload.get("nodes") or payload.get("objects") or []),
        "filtered_edges": len(payload.get("edges") or payload.get("relationships") or []),
    }



def _normalize_v7_scene_graph_direction(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize copied legacy scene graphs to v7 direction_6 schema."""
    edges = payload.get("relationships") or payload.get("edges") or []
    for edge in edges:
        metrics = edge.get("metrics") or {}
        angle = edge.get("angle") if edge.get("angle") is not None else metrics.get("angle")
        direction = edge.get("direction_6") or edge.get("direction_official")
        if not direction and angle is not None:
            try:
                direction = official_dir6_from_angle(float(angle))
            except Exception:
                direction = None
        direction = str(direction or "").replace("-", "_")
        edge["direction_6"] = direction
        for old_key in ("direction" + "_8", "direction" + "_4"):
            edge.pop(old_key, None)
        if isinstance(metrics, dict):
            direction_ego = metrics.get("direction_ego")
            if isinstance(direction_ego, dict):
                direction_ego.pop("direction" + "_8", None)
                direction_ego.pop("angle_matches", None)
                direction_ego["direction_6"] = direction
            direction_source = metrics.get("direction_source")
            if isinstance(direction_source, dict):
                direction_source.pop("direction" + "_8", None)
                direction_source.pop("angle_matches", None)
                direction_source["direction_6"] = direction
        predicates = list(edge.get("predicates") or [])
        if direction:
            edge["predicates"] = [direction] + [str(p).replace("-", "_") for p in predicates[1:]]
    payload["schema"] = "v7_filtered_scene_graph_direction6"
    return payload


def copy_offline_scene_graph(src: Path, dst: Path, *, scene_id: str, frame_id: str) -> Dict[str, Any]:
    payload = json.loads(src.read_text(encoding="utf-8"))
    payload.setdefault("scene_name", scene_id)
    payload.setdefault("frame_id", frame_id)
    payload = _normalize_v7_scene_graph_direction(payload)

    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    objects = payload.get("objects") or payload.get("nodes") or []
    relationships = payload.get("relationships") or payload.get("edges") or []
    counts = scene_graph_counts(dst)
    return {"source": str(src), "objects": len(objects), "relationships": len(relationships), **counts}


def rows(session, query) -> List[Dict[str, Any]]:
    return [dict(r) for r in session.run(query.cypher, **query.params)]




def _rel_dir(rel: Dict[str, Any]) -> str:
    direction = rel.get("direction_6") or rel.get("direction_official")
    if direction:
        return str(direction)
    angle = rel.get("angle")
    try:
        return official_dir6_from_angle(float(angle)) or "" if angle is not None else ""
    except Exception:
        return ""


def load_graph_index(path: Path | None) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {"objects": {}, "out": {}}
    graph = json.loads(path.read_text(encoding="utf-8"))
    objs = graph.get("objects") or graph.get("nodes") or []
    rels = graph.get("relationships") or graph.get("edges") or []
    objects = {str(o.get("id") or o.get("unique_id")): o for o in objs}
    out: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for rel in rels:
        src = str(rel.get("src") or rel.get("source") or rel.get("from"))
        dst = str(rel.get("dst") or rel.get("target") or rel.get("to"))
        if not src or not dst or src == "None" or dst == "None":
            continue
        out.setdefault(src, {})[dst] = rel
    return {"objects": objects, "out": out}


def object_xy(obj: Dict[str, Any]) -> tuple[Any, Any]:
    trans = obj.get("translation") or {}
    return obj.get("tx") or obj.get("translation_x") or trans.get("x"), obj.get("ty") or obj.get("translation_y") or trans.get("y")


def graph_converge_rows(graph_index: Dict[str, Any], a_id: str, c_id: str) -> List[Dict[str, Any]]:
    objects = graph_index.get("objects", {})
    out = graph_index.get("out", {})
    common = set(out.get(str(a_id), {})) & set(out.get(str(c_id), {}))
    rows_out: List[Dict[str, Any]] = []
    for x_id in sorted(common):
        x = objects.get(str(x_id), {})
        tx, ty = object_xy(x)
        rel_a = out[str(a_id)][str(x_id)]
        rel_c = out[str(c_id)][str(x_id)]
        metrics_a = rel_a.get("metrics") or {}
        dist_a = rel_a.get("distance") or (metrics_a.get("distance") if isinstance(metrics_a, dict) else None)
        rows_out.append({
            "id": str(x_id),
            "type": x.get("type") or x.get("category") or "",
            "status": x.get("status") or "",
            "dir_from_a": _rel_dir(rel_a),
            "dir_from_c": _rel_dir(rel_c),
            "actual_dist": dist_a,
            "distance": dist_a,
            "tx": tx,
            "ty": ty,
        })
    return rows_out


def graph_directed_refs_for_candidates(graph_index: Dict[str, Any], candidate_ids: List[str]) -> List[Dict[str, Any]]:
    candidate_set = set(str(x) for x in candidate_ids)
    if not candidate_set:
        return []
    objects = graph_index.get("objects", {})
    out = graph_index.get("out", {})
    ref_map: Dict[str, Dict[str, Any]] = {}
    for ref_id in sorted(out):
        rels = out[ref_id]
        hits = candidate_set & set(rels)
        if not hits:
            continue
        ref_obj = objects.get(ref_id, {})
        tx, ty = object_xy(ref_obj)
        ref = ref_map.setdefault(ref_id, {"id": ref_id, "unique_id": ref_id, "type": ref_obj.get("type") or ref_obj.get("category") or "", "status": ref_obj.get("status") or "", "tx": tx, "ty": ty, "dir_to": {}})
        for cand_id in sorted(hits):
            ref["dir_to"][cand_id] = _rel_dir(rels[cand_id])
    return [ref_map[key] for key in sorted(ref_map)]


def graph_pivot_neighbors(graph_index: Dict[str, Any], pivot_id: str) -> List[Dict[str, Any]]:
    objects = graph_index.get("objects", {})
    out = graph_index.get("out", {}).get(pivot_id, {})
    rows: List[Dict[str, Any]] = []
    for obj_id in sorted(out):
        rel = out[obj_id]
        obj = objects.get(obj_id, {})
        tx, ty = object_xy(obj)
        metrics = rel.get("metrics") or {}
        dist = rel.get("distance") or (metrics.get("distance") if isinstance(metrics, dict) else None)
        rows.append({
            "id": obj_id,
            "unique_id": obj_id,
            "type": obj.get("type") or obj.get("category") or "",
            "status": obj.get("status") or "",
            "dir_official": _rel_dir(rel),
            "actual_dist": dist,
            "tx": tx,
            "ty": ty,
        })
    return rows



def query_hash(cypher: str, params: Dict[str, Any]) -> str:
    payload = json.dumps({"cypher": cypher, "params": params}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def run_verify_query(session, qa: Dict[str, Any], cypher: str, params: Dict[str, Any], *, branch_index: int | None = None) -> List[Dict[str, Any]]:
    qh = query_hash(cypher, params)
    family = qa.get("l2_family", "")
    gap = qa.get("path_pattern", "")
    label = f"family={family} gap={gap} query_hash={qh}"
    if branch_index is not None:
        label += f" branch={branch_index}"
    trace = os.environ.get("ADVTEST_VERIFY_TRACE", "").strip().lower() in {"1", "true", "yes", "on"}
    if trace:
        print(f"[v7][verify] START {label} params={json.dumps(params, ensure_ascii=False, sort_keys=True)}", flush=True)
    start = time.perf_counter()
    try:
        result = [dict(r) for r in session.run(cypher, **params)]
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        qa.setdefault("verify_audit", []).append({"query_hash": qh, "branch_index": branch_index, "elapsed_ms": elapsed_ms, "status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
        print(f"[v7][verify] ERROR {label} elapsed_ms={elapsed_ms} error={type(exc).__name__}: {exc}", flush=True)
        raise
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    qa.setdefault("verify_audit", []).append({"query_hash": qh, "branch_index": branch_index, "elapsed_ms": elapsed_ms, "status": "OK", "row_count": len(result)})
    qa["verify_elapsed_ms"] = int(sum(item.get("elapsed_ms", 0) for item in qa.get("verify_audit", [])))
    slow_ms = int(os.environ.get("ADVTEST_VERIFY_SLOW_LOG_MS") or 1000)
    if trace or elapsed_ms >= slow_ms:
        slow_ms = int(os.environ.get("ADVTEST_VERIFY_SLOW_MS") or 1000)
    if trace or elapsed_ms >= slow_ms:
        print(f"[v7][verify] DONE {label} elapsed_ms={elapsed_ms} rows={len(result)}", flush=True)
    return result


def _fast_pre_verify(graph_index: Dict[str, Any], data, plan) -> bool:
    """Lightweight pre-verify working directly on DryRunInput/DryRunPlan.
    Skips building the full QA record (no Cypher, no constraint metadata).
    """
    from gap_pipeline.l2_taxonomy import L2Family

    objects = graph_index.get("objects", {})
    out = graph_index.get("out", {})

    def _edir(src: str, dst: str):
        rel = out.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("direction_6") or rel.get("direction_official")
        if d:
            return str(d)
        angle = rel.get("angle")
        if angle is not None:
            try:
                a = float(angle)
                if -30 < a <= 30: return "front"
                if 30 < a <= 90: return "front_left"
                if -90 < a <= -30: return "front_right"
                if 90 < a <= 150: return "back_left"
                if -150 < a <= -90: return "back_right"
                return "back"
            except (ValueError, TypeError):
                pass
        return None

    def _edist(src: str, dst: str):
        rel = out.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("distance")
        if d is not None:
            try: return float(d)
            except (ValueError, TypeError): pass
        m = rel.get("metrics")
        if isinstance(m, dict) and m.get("distance") is not None:
            try: return float(m["distance"])
            except (ValueError, TypeError): pass
        return None

    fam = plan.family

    if fam == L2Family.VIEWPOINT_TRANSFER:
        return True

    if fam == L2Family.DIRECTION_CHAIN:
        return _edir(data.gap.a_id, data.gap.b_id) is not None and _edir(data.gap.b_id, data.gap.c_id) is not None

    if fam == L2Family.DISTANCE_CHAIN:
        d1 = _edist(data.gap.a_id, data.gap.b_id)
        d2 = _edist(data.gap.b_id, data.gap.c_id)
        return d1 is not None and d2 is not None and d1 != d2

    def _unique_match(src, dir_from, ttype, expect, src2=None, dir2=None, clauses=None):
        cands = set()
        for dst in out.get(src, {}):
            obj = objects.get(dst, {})
            if obj.get("type") != ttype:
                continue
            if _edir(src, dst) != dir_from:
                continue
            cands.add(dst)
        if not cands:
            return False
        if src2 and dir2:
            cands = {x for x in cands if _edir(src2, x) == dir2}
            if not cands:
                return False
        if clauses:
            for c in clauses:
                rid = c.get("ref_id") if isinstance(c, dict) else getattr(c, "ref_id", None)
                rval = c.get("value") if isinstance(c, dict) else getattr(c, "value", None)
                if rid and rval:
                    cands = {x for x in cands if _edir(rid, x) == rval}
                    if not cands:
                        return False
        return len(cands) == 1 and (not expect or next(iter(cands)) == expect)

    if fam == L2Family.CONVERGE:
        d1 = data.a_to_b_dir or ""
        d2 = data.c_to_b_dir or ""
        if not d1 or not d2:
            return True
        return _unique_match(data.gap.a_id, d1, data.gap.b_type, data.gap.b_id,
                             src2=data.gap.c_id, dir2=d2, clauses=plan.clauses)

    if fam == L2Family.DIVERGE_COMPARE:
        d1 = data.b_to_a_dir or ""
        d2 = data.b_to_c_dir or ""
        if not d1 or not d2:
            return True
        dbg = plan.debug or {}
        ac = dbg.get("a", {}).get("clauses", []) if isinstance(dbg, dict) else []
        cc = dbg.get("c", {}).get("clauses", []) if isinstance(dbg, dict) else []
        if not _unique_match(data.gap.b_id, d1, data.gap.a_type, data.gap.a_id, clauses=ac):
            return False
        return _unique_match(data.gap.b_id, d2, data.gap.c_type, data.gap.c_id, clauses=cc)

    return True


def pre_verify_graph_index(graph_index: Dict[str, Any], qa: Dict[str, Any]) -> bool:
    """Fast in-memory pre-verification using graph_index.

    Replicates the core checks of the Cypher verify queries:
    - converge: direction constraints from A/C/refs to X, type match, unique result
    - diverge_compare: direction constraints for both branches, unique result each
    - distance_chain: d(A,B) != d(B,C) and both exist
    - direction_chain: dir(A,B) and dir(B,C) both exist
    - viewpoint_transfer: always passes

    Returns True if the plan is likely valid (should proceed to Neo4j verify),
    False if it will definitely fail (skip Neo4j query).
    """
    family = qa.get("l2_family", "")
    vp = qa.get("verify_payload") or {}
    objects = graph_index.get("objects", {})
    out = graph_index.get("out", {})

    def _edge_dir(src: str, dst: str) -> str | None:
        """Get direction_6 from src→dst edge in graph_index."""
        rel = out.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("direction_6") or rel.get("direction_official")
        if d:
            return str(d)
        # Fallback: compute from angle (same logic as Cypher CASE)
        angle = rel.get("angle")
        if angle is not None:
            try:
                a = float(angle)
                if -30 < a <= 30: return "front"
                if 30 < a <= 90: return "front_left"
                if -90 < a <= -30: return "front_right"
                if 90 < a <= 150: return "back_left"
                if -150 < a <= -90: return "back_right"
                return "back"
            except (ValueError, TypeError):
                pass
        return None

    def _edge_dist(src: str, dst: str) -> float | None:
        """Get distance from src→dst edge in graph_index."""
        rel = out.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("distance")
        if d is not None:
            try:
                return float(d)
            except (ValueError, TypeError):
                pass
        metrics = rel.get("metrics")
        if isinstance(metrics, dict) and metrics.get("distance") is not None:
            try:
                return float(metrics["distance"])
            except (ValueError, TypeError):
                pass
        return None

    def _check_converge_branch(params: Dict[str, Any], expected_id: str | None = None) -> bool:
        """Check converge/diverge branch: find all X matching type+direction constraints.
        Returns True only if exactly 1 X matches AND it is the expected target.
        """
        # Identify the source node (a_id or b_id) and required directions
        src_a = params.get("a_id") or params.get("b_id")
        target_type = params.get("target_type") or params.get("branch_type")
        dir_from_src = params.get("dir_from_a") or params.get("branch_dir")
        src_c = params.get("c_id")  # only for converge
        dir_from_c = params.get("dir_from_c")

        if not src_a or not target_type:
            return True  # Can't pre-verify, let Neo4j handle

        # Find all X that src_a points to
        candidates = set()
        for dst, rel in out.get(src_a, {}).items():
            obj = objects.get(dst, {})
            if obj.get("type") != target_type:
                continue
            d = _edge_dir(src_a, dst)
            if d != dir_from_src:
                continue
            candidates.add(dst)

        if not candidates:
            return False

        # If converge: also filter by C→X direction
        if src_c and dir_from_c:
            candidates = {x for x in candidates if _edge_dir(src_c, x) == dir_from_c}
            if not candidates:
                return False

        # Check ref constraints
        for i in range(1, 4):
            ref_id = params.get(f"ref_id_{i}")
            ref_dir = params.get(f"ref_dir_{i}")
            if ref_id and ref_dir:
                candidates = {x for x in candidates if _edge_dir(ref_id, x) == ref_dir}
                if not candidates:
                    return False

        # Must be exactly 1 match, and it must be the expected target
        if len(candidates) != 1:
            return False
        if expected_id and next(iter(candidates)) != expected_id:
            return False
        return True

    # Extract expected A, B, C from path_pattern "A|B|C"
    pp = str(qa.get("path_pattern") or "")
    pp_parts = pp.split("|") if "|" in pp else []
    expected_a = pp_parts[0] if len(pp_parts) >= 3 else None
    expected_b = pp_parts[1] if len(pp_parts) >= 3 else None
    expected_c = pp_parts[2] if len(pp_parts) >= 3 else None

    if family == "viewpoint_transfer":
        return True

    if family == "converge":
        params = vp.get("params", {})
        return _check_converge_branch(params, expected_id=expected_b)

    if family == "diverge_compare":
        branches = vp.get("branches", [])
        expected_ids = [expected_a, expected_c]
        for i, b in enumerate(branches):
            eid = expected_ids[i] if i < len(expected_ids) else None
            if not _check_converge_branch(b.get("params", {}), expected_id=eid):
                return False
        return True

    if family == "distance_chain":
        params = vp.get("params", {})
        a_id, b_id, c_id = params.get("a_id"), params.get("b_id"), params.get("c_id")
        if not all([a_id, b_id, c_id]):
            return True
        d_ab = _edge_dist(a_id, b_id)
        d_bc = _edge_dist(b_id, c_id)
        if d_ab is None or d_bc is None:
            return False
        return d_ab != d_bc

    if family == "direction_chain":
        params = vp.get("params", {})
        a_id, b_id, c_id = params.get("a_id"), params.get("b_id"), params.get("c_id")
        if not all([a_id, b_id, c_id]):
            return True
        dir_ab = _edge_dir(a_id, b_id)
        dir_bc = _edge_dir(b_id, c_id)
        return dir_ab is not None and dir_bc is not None

    return True  # Unknown family → pass through


def execute_verify(session, qa: Dict[str, Any]) -> Dict[str, Any]:
    payload = qa.get("verify_payload") or {}
    if payload.get("branches"):
        outs = []
        for idx, b in enumerate(payload["branches"]):
            outs.append(run_verify_query(session, qa, b["cypher"], b.get("params", {}), branch_index=idx))
        qa["verify_result"] = outs
        qa["logic_verification"] = "NEO4J_EXECUTED"
    elif payload.get("cypher"):
        qa["verify_result"] = run_verify_query(session, qa, payload["cypher"], payload.get("params", {}))
        qa["logic_verification"] = "NEO4J_EXECUTED"
    else:
        qa["logic_verification"] = "NEO4J_EXECUTED"
    if qa.get("l2_family") == "viewpoint_transfer":
        qa["verify_result"] = [{"viewpoint_transfer": True}]
        qa["logic_verification"] = "NEO4J_EXECUTED"
    return qa


def _memory_verify(graph_index: Dict[str, Any], qa: Dict[str, Any]) -> Dict[str, Any]:
    """In-memory verification equivalent to execute_verify + Neo4j.

    Produces the same verify_result structure that verify_valid() expects,
    using graph_index data instead of Neo4j queries. Quality is identical.
    """
    objects = graph_index.get("objects", {})
    out_edges = graph_index.get("out", {})

    def _edir(src: str, dst: str):
        rel = out_edges.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("direction_6") or rel.get("direction_official")
        if d:
            return str(d)
        angle = rel.get("angle")
        if angle is not None:
            try:
                a = float(angle)
                if -30 < a <= 30: return "front"
                if 30 < a <= 90: return "front_left"
                if -90 < a <= -30: return "front_right"
                if 90 < a <= 150: return "back_left"
                if -150 < a <= -90: return "back_right"
                return "back"
            except (ValueError, TypeError):
                pass
        return None

    def _edist(src: str, dst: str):
        rel = out_edges.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("distance")
        if d is not None:
            try: return float(d)
            except (ValueError, TypeError): pass
        return None

    family = qa.get("l2_family", "")
    pp = str(qa.get("path_pattern") or "")
    pp_parts = pp.split("|") if "|" in pp else []
    a_id = pp_parts[0] if len(pp_parts) >= 3 else ""
    b_id = pp_parts[1] if len(pp_parts) >= 3 else ""
    c_id = pp_parts[2] if len(pp_parts) >= 3 else ""

    if family == "viewpoint_transfer":
        qa["verify_result"] = [{"viewpoint_transfer": True}]
        qa["logic_verification"] = "IN_MEMORY_VERIFIED"
        return qa

    if family == "direction_chain":
        dir_ab = _edir(a_id, b_id)
        dir_bc = _edir(b_id, c_id)
        qa["verify_result"] = [{"dir_ab": dir_ab, "dir_bc": dir_bc}]
        qa["logic_verification"] = "IN_MEMORY_VERIFIED"
        return qa

    if family == "distance_chain":
        d_ab = _edist(a_id, b_id)
        d_bc = _edist(b_id, c_id)
        qa["verify_result"] = [{"d_ab": d_ab, "d_bc": d_bc}]
        qa["logic_verification"] = "IN_MEMORY_VERIFIED"
        return qa

    def _find_matching(src: str, dir_from: str, target_type: str, extra_clauses=None):
        """Find objects reachable from src in direction dir_from with given type."""
        matches = set()
        for dst, rel in out_edges.get(src, {}).items():
            obj = objects.get(dst, {})
            if obj.get("type") != target_type:
                continue
            if _edir(src, dst) != dir_from:
                continue
            matches.add(dst)
        # Apply extra ref_dir clauses
        if extra_clauses:
            for clause in extra_clauses:
                if not isinstance(clause, dict):
                    continue
                ref_id = str(clause.get("ref_id") or "")
                value = str(clause.get("value") or "")
                kind = str(clause.get("kind") or "")
                if kind == "ref_dir" and ref_id and value:
                    matches = {m for m in matches if _edir(ref_id, m) == value}
        return sorted(matches)

    if family == "converge":
        # Parse verify_payload params for directions and type
        vp = qa.get("verify_payload") or {}
        params = vp.get("params", {})
        target_type = params.get("target_type") or (objects.get(b_id, {}).get("type", ""))
        dir_from_a = params.get("dir_from_a") or _edir(a_id, b_id) or ""
        dir_from_c = params.get("dir_from_c") or _edir(c_id, b_id) or ""

        # Find candidates from A side
        from_a = set()
        for dst in out_edges.get(a_id, {}):
            obj = objects.get(dst, {})
            if obj.get("type") == target_type and _edir(a_id, dst) == dir_from_a:
                from_a.add(dst)
        # Intersect with C side
        from_c = set()
        for dst in out_edges.get(c_id, {}):
            obj = objects.get(dst, {})
            if obj.get("type") == target_type and _edir(c_id, dst) == dir_from_c:
                from_c.add(dst)
        matches = from_a & from_c

        # Apply ref_dir constraints from verify_payload params (ref_id_1/ref_dir_1, etc.)
        for i in range(1, 10):
            ref_id = params.get(f"ref_id_{i}")
            ref_dir = params.get(f"ref_dir_{i}")
            if ref_id and ref_dir:
                matches = {m for m in matches if _edir(ref_id, m) == ref_dir}
            else:
                break

        ids = sorted(matches)
        qa["verify_result"] = [{"n": len(ids), "ids": ids}]
        qa["logic_verification"] = "IN_MEMORY_VERIFIED"
        return qa

    if family == "diverge_compare":
        vp = qa.get("verify_payload") or {}
        branches = vp.get("branches", [])
        branch_results = []
        for br in branches:
            params = br.get("params", {}) if isinstance(br, dict) else {}
            pivot = params.get("b_id", b_id)
            branch_type = params.get("branch_type", "")
            branch_dir = params.get("branch_dir", "")
            # Find matching
            matches = set()
            for dst in out_edges.get(pivot, {}):
                obj = objects.get(dst, {})
                if obj.get("type") == branch_type and _edir(pivot, dst) == branch_dir:
                    matches.add(dst)
            # Apply ref constraints from params
            for key, val in params.items():
                if key.startswith("ref_dir_"):
                    idx = key.split("_")[-1]
                    ref_id = params.get(f"ref_id_{idx}", "")
                    if ref_id and val:
                        matches = {m for m in matches if _edir(ref_id, m) == val}
            ids = sorted(matches)
            branch_results.append([{"n": len(ids), "ids": ids}])
        qa["verify_result"] = branch_results
        qa["logic_verification"] = "IN_MEMORY_VERIFIED"
        return qa

    # Fallback: no verify needed
    qa["logic_verification"] = "IN_MEMORY_VERIFIED"
    return qa


def directed_refs_for_candidates(session, candidate_ids: List[str]) -> List[Dict[str, Any]]:
    if not candidate_ids:
        return []
    ref_map: Dict[str, Dict[str, Any]] = {}
    q = fetch_candidate_ref_directions(candidate_ids)
    for r in rows(session, q):
        rid = str(r.get("ref_id"))
        ref = ref_map.setdefault(
            rid,
            {
                "id": rid,
                "unique_id": rid,
                "type": r.get("ref_type"),
                "status": r.get("ref_status") or "",
                "tx": r.get("ref_tx"),
                "ty": r.get("ref_ty"),
                "dir_to": {},
            },
        )
        ref["dir_to"][str(r.get("cand_id"))] = r.get("dir_official")
    return list(ref_map.values())


FORMAL_FAMILY_RATIO = {
    "converge": 0.40,
    "diverge_compare": 0.35,
    "direction_chain": 0.08,
    "distance_chain": 0.08,
    "viewpoint_transfer": 0.09,
}

# Minimum quota: each family must have at least this share
FORMAL_FAMILY_MIN_RATIO = {
    "converge": 0.15,
    "diverge_compare": 0.15,
    "direction_chain": 0.04,
    "distance_chain": 0.04,
    "viewpoint_transfer": 0.03,
}

FORMAL_PRIMARY_FAMILIES = {"converge", "diverge_compare"}

FORMAL_FAMILY_PRIORITY_WEIGHT = {
    "converge": 1000.0,
    "diverge_compare": 1000.0,
    "direction_chain": 1000.0,
    "distance_chain": 1000.0,
    "viewpoint_transfer": 1000.0,
}

FORMAL_REDISTRIBUTION_ORDER = [
    "converge",
    "diverge_compare",
    "direction_chain",
    "distance_chain",
    "viewpoint_transfer",
]


def compute_family_targets(total_gaps: int, availability: Dict[str, int]) -> Dict[str, int]:
    raw = {fam: int(total_gaps * ratio) for fam, ratio in FORMAL_FAMILY_RATIO.items()}
    remainder = total_gaps - sum(raw.values())
    for fam in FORMAL_REDISTRIBUTION_ORDER:
        if remainder <= 0:
            break
        raw[fam] = raw.get(fam, 0) + 1
        remainder -= 1
    targets = {fam: min(raw.get(fam, 0), availability.get(fam, 0)) for fam in FORMAL_FAMILY_RATIO}
    spare = total_gaps - sum(targets.values())
    while spare > 0:
        changed = False
        for fam in FORMAL_REDISTRIBUTION_ORDER:
            if spare <= 0:
                break
            cap = availability.get(fam, 0) - targets.get(fam, 0)
            if cap <= 0:
                continue
            targets[fam] = targets.get(fam, 0) + 1
            spare -= 1
            changed = True
        if not changed:
            break
    return targets


def compute_strict_family_targets(total_gaps: int, availability: Dict[str, int]) -> Dict[str, int]:
    targets: Dict[str, int] = {}
    for fam, ratio in FORMAL_FAMILY_RATIO.items():
        desired = int(total_gaps * ratio)
        cap = int(total_gaps * FORMAL_FAMILY_MAX_RATIO.get(fam, ratio))
        targets[fam] = min(desired, cap, availability.get(fam, 0))
    return targets



FORMAL_FAMILY_MAX_RATIO = {
    "converge": 0.50,
    "diverge_compare": 0.50,
    "direction_chain": 0.20,
    "distance_chain": 0.20,
    "viewpoint_transfer": 0.15,
}

AUXILIARY_FAMILIES = {"direction_chain", "distance_chain", "viewpoint_transfer"}
AUXILIARY_MAX_RATIO = float(os.environ.get("ADVTEST_AUXILIARY_MAX_RATIO") or 0.25)

# ── M3: Phase 1→2 switch — dynamic plateau detection ──
#    Phase 1 (greedy converge+diverge) switches to Phase 2 (balanced 4-slot)
#    when delta_l2 stays at 1 for a sustained window of consecutive questions.
#    Window size = max(FLOOR, int(total_gaps × RATIO)):
#      - RATIO: proportion of total gaps (default 2%) — scales with pool size
#      - FLOOR: minimum window (default 20) — prevents premature switch on small pools
#    Example: 6000 gaps → window=120, 500 gaps → window=20
PHASE1_PLATEAU_RATIO = float(os.environ.get("ADVTEST_PHASE1_PLATEAU_RATIO") or 0.02)
PHASE1_PLATEAU_FLOOR = int(os.environ.get("ADVTEST_PHASE1_PLATEAU_FLOOR") or 20)

# Phase 2: 4-slot balanced generation.  Each slot maps to family preference order.
# Slot A: converge + diverge (prefer diverge first, fallback converge)
# Slot B: direction_chain
# Slot C: distance_chain
# Slot D: viewpoint_transfer
PHASE2_SLOTS = {
    "A": ["diverge_compare", "converge"],
    "B": ["direction_chain"],
    "C": ["distance_chain"],
    "D": ["viewpoint_transfer"],
}
# All families that appear in any slot (for quick membership test)
PHASE2_ALL_FAMILIES = {fam for families in PHASE2_SLOTS.values() for fam in families}


def coverage_gain(footprint: Dict[str, List[str]], state: L2CoverageState) -> Dict[str, int]:
    l0 = sum(1 for x in footprint.get("l0", []) if x not in state.l0)
    l1 = sum(1 for x in footprint.get("l1", []) if x not in state.l1)
    l2 = sum(1 for x in footprint.get("l2", []) if x not in state.l2)
    return {"l0": l0, "l1": l1, "l2": l2, "total": l0 + l1 + l2}


def family_cap_blocked(family: str, used_counts: Dict[str, int], generated_count: int) -> bool:
    cap = FORMAL_FAMILY_MAX_RATIO.get(family)
    if cap is None:
        return False
    after_total = max(generated_count + 1, 1)
    return (used_counts.get(family, 0) + 1) / after_total > cap


def plan_attempt_key(gap_key: str, plan: Any) -> str:
    payload = {
        "gap_key": gap_key,
        "family": plan.family.value,
        "footprint": plan.footprint or {},
        "answer": getattr(plan, "answer", ""),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def stable_random_plan_key(gap_key: str, plan: Any) -> str:
    """Content-derived plan identity used by resumable random sampling."""
    question = getattr(plan, "question", None)
    payload = {
        "gap_key": gap_key,
        "family": plan.family.value,
        "answer": getattr(plan, "answer", None),
        "clauses": [
            {
                "kind": getattr(clause, "kind", ""),
                "value": getattr(clause, "value", ""),
                "ref_id": getattr(clause, "ref_id", ""),
                "text_hint": getattr(clause, "text_hint", ""),
            }
            for clause in getattr(plan, "clauses", [])
        ],
        "footprint": {
            level: sorted(str(value) for value in values)
            for level, values in (getattr(plan, "footprint", {}) or {}).items()
        },
        "question": {
            "answer_type": getattr(question, "answer_type", ""),
            "template_family": getattr(question, "template_family", ""),
        },
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def classify_verify_failure(qa: Dict[str, Any]) -> str:
    result = qa.get("verify_result")
    family = qa.get("l2_family", "unknown")
    if not result:
        return "empty_result"
    try:
        if family == "converge":
            n = result[0].get("n")
            if n == 0:
                return "n_zero"
            if isinstance(n, int) and n > 1:
                return "n_multi"
            return f"n_{n}"
        if family == "diverge_compare":
            n = result[0].get("n")
            if n == 0:
                return "n_zero"
            if isinstance(n, int) and n > 1:
                return "n_multi"
            return f"n_{n}"
        if family in {"distance_chain", "direction_chain"}:
            return "rows_lt_1" if len(result) < 1 else "invalid_rows"
    except Exception as exc:
        return f"classify_error_{type(exc).__name__}"
    return "invalid"



def choose_formal_plan(plans, used_counts: Dict[str, int], targets: Dict[str, int], rng: random.Random):
    weighted = []
    for plan in plans:
        fam = plan.family.value
        deficit = max(targets.get(fam, 0) - used_counts.get(fam, 0), 0)
        weight = deficit * FORMAL_FAMILY_PRIORITY_WEIGHT.get(fam, 1.0)
        if weight > 0:
            weighted.append((plan, weight))
    if weighted:
        total = sum(w for _, w in weighted)
        pick = rng.random() * total
        acc = 0.0
        for plan, weight in weighted:
            acc += weight
            if pick <= acc:
                return plan
    return min(plans, key=lambda p: (used_counts.get(p.family.value, 0) - targets.get(p.family.value, 0), -p.score))


def verify_valid(qa: Dict[str, Any]) -> bool:
    result = qa.get("verify_result")
    family = qa.get("l2_family")
    # Extract expected A, B, C from path_pattern "A|B|C"
    pp = str(qa.get("path_pattern") or "")
    pp_parts = pp.split("|") if "|" in pp else []
    expected_a = pp_parts[0] if len(pp_parts) >= 3 else None
    expected_b = pp_parts[1] if len(pp_parts) >= 3 else None
    expected_c = pp_parts[2] if len(pp_parts) >= 3 else None

    if family == "converge":
        if not result or result[0].get("n") != 1 or not result[0].get("ids"):
            return False
        found_id = str(result[0]["ids"][0])
        # Must find exactly the expected B node
        if expected_b and found_id != expected_b:
            return False
        return True
    if family == "diverge_compare":
        # Branches verify: both A-side and C-side must be uniquely resolved
        if not result or not isinstance(result, list) or len(result) < 2:
            return False
        a_ok = isinstance(result[0], list) and len(result[0]) > 0 and result[0][0].get("n") == 1
        c_ok = isinstance(result[1], list) and len(result[1]) > 0 and result[1][0].get("n") == 1
        if not (a_ok and c_ok):
            return False
        # Must find exactly the expected A and C nodes
        found_a = str(result[0][0]["ids"][0]) if result[0][0].get("ids") else None
        found_c = str(result[1][0]["ids"][0]) if result[1][0].get("ids") else None
        if expected_a and found_a and found_a != expected_a:
            return False
        if expected_c and found_c and found_c != expected_c:
            return False
        return True
    if family == "distance_chain":
        if not result:
            return False
        row = result[0]
        return row.get("d_ab") is not None and row.get("d_bc") is not None and row.get("d_ab") != row.get("d_bc")
    if family == "direction_chain":
        if not result:
            return False
        row = result[0]
        return row.get("dir_ab") is not None and row.get("dir_bc") is not None
    if family == "viewpoint_transfer":
        return qa.get("answer") in {"left", "right"}
    return bool(result)


def build_summary(records: List[Dict[str, Any]], coverage: L2CoverageState, *, tried: int, pool_size: int, pool_source: str = "", started_at: str = "", ended_at: str = "", elapsed_ms: int = 0, family_policy: Dict[str, Any] | None = None, universe_stats: Dict[str, Any] | None = None) -> Dict[str, Any]:
    families = collections.Counter(r.get("template_id") for r in records)
    verify = collections.Counter(r.get("logic_verification") for r in records)
    return {
        "timestamp_start": started_at,
        "timestamp_end": ended_at,
        "elapsed_ms": elapsed_ms,

        "generated": len(records),
        "total_gap_count": pool_size,
        "covered_gap_count": len(coverage.l2),
        "uncovered_gap_count": max(pool_size - len(coverage.l2), 0),
        "failed_candidate_count": max(tried - len(records), 0),
        "tried_candidate_count": tried,
        "pool_source": pool_source,
        "universe_stats": universe_stats or {},

        "pool_size": pool_size,
        "families": dict(families),
        "family_policy": family_policy or {},
        "verification": dict(verify),
        "coverage": {
            "l0": len(coverage.l0),
            "l1": len(coverage.l1),
            "l2": len(coverage.l2),
        },
    }


def write_summary(output: Path | None, summary: Dict[str, Any]) -> None:
    if output is None:
        print(json.dumps({"summary": summary}, ensure_ascii=False, indent=2))
        return
    path = output if output.name.endswith("summary.json") else output.with_suffix(output.suffix + ".summary.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")



def make_neo4j_session() -> BoltNeo4jSession:
    advtest_env.load_advtest_env()
    bolt_uri = os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return BoltNeo4jSession(bolt_uri, user, password)



def update_plan_status(artifact_root: Path, scene_id: str, frame_id: str, plan_name: str, status: str) -> None:
    frame_dir = V7ArtifactPaths(artifact_root, scene_id=scene_id, frame_id=frame_id).frame_dir
    path = frame_dir / "plan_status.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"schema": "v7_plan_status", "scene_id": scene_id, "frame_id": frame_id, "plans": {}}
    payload["plans"][plan_name] = status
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")



def compact_scene_context(path: Path, max_edges: int = 120) -> str:
    if not path.exists():
        return ""
    payload = json.loads(path.read_text(encoding="utf-8"))
    max_edges = int(os.environ.get("LLM_SCENE_CONTEXT_MAX_EDGES") or max_edges)

    nodes = payload.get("nodes") or payload.get("objects") or []
    edges = payload.get("edges") or payload.get("relationships") or []
    node_lines = []
    for n in nodes:
        uid = n.get("unique_id") or n.get("id")
        typ = str(n.get("type") or "object")
        category = str(n.get("category") or "")
        aliases = []
        if "trafficcone" in category.replace("_", "").replace(".", "").lower():
            aliases.extend(["traffic_cone", "traffic cone"])
        if typ == "barrier":
            aliases.append("barrier")
        if typ == "car" or "vehicle.car" in category:
            aliases.append("car")
        alias_text = f" aliases=[{', '.join(dict.fromkeys(aliases))}]" if aliases else ""
        desc = [f"id={uid}", f"type={typ}"]
        if category:
            desc.append(f"category={category}")
        if alias_text:
            desc.append(alias_text.strip())
        for key in ("status", "attribute", "pose", "motion", "visibility"):
            if n.get(key):
                desc.append(f"{key}={n.get(key)}")
        node_lines.append(" ".join(desc))
    edge_lines = []
    for e in edges[:max_edges]:
        src = e.get("source") or e.get("from") or e.get("source_id")
        tgt = e.get("target") or e.get("to") or e.get("target_id")
        rel = e.get("relation") or e.get("type") or e.get("spatial_relation") or e.get("description") or e.get("direction_6") or e.get("direction_official") or ",".join(e.get("predicates") or []) or "related_to"
        if src and tgt:
            edge_lines.append(f"{src} -[{rel}]-> {tgt}")
    return "nodes:\n" + "\n".join(node_lines) + "\nedges:\n" + "\n".join(edge_lines)


def llm_ping(client: LLMClient) -> None:
    log_stage(f"LLM ping start model={client.model} base={client.api_base}")
    try:
        client._post_json("/chat/completions", {
            "model": client.model,
            "messages": [{"role": "user", "content": "Reply OK only."}],
            "temperature": 0,
            "max_tokens": 4,
        })
    except Exception as exc:
        raise RuntimeError(
            f"LLM ping failed before offline coverage. Check API base/key/model/network. "
            f"base={client.api_base} model={client.model} error={exc}"
        ) from exc
    log_stage("LLM ping DONE")





def plan_prepare_scene_graph(artifact_root: Path, *, scene_id: str, frame_id: str, gap_limit: int, scene_graph_source: Path | None = None) -> Dict[str, Any]:
    log_stage(f"prepare_scene_graph start scene={scene_id} frame={frame_id}")
    artifacts = V7ArtifactPaths(artifact_root, scene_id=scene_id, frame_id=frame_id)
    if scene_graph_source:
        graph = copy_offline_scene_graph(scene_graph_source, artifacts.filtered_scene_graph, scene_id=scene_id, frame_id=frame_id)
    else:
        graph = export_filtered_scene_graph(make_neo4j_session(), artifacts.filtered_scene_graph, limit_objects=gap_limit)
    update_plan_status(artifact_root, scene_id, frame_id, "prepare_scene_graph", "DONE")
    write_manifest(artifacts, summary={"filtered_scene_graph": graph})
    counts = scene_graph_counts(artifacts.filtered_scene_graph)
    log_stage(f"scene_graph stats raw_nodes={counts['raw_nodes']} raw_edges={counts['raw_edges']} filtered_nodes={counts['filtered_nodes']} filtered_edges={counts['filtered_edges']}")

    log_stage(f"prepare_scene_graph DONE output={artifacts.filtered_scene_graph}")

    return graph




def log_stage(message: str) -> None:
    print(f"[v7][offline] {message}", flush=True)

def plan_prepare_initial_coverage(artifact_root: Path, *, scene_id: str, frame_id: str, initial_qa: List[Path], use_llm: bool = False, concurrency: int = 1) -> Dict[str, Any]:
    log_stage(f"prepare_initial_coverage start files={len(initial_qa)} use_llm={use_llm}")

    artifacts = V7ArtifactPaths(artifact_root, scene_id=scene_id, frame_id=frame_id)
    coverage_mode = (os.environ.get("ADVTEST_INITIAL_COVERAGE_MODE") or os.environ.get("LLM_INITIAL_COVERAGE_MODE") or "cypher").strip().lower()
    needs_neo4j = use_llm and coverage_mode != "footprint"
    if needs_neo4j:
        log_stage(f"import Neo4j scene graph start input={artifacts.filtered_scene_graph}")
        import_scene_graph_bolt(artifacts.filtered_scene_graph)
        log_stage("import Neo4j scene graph DONE")
    llm_client = LLMClient.from_env() if use_llm and initial_qa else None
    if llm_client and coverage_mode != "footprint":
        llm_ping(llm_client)
    object_ids = object_ids_from_scene_graph(artifacts.filtered_scene_graph) if use_llm else None
    scene_context = compact_scene_context(artifacts.filtered_scene_graph) if use_llm else ""
    if use_llm:
        log_stage(f"coverage scene_context chars={len(scene_context)} object_ids={len(object_ids or [])}")
    summary = export_initial_coverage(initial_qa, artifacts.initial_coverage_file, artifacts.coverage_state_file, scene_id=scene_id, frame_id=frame_id, llm_client=llm_client, object_ids=object_ids, scene_context=scene_context, ground_graph_path=artifacts.filtered_scene_graph, concurrency=concurrency) if initial_qa else {"records": 0, "coverage": {"l0": 0, "l1": 0, "l2": 0}}
    summary["method"] = "llm" if use_llm and initial_qa else "replay"
    if summary.get("records", 0) == 0 and initial_qa:
        log_stage(f"WARNING prepare_initial_coverage matched 0 records for scene={scene_id} frame={frame_id}; check ADVTEST_ORIGINAL_QA and scene/frame ids")

    update_plan_status(artifact_root, scene_id, frame_id, "prepare_initial_coverage", "DONE")
    write_manifest(artifacts, summary={"initial_coverage": summary})
    log_stage(f"prepare_initial_coverage DONE records={summary.get('records', 0)} coverage={summary.get('coverage', {})}")
    return summary



def run_offline_artifacts(
    artifact_root: Path,
    *,
    scene_id: str = "global",
    frame_id: str = "all",
    gap_limit: int = 500,
    initial_qa: List[Path] | None = None,
    scene_graph_source: Path | None = None,
    initial_coverage_llm: bool = False,
    concurrency: int = 1,
) -> Dict[str, Any]:
    artifacts = V7ArtifactPaths(artifact_root, scene_id=scene_id, frame_id=frame_id)
    log_stage(f"full start scene={scene_id} frame={frame_id} initial_qa_files={len(initial_qa or [])}")
    graph = plan_prepare_scene_graph(artifact_root, scene_id=scene_id, frame_id=frame_id, gap_limit=gap_limit, scene_graph_source=scene_graph_source)
    initial_summary = plan_prepare_initial_coverage(artifact_root, scene_id=scene_id, frame_id=frame_id, initial_qa=initial_qa or [], use_llm=initial_coverage_llm, concurrency=concurrency)
    summary = {"filtered_scene_graph": graph.get("meta", {}), "initial_coverage": initial_summary}
    write_manifest(artifacts, summary=summary)
    update_plan_status(artifact_root, scene_id, frame_id, "offline", "DONE")
    log_stage(f"full offline artifacts DONE scene={scene_id} frame={frame_id}")
    return summary


def emit_incremental_coverage_report(qas: List[Dict[str, Any]], summary: Dict[str, Any], *, artifacts: V7ArtifactPaths | None, selected_attempts: Dict[str, Dict[str, Any]] | None = None) -> None:
    """Write per-question incremental coverage contribution for plotting."""
    if not artifacts:
        return
    total_l0 = max(int((summary.get("coverage") or {}).get("l0") or 0), 1)
    total_l1 = max(int((summary.get("coverage") or {}).get("l1") or 0), 1)
    total_l2 = max(int(summary.get("total_gap_count") or (summary.get("coverage") or {}).get("l2") or 0), 1)
    seen_l0: set[str] = set()
    seen_l1: set[str] = set()
    seen_l2: set[str] = set()
    rows: List[Dict[str, Any]] = []
    for idx, qa in enumerate(qas, start=1):
        fp = qa.get("coverage_footprint") or {}
        l0 = {str(x) for x in fp.get("l0", [])}
        l1 = {str(x) for x in fp.get("l1", [])}
        l2 = {str(x) for x in fp.get("l2", [])}
        new_l0 = l0 - seen_l0
        new_l1 = l1 - seen_l1
        new_l2 = l2 - seen_l2
        seen_l0.update(l0)
        seen_l1.update(l1)
        seen_l2.update(l2)
        attempt_key = str(qa.get("plan_attempt_key") or "")
        if selected_attempts is not None and attempt_key:
            selected = selected_attempts.setdefault(attempt_key, {})
            selected["delta_l0"] = len(new_l0)
            selected["delta_l1"] = len(new_l1)
            selected["delta_l2"] = len(new_l2)
        rows.append({
            "order_index": idx,
            "question_id": qa.get("question_id", str(idx)),
            "selection_phase": qa.get("selection_phase", ""),
            "l2_family": qa.get("l2_family", qa.get("template_id", "")),
            "timestamp_start": qa.get("timestamp_start", ""),
            "timestamp_end": qa.get("timestamp_end", ""),
            "generation_elapsed_ms": qa.get("generation_elapsed_ms", 0),
            "question": qa.get("question", ""),
            "raw_l0": len(l0),
            "raw_l1": len(l1),
            "raw_l2": len(l2),
            "delta_l0": len(new_l0),
            "delta_l1": len(new_l1),
            "delta_l2": len(new_l2),
            "cum_l0": len(seen_l0),
            "cum_l1": len(seen_l1),
            "cum_l2": len(seen_l2),
            "coverage_rate_l0": len(seen_l0) / total_l0,
            "coverage_rate_l1": len(seen_l1) / total_l1,
            "coverage_rate_l2": len(seen_l2) / total_l2,
            "new_l0": sorted(new_l0),
            "new_l1": sorted(new_l1),
            "new_l2": sorted(new_l2),
        })
    # Only write CSV (skip JSONL to save disk space)
    csv_path = artifacts.reports_dir / f"{artifacts.frame_key}_incremental_coverage.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # Exclude new_l0/l1/l2 lists from CSV — delta counts are sufficient for plotting
    fieldnames = [k for k in rows[0].keys() if not k.startswith("new_")] if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    summary.setdefault("reports", {})["incremental_coverage_csv"] = str(csv_path)



def emit_candidate_potential_report(plan_cache: Dict[str, Any], selected_attempts: Dict[str, Dict[str, Any]], *, artifacts: V7ArtifactPaths | None) -> None:
    """Write candidate-level raw footprint potential and whether it was selected."""
    if not artifacts:
        return
    rows: List[Dict[str, Any]] = []
    for gap_key, cached in plan_cache.items():
        data, plans = cached
        for rank, plan in enumerate(plans, start=1):
            fp = plan.footprint or {}
            attempt_key = plan_attempt_key(gap_key, plan)
            selected = selected_attempts.get(attempt_key, {})
            rows.append({
                "gap_key": gap_key,
                "a_id": data.gap.a_id,
                "b_id": data.gap.b_id,
                "c_id": data.gap.c_id,
                "family": plan.family.value,
                "plan_rank": rank,
                "raw_l0": len(fp.get("l0", [])),
                "raw_l1": len(fp.get("l1", [])),
                "raw_l2": len(fp.get("l2", [])),
                "answer": getattr(plan, "answer", ""),
                "selected": bool(selected),
                "selected_order": selected.get("order_index", ""),
                "selection_phase": selected.get("selection_phase", ""),
                "selected_delta_l2": selected.get("delta_l2", ""),
                "constraint_types": "|".join(str(x) for x in getattr(plan, "constraint_types", []) or []),
                "debug": json.dumps(getattr(plan, "debug", {}) or {}, ensure_ascii=False, sort_keys=True),
            })
    jsonl_path = artifacts.reports_dir / f"{artifacts.frame_key}_candidate_potential.jsonl"
    write_jsonl(jsonl_path, rows)
    csv_path = artifacts.reports_dir / f"{artifacts.frame_key}_candidate_potential.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)



def run_neo4j(
    output: Path | None = None,
    *,
    seed: int = 0,
    artifact_root: Path | None = None,
    scene_id: str = "global",
    frame_id: str = "all",
    use_llm: bool = False,
    selection_policy: str = "advtest",
    random_run_id: str = "",
    checkpoint_interval: int = 1000,
    max_draws: int | None = None,
) -> List[Dict[str, Any]]:
    artifacts = V7ArtifactPaths(artifact_root, scene_id=scene_id, frame_id=frame_id) if artifact_root else None
    use_neo4j = os.environ.get("ADVTEST_USE_NEO4J", "false").lower() in ("1", "true", "yes")

    if use_neo4j:
        if artifacts and artifacts.filtered_scene_graph.exists():
            log_stage(f"generate import Neo4j scene graph start input={artifacts.filtered_scene_graph}")
            import_scene_graph_bolt(artifacts.filtered_scene_graph)
            log_stage("generate import Neo4j scene graph DONE")
    else:
        log_stage("generate in-memory mode enabled (bypassing Neo4j)")

    initial_coverage_summary: Dict[str, Any] = {}
    if artifacts and artifacts.manifest_file.exists():
        try:
            initial_coverage_summary = (json.loads(artifacts.manifest_file.read_text(encoding="utf-8")).get("summary") or {}).get("initial_coverage") or {}
        except Exception:
            initial_coverage_summary = {}

    session = None
    if use_neo4j:
        session = make_neo4j_session()

    llm_client = LLMClient.from_env() if use_llm else None
    if artifacts and output is None:
        output = artifacts.generated_jsonl

    graph_index = load_graph_index(artifacts.filtered_scene_graph if artifacts else None)

    if use_neo4j and session:
        try:
            neo4j_graph_stats = fetch_neo4j_graph_stats(session)
        except Exception as e:
            log_stage(f"WARNING: Neo4j connection failed ({e}), falling back to in-memory stats.")
            use_neo4j = False
            session.close()
            session = None

    if not use_neo4j or not session:
        neo4j_graph_stats = {
            "object_count": len(graph_index.get("objects", {})),
            "relationship_count": sum(len(targets) for targets in graph_index.get("out", {}).values())
        }

    log_stage(f"generate graph_stats={neo4j_graph_stats}")

    selected_attempts: Dict[str, Dict[str, Any]] = {}



    out: List[Dict[str, Any]] = []
    used_counts: Dict[str, int] = {}
    failed_candidate_detail_counts: Dict[str, Dict[str, int]] = {}
    last_failure_detail: Dict[str, str] = {}
    converge_failure_samples: List[Dict[str, Any]] = []
    max_failure_samples = int(os.environ.get("ADVTEST_CONVERGE_FAILURE_SAMPLES") or 20)


    coverage = L2CoverageState()
    if artifacts and artifacts.coverage_state_file.exists():
        try:
            with artifacts.coverage_state_file.open("r", encoding="utf-8") as f:
                state_data = json.load(f)
            coverage.l0.update(state_data.get("L0", []))
            coverage.l1.update(state_data.get("L1", []))
            coverage.l2.update(state_data.get("L2", []))
            log_stage(f"generate loaded initial coverage L0={len(coverage.l0)} L1={len(coverage.l1)} L2={len(coverage.l2)}")
        except Exception as e:
            log_stage(f"generate WARNING failed to load coverage state file: {e}")
    started_at = utc_now_iso()
    start_dt = datetime.now(timezone.utc)

    backfill_counts: Dict[str, int] = {}

    max_questions = None

    selector = L2GapSelector(rng=random.Random(seed))
    pool_source = "neo4j_full_gap_universe" if use_neo4j else "local_in_memory_gap_universe"
    if use_neo4j and session:
        pool = selector.shuffled(fetch_l2_gaps(session))
    else:
        pool = selector.shuffled(fetch_l2_gaps_in_memory(graph_index))
    tried: set[str] = set()

    # Seed variant RNG for reproducible question wording
    set_variant_seed(seed)

    # Primary family ratio: converge + diverge get 70% selection probability
    primary_ratio = float(os.environ.get("ADVTEST_PRIMARY_RATIO") or 0.70)

    planner = L2ConstraintPlanner(max_refs=3, allow_dist_rank=False)
    dry_runner = L2DryRunner(planner=planner, min_distance_gap=0.1)

    def note_candidate_failure(family: str, reason: str) -> None:
        failed_candidate_counts[family] = failed_candidate_counts.get(family, 0) + 1
        bucket = failed_candidate_detail_counts.setdefault(family, {})
        bucket[reason] = bucket.get(reason, 0) + 1

    failed_candidate_counts: Dict[str, int] = {}
    _pre_verify_counts: Dict[str, int] = {}


    plan_cache: Dict[str, Any] = {}
    available_family_counts: Dict[str, int] = {}
    pool_index: Dict[str, Dict[str, Any]] = {}    # gap_key -> pool entry (O(1) lookup)

    # ── Precompute shared data to avoid redundant per-gap computation ──
    import time as _time
    _t0 = _time.perf_counter()

    # pivot_neighbors: only depends on B (24 unique nodes, not 6072 gaps)
    _pivot_cache: Dict[str, list] = {}
    _unique_b_ids = set(g["b_id"] for g in pool)
    for bid in _unique_b_ids:
        _pivot_cache[bid] = graph_pivot_neighbors(graph_index, bid)

    # converge_rows: only depends on (A,C) pair (n*(n-1) unique, not n*(n-1)*(n-2))
    _converge_cache: Dict[tuple, list] = {}
    _unique_ac = set((g["a_id"], g["c_id"]) for g in pool)
    for a_id, c_id in _unique_ac:
        _converge_cache[(a_id, c_id)] = graph_converge_rows(graph_index, a_id, c_id)

    # directed_refs: depends on candidate_ids from converge_rows → cache by (A,C) too
    _refs_cache: Dict[tuple, list] = {}
    for ac_key, rows in _converge_cache.items():
        cand_ids = [str(r.get("id")) for r in rows if r.get("id")]
        _refs_cache[ac_key] = graph_directed_refs_for_candidates(graph_index, cand_ids)

    _t1 = _time.perf_counter()
    log_stage(f"generate precompute done unique_b={len(_unique_b_ids)} unique_ac={len(_unique_ac)} elapsed_ms={int((_t1-_t0)*1000)}")

    # M3: All 5 families enter plan_cache (no R1/R2 split)
    _PHASE1_FAMILIES = {"converge", "diverge_compare"}

    def build_gap_plans(g: Dict[str, Any]):
        gap = L2Gap(g["a_id"], g["b_id"], g["c_id"], g["a_type"], g["b_type"], g["c_type"])
        a, b, c = node_obj(g, "a"), node_obj(g, "b"), node_obj(g, "c")
        converge_rows = _converge_cache.get((gap.a_id, gap.c_id), [])
        directed_refs = _refs_cache.get((gap.a_id, gap.c_id), [])
        pivot_neighbors = _pivot_cache.get(gap.b_id, [])
        a_out = graph_index.get("out", {}).get(gap.a_id, {})
        b_out = graph_index.get("out", {}).get(gap.b_id, {})
        c_out = graph_index.get("out", {}).get(gap.c_id, {})
        data = DryRunInput(gap, a, b, c, converge_rows=converge_rows, pivot_neighbors=pivot_neighbors, available_refs=directed_refs)
        data.a_to_b_dir = _rel_dir(a_out.get(gap.b_id, {}))
        data.c_to_b_dir = _rel_dir(c_out.get(gap.b_id, {}))
        data.b_to_a_dir = _rel_dir(b_out.get(gap.a_id, {}))
        data.b_to_c_dir = _rel_dir(b_out.get(gap.c_id, {}))
        # M3: all families enter plan_cache (unified single-round)
        plans = dry_runner.feasible(data)
        return data, plans

    # ── Direct plan verify: operates on DryRunInput/DryRunPlan + graph_index ──
    # Bypasses plan_to_qa_record, _memory_verify, verify_valid entirely.
    # Savings: ~14s (plan_to_qa_record 5.5s + _memory_verify 8.6s) from 59s.
    _gi_out = graph_index.get("out", {})
    _gi_obj = graph_index.get("objects", {})

    def _gi_dir(src: str, dst: str) -> str | None:
        """Get direction from graph_index out edges."""
        rel = _gi_out.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("direction_6") or rel.get("direction_official")
        if d:
            return str(d)
        angle = rel.get("angle")
        if angle is not None:
            try:
                a = float(angle)
                if -30 < a <= 30: return "front"
                if 30 < a <= 90: return "front_left"
                if -90 < a <= -30: return "front_right"
                if 90 < a <= 150: return "back_left"
                if -150 < a <= -90: return "back_right"
                return "back"
            except (ValueError, TypeError):
                pass
        return None

    def _gi_dist(src: str, dst: str) -> float | None:
        rel = _gi_out.get(src, {}).get(dst)
        if not rel:
            return None
        d = rel.get("distance")
        if d is not None:
            try: return float(d)
            except (ValueError, TypeError): pass
        # Fallback: check metrics.distance (same as _edge_dist in pre_verify)
        metrics = rel.get("metrics")
        if isinstance(metrics, dict) and metrics.get("distance") is not None:
            try: return float(metrics["distance"])
            except (ValueError, TypeError): pass
        return None

    def _direct_plan_verify(data: DryRunInput, plan) -> bool:
        """Verify a plan directly from DryRunInput without building QA record.
        Equivalent to plan_to_qa_record + _memory_verify + verify_valid but ~10x faster.
        """
        fam = plan.family.value
        a_id, b_id, c_id = data.gap.a_id, data.gap.b_id, data.gap.c_id

        if fam == "viewpoint_transfer":
            return True

        if fam == "direction_chain":
            return _gi_dir(a_id, b_id) is not None and _gi_dir(b_id, c_id) is not None

        if fam == "distance_chain":
            d_ab = _gi_dist(a_id, b_id)
            d_bc = _gi_dist(b_id, c_id)
            return d_ab is not None and d_bc is not None and d_ab != d_bc

        if fam == "converge":
            # Must find exactly 1 X matching: type=b_type, dir(a→X)=dir_from_a, dir(c→X)=dir_from_c + ref constraints
            target_type = data.gap.b_type
            dir_from_a = data.a_to_b_dir or ""
            dir_from_c = data.c_to_b_dir or ""
            # Find from A side
            candidates = set()
            for dst, rel in _gi_out.get(a_id, {}).items():
                obj = _gi_obj.get(dst, {})
                if obj.get("type") == target_type and _gi_dir(a_id, dst) == dir_from_a:
                    candidates.add(dst)
            if not candidates:
                return False
            # Intersect with C side
            candidates = {x for x in candidates if _gi_dir(c_id, x) == dir_from_c}
            if not candidates:
                return False
            # Apply ref_dir constraints from plan.clauses
            for clause in plan.clauses:
                if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                    candidates = {x for x in candidates if _gi_dir(clause.ref_id, x) == clause.value}
                    if not candidates:
                        return False
            # Must be exactly 1 match and it must be b_id
            return len(candidates) == 1 and next(iter(candidates)) == b_id

        if fam == "diverge_compare":
            from gap_pipeline.l2_adapter import _branch_clauses
            # Check A branch
            a_type, a_dir = data.gap.a_type, data.b_to_a_dir or ""
            a_cands = set()
            for dst, rel in _gi_out.get(b_id, {}).items():
                obj = _gi_obj.get(dst, {})
                if obj.get("type") == a_type and _gi_dir(b_id, dst) == a_dir:
                    a_cands.add(dst)
            if not a_cands:
                return False
            a_clauses = _branch_clauses(plan, "a", excluded_ref_id="")
            for clause in a_clauses:
                if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                    a_cands = {x for x in a_cands if _gi_dir(clause.ref_id, x) == clause.value}
                    if not a_cands:
                        return False
            if len(a_cands) != 1 or next(iter(a_cands)) != a_id:
                return False

            # Check C branch
            c_type, c_dir = data.gap.c_type, data.b_to_c_dir or ""
            c_cands = set()
            for dst, rel in _gi_out.get(b_id, {}).items():
                obj = _gi_obj.get(dst, {})
                if obj.get("type") == c_type and _gi_dir(b_id, dst) == c_dir:
                    c_cands.add(dst)
            if not c_cands:
                return False
            c_clauses = _branch_clauses(plan, "c", excluded_ref_id="")
            for clause in c_clauses:
                if clause.kind == "ref_dir" and clause.ref_id and clause.value:
                    c_cands = {x for x in c_cands if _gi_dir(clause.ref_id, x) == clause.value}
                    if not c_cands:
                        return False
            if len(c_cands) != 1 or next(iter(c_cands)) != c_id:
                return False
            return True

        return True  # Unknown family → pass

    _t2 = _time.perf_counter()
    _pre_verify_filtered = 0
    _pre_verify_total = 0
    for g in pool:
        key = l2_key(g["a_id"], g["b_id"], g["c_id"])
        data, plans = build_gap_plans(g)
        if plans:
            verified_plans = []
            for plan in plans:
                _pre_verify_total += 1
                if _direct_plan_verify(data, plan):
                    verified_plans.append(plan)
                else:
                    _pre_verify_filtered += 1
            plans = verified_plans
        plan_cache[key] = (data, plans)
        pool_index[key] = g
        for plan in plans:
            fam = plan.family.value
            available_family_counts[fam] = available_family_counts.get(fam, 0) + 1
    _t3 = _time.perf_counter()
    log_stage(f"generate plan_cache built gaps={len(pool)} elapsed_ms={int((_t3-_t2)*1000)} total_ms={int((_t3-_t0)*1000)} pre_verify_filtered={_pre_verify_filtered}/{_pre_verify_total}")
    feasible_gap_count = sum(1 for _, plans in plan_cache.values() if plans)

    # ── Pipeline stage timestamps (for per-record and summary tracing) ──
    _perf_start = _t0 - (_t1 - _t0)  # rough pipeline perf start (before precompute)
    _stage_ts = {
        "precompute_done": (start_dt + __import__('datetime').timedelta(seconds=_t1 - _t0)).isoformat(),
        "plan_cache_done": (start_dt + __import__('datetime').timedelta(seconds=_t3 - _t0 + (_t1 - _t0))).isoformat(),
        "precompute_ms": int((_t1 - _t0) * 1000),
        "plan_cache_ms": int((_t3 - _t2) * 1000),
        "pre_verify_filtered": _pre_verify_filtered,
        "pre_verify_total": _pre_verify_total,
    }
    unavailable_gap_count = len(pool) - feasible_gap_count

    # Build index: gap_key -> its canonical L2 key (for fast pruning)
    # A gap is "covered" when its own l2_key appears in coverage.l2
    gap_l2_keys: Dict[str, set] = {}
    l2_to_gaps: Dict[str, list] = {}  # reverse: l2_element -> list of gap_keys
    for gk in pool_index:
        gap_l2_keys[gk] = {gk}  # gap's own key = l2_key(a,b,c)
        l2_to_gaps.setdefault(gk, []).append(gk)
    active_keys: set = set(pool_index.keys())  # gaps with uncovered L2 elements
    if coverage.l2:
        active_keys.difference_update(coverage.l2)

    coverage_targets = compute_family_targets(len(pool), available_family_counts)
    family_targets = compute_strict_family_targets(len(pool), available_family_counts)
    log_stage(f"generate family_policy desired={FORMAL_FAMILY_RATIO} max_ratio={FORMAL_FAMILY_MAX_RATIO} availability={available_family_counts} targets={family_targets}")

    if artifacts and selection_policy == "advtest":
        artifacts.generated_jsonl.parent.mkdir(parents=True, exist_ok=True)
        artifacts.generated_jsonl.write_text("", encoding="utf-8")
        if artifacts.generated_csv.exists():
            artifacts.generated_csv.unlink()

    def process_gap(g: Dict[str, Any], preferred_plan=None) -> List[Dict[str, Any]]:
        gap_key = l2_key(g["a_id"], g["b_id"], g["c_id"])
        cached = plan_cache.get(gap_key)
        if not cached:
            return []
        data, plans = cached
        qas: List[Dict[str, Any]] = []
        if not plans:
            return qas
        if preferred_plan is not None:
            ordered_plans = [preferred_plan]
        else:
            selected_plan = choose_formal_plan(plans, used_counts, family_targets, selector.rng)
            ordered_plans = [selected_plan] + [p for p in plans if p is not selected_plan]

        frame_idx = int(frame_id) if str(frame_id).isdigit() else None
        for plan in ordered_plans:
            qa_start_perf = _time.perf_counter()
            qa = plan_to_qa_record(data, plan, question_id="0", scene_name=scene_id, frame_idx=frame_idx, skip_cypher=True)
            # Plans are pre-verified in plan_cache build (_memory_verify + verify_valid)
            qa["logic_verification"] = "IN_MEMORY_VERIFIED"
            qa["timestamp_start"] = utc_now_iso()
            if llm_client:
                try:
                    llm_result = llm_client.verbalize(qa.get("question", ""))
                    qa["question"] = llm_result.text
                    qa["token_prompt"] = llm_result.prompt_tokens
                    qa["token_completion"] = llm_result.completion_tokens
                    qa["timestamp_llm"] = utc_now_iso()
                    qa["generation_backend"] = "llm_verbalized"
                    qa["llm_model"] = llm_client.model
                    qa["raw_llm_output"] = llm_result.raw or {}
                except Exception as exc:
                    qa["timestamp_llm"] = utc_now_iso()
                    qa["generation_backend"] = "programmatic_llm_fallback"
                    qa["llm_model"] = llm_client.model
                    qa["raw_llm_output"] = {"error": f"{type(exc).__name__}: {exc}"}
                    qa["token_prompt"] = 0
                    qa["token_completion"] = 0
            else:
                qa["timestamp_llm"] = ""
            qa["timestamp_end"] = utc_now_iso()
            qa["generation_elapsed_ms"] = round((_time.perf_counter() - qa_start_perf) * 1000, 2)
            qa["plan_attempt_key"] = plan_attempt_key(gap_key, plan)

            qa["_family"] = plan.family.value
            qas.append(qa)
            break
        return qas

    if selection_policy == "random_full":
        if artifacts is None:
            raise ValueError("random_full selection requires --artifact-root")

        universe_l0 = set(str(key) for key in graph_index.get("objects", {}))
        universe_l1 = set()
        for src, targets in graph_index.get("out", {}).items():
            for dst in targets:
                universe_l1.add(l1_key(str(src), str(dst)))
        universe_l2 = set(pool_index)
        initial_coverage = {
            "l0": set(coverage.l0),
            "l1": set(coverage.l1),
            "l2": set(coverage.l2),
        }
        initial_gap_keys = sorted(universe_l2 - initial_coverage["l2"])
        if not initial_gap_keys:
            raise ValueError(
                f"Random initial gap pool is empty for {scene_id}_frame{frame_id}"
            )

        gap_to_plan_ids: Dict[str, List[str]] = {}
        plan_objects: Dict[str, List[Any]] = {}
        missing_plan_gaps = []
        for gap_key in initial_gap_keys:
            _, plans = plan_cache[gap_key]
            if not plans:
                missing_plan_gaps.append(gap_key)
                continue
            keyed_plans = {}
            for plan in plans:
                plan_id = stable_random_plan_key(gap_key, plan)
                keyed_plans.setdefault(plan_id, plan)
            ordered = sorted(keyed_plans.items())
            gap_to_plan_ids[gap_key] = [plan_id for plan_id, _ in ordered]
            plan_objects[gap_key] = [plan for _, plan in ordered]
        if missing_plan_gaps:
            sample = ", ".join(missing_plan_gaps[:5])
            raise RuntimeError(
                "Random full-coverage preflight failed: "
                f"{len(missing_plan_gaps)} initial gaps have no verified plan; "
                f"sample={sample}"
            )

        selector = StaticRandomSelector(gap_to_plan_ids, seed=seed)
        accumulator = CoverageAccumulator.create(
            universe={
                "l0": universe_l0,
                "l1": universe_l1,
                "l2": universe_l2,
            },
            initial_coverage=initial_coverage,
        )
        random_dir = artifacts.frame_dir / "random_full"
        if random_run_id:
            random_dir = random_dir / random_run_id
        random_dir = random_dir / f"seed_{seed}"
        checkpoint_path = random_dir / "checkpoint.json"
        draws_path = random_dir / "draws.jsonl"
        unique_questions_path = random_dir / "unique_questions.jsonl"
        summary_path = random_dir / "summary.json"
        manifest_path = random_dir / "manifest.json"
        random_dir.mkdir(parents=True, exist_ok=True)

        if checkpoint_path.exists():
            checkpoint_metadata = load_random_checkpoint(
                checkpoint_path,
                selector=selector,
                accumulator=accumulator,
            )
            expected_frame = f"{scene_id}_frame{frame_id}"
            if checkpoint_metadata.get("frame_key") != expected_frame:
                raise ValueError("Random checkpoint belongs to a different frame")
            if draws_path.exists():
                retained = []
                with draws_path.open("r", encoding="utf-8") as handle:
                    for index, line in enumerate(handle):
                        if index >= accumulator.draws:
                            break
                        retained.append(line)
                draws_path.write_text("".join(retained), encoding="utf-8")
            log_stage(
                f"random_full resume seed={seed} draws={accumulator.draws} "
                f"coverage={len(accumulator.covered_l2)}/{len(accumulator.universe_l2)}"
            )
        else:
            draws_path.write_text("", encoding="utf-8")
            unique_questions_path.write_text("", encoding="utf-8")

        metadata = {
            "frame_key": f"{scene_id}_frame{frame_id}",
            "seed": seed,
                "selection_policy": "static_initial_gap_with_replacement_random_plan",
                "random_run_id": random_run_id,
            "initial_gap_count": len(initial_gap_keys),
            "candidate_fingerprint": selector.fingerprint,
        }

        def realize_random_draw(draw, draw_index: int) -> Dict[str, Any]:
            plans = plan_objects[draw.gap_id]
            plan = plans[draw.plan_index]
            wording_seed = int(
                hashlib.sha256(
                    f"{seed}:{draw_index}:{draw.gap_id}:{draw.plan_id}".encode("utf-8")
                ).hexdigest()[:8],
                16,
            )
            set_variant_seed(wording_seed)
            qas = process_gap(pool_index[draw.gap_id], preferred_plan=plan)
            if not qas:
                raise RuntimeError(
                    f"Preverified random plan failed to realize: {draw.plan_id}"
                )
            qa = qas[0]
            qa["question_id"] = str(draw_index)
            qa["selection_phase"] = "random_static"
            qa["generation_phase"] = 0
            qa["generation_round"] = 0
            qa["random_gap_id"] = draw.gap_id
            qa["random_plan_id"] = draw.plan_id
            qa["random_wording_seed"] = wording_seed
            return normalize_and_validate(qa)

        draw_handle = draws_path.open("a", encoding="utf-8")
        unique_handle = unique_questions_path.open("a", encoding="utf-8")

        def record_random_draw(draw, record, gain) -> None:
            question_hash = hashlib.sha256(
                str(record.get("question") or "").encode("utf-8")
            ).hexdigest()
            compact = {
                "draw_index": accumulator.draws,
                "gap_id": draw.gap_id,
                "plan_id": draw.plan_id,
                "template_id": record.get("template_id", ""),
                "question_hash": question_hash,
                "gain": dict(gain),
                "coverage_l0": len(accumulator.covered_l0),
                "coverage_l1": len(accumulator.covered_l1),
                "coverage_l2": len(accumulator.covered_l2),
            }
            draw_handle.write(json.dumps(compact, ensure_ascii=False) + "\n")
            if accumulator.text_counts[question_hash] == 1:
                unique_handle.write(json.dumps(dict(record), ensure_ascii=False) + "\n")
            if accumulator.draws % checkpoint_interval == 0:
                draw_handle.flush()
                unique_handle.flush()
                log_stage(
                    f"random_full Q{accumulator.draws} seed={seed} "
                    f"coverage={len(accumulator.covered_l2)}/{len(accumulator.universe_l2)}"
                )

        try:
            random_summary = run_random_until_full(
                selector=selector,
                accumulator=accumulator,
                realize=realize_random_draw,
                on_draw=record_random_draw,
                checkpoint_path=checkpoint_path,
                checkpoint_interval=checkpoint_interval,
                max_draws=max_draws,
                metadata=metadata,
            )
        finally:
            draw_handle.flush()
            unique_handle.flush()
            draw_handle.close()
            unique_handle.close()
            write_random_checkpoint(
                checkpoint_path,
                selector=selector,
                accumulator=accumulator,
                metadata=metadata,
            )

        random_summary.update(
            {
                "scene_id": scene_id,
                "frame_id": frame_id,
                "seed": seed,
                "selection_policy": metadata["selection_policy"],
                "candidate_fingerprint": selector.fingerprint,
                "initial_coverage": {
                    level: {
                        "covered": len(initial_coverage[level]),
                        "total": len(getattr(accumulator, f"universe_{level}")),
                        "rate": (
                            len(initial_coverage[level])
                            / len(getattr(accumulator, f"universe_{level}"))
                            if getattr(accumulator, f"universe_{level}")
                            else 1.0
                        ),
                    }
                    for level in ("l0", "l1", "l2")
                },
                "paths": {
                    "checkpoint": str(checkpoint_path),
                    "draws": str(draws_path),
                    "unique_questions": str(unique_questions_path),
                    "summary": str(summary_path),
                },
            }
        )
        write_summary(summary_path, random_summary)
        write_summary(
            manifest_path,
            {
                "schema": "rq2_random_full_coverage_manifest_v1",
                "metadata": metadata,
                "summary_sha256": hashlib.sha256(
                    summary_path.read_bytes()
                ).hexdigest(),
                "paths": random_summary["paths"],
            },
        )
        log_stage(
            f"random_full DONE seed={seed} draws={accumulator.draws} "
            f"coverage={len(accumulator.covered_l2)}/{len(accumulator.universe_l2)}"
        )
        if session:
            session.close()
        return []

    if selection_policy != "advtest":
        raise ValueError(f"Unknown selection_policy: {selection_policy}")

    def find_underserved_family() -> str | None:
        """Find a family below its minimum quota."""
        if len(out) < 20:
            return None
        worst_family = None
        worst_deficit = 0
        for fam, min_r in FORMAL_FAMILY_MIN_RATIO.items():
            min_count = int(len(out) * min_r)
            current = used_counts.get(fam, 0)
            deficit = min_count - current
            if deficit > worst_deficit:
                worst_deficit = deficit
                worst_family = fam
        return worst_family


    auxiliary_uncapped = [False]  # mutable flag, set when primary pool exhausted

    def _auxiliary_budget_left() -> bool:
        """Check if auxiliary families (chain/viewpoint) still have room under 25% cap."""
        if auxiliary_uncapped[0]:
            return True
        if len(out) < 20:
            return True
        aux_count = sum(1 for r in out if r.get("l2_family") in AUXILIARY_FAMILIES)
        return aux_count / max(len(out), 1) < AUXILIARY_MAX_RATIO

    # ── Cursor-based selection: gap-level L0/L1 scoring ──────────
    # Score a GAP (not a plan) by how many NEW L0 nodes + L1 edges it covers.
    # gap (A,B,C) guarantees: L0={A,B,C}, L1={A|B, B|C}
    # This is ground truth — no ref prediction, no speculation.
    #
    # Thresholds by L2 coverage ratio:
    #   0-50%:  score >= 200  (want 2+ new L0 nodes)
    #   50-80%: score >= 100  (want 1+ new L0 node)
    #   80-95%: score >= 10   (want 1+ new L1 edge)
    #   95%+:   score > 0     (accept any uncovered gap)
    _THRESHOLDS = [(0.50, 200), (0.80, 100), (0.95, 10), (1.01, 0)]

    _tried_fast: set = set()  # (gap_key, plan_idx) tuples

    # Pre-sort plans per gap by footprint L2 size (descending).
    # Footprint is deterministic, pre-computed in plan_cache — zero extra cost.
    _gap_plans: Dict[str, list] = {}
    for gk, (_, plans) in plan_cache.items():
        indexed = list(enumerate(plans))
        indexed.sort(key=lambda x: len((x[1].footprint or {}).get("l2", [])), reverse=True)
        _gap_plans[gk] = indexed

    def _gap_score(gk: str) -> int:
        """Score a gap by its guaranteed L0/L1 coverage gain. O(1)."""
        g = pool_index[gk]
        a, b, c = str(g["a_id"]), str(g["b_id"]), str(g["c_id"])
        l0_new = sum(1 for x in (a, b, c) if x not in coverage.l0)
        l1_ab = l1_key(a, b) not in coverage.l1
        l1_bc = l1_key(b, c) not in coverage.l1
        l1_new = int(l1_ab) + int(l1_bc)
        return l0_new * 100 + l1_new * 10 + 1  # +1 for guaranteed L2

    def _coverage_ratio() -> float:
        return len(coverage.l2) / max(len(pool), 1)

    def _pick_plan(gk: str, *, allowed_families: set[str] | None = None) -> tuple[Any, int, int] | None:
        """Pick the feasible plan that maximizes dynamic incremental L2 coverage gain for a gap,
        restricted to the allowed families.
        Returns (plan, plan_index, l2_gain) or None.
        """
        candidates = _gap_plans.get(gk, [])
        best_candidate = None
        best_gain = -1
        
        for pi, plan in candidates:
            if (gk, pi) in _tried_fast:
                continue
            if allowed_families and plan.family.value not in allowed_families:
                continue
            
            # Dynamic incremental gain check
            fp_l2 = (plan.footprint or {}).get("l2", [])
            gain = sum(1 for x in fp_l2 if x not in coverage.l2)
            
            # Since the gap gk itself is guaranteed uncovered in active_keys,
            # gain should be at least 1 for any plan covering gk.
            if gain > best_gain:
                best_gain = gain
                best_candidate = (plan, pi, max(gain, 1))
                
        return best_candidate

    def _cursor_select(*, restrict_families: set | None = None) -> tuple[Dict[str, Any], Any, int] | None:
        """Two-level selection:
        1. Gap ordering: L0/L1 gap score (early diversity)
        2. Plan within gap: footprint coverage_gain (L2 efficiency)
        """
        ratio = _coverage_ratio()
        # Gap-level thresholds (L0/L1 based)
        thresholds_to_try = [t for cap, t in _THRESHOLDS if ratio < cap]
        if not thresholds_to_try:
            thresholds_to_try = [0]

        for min_score in thresholds_to_try:
            for gk in list(active_keys):
                if min_score > 0:
                    gs = _gap_score(gk)
                    if gs < min_score:
                        continue
                result = _pick_plan(gk, allowed_families=restrict_families)
                if result is None:
                    continue
                plan, pi, l2_gain = result
                return (pool_index[gk], plan, pi)
        return None

    # ── Single-pass cursor: pre-sort gaps once, iterate linearly ──
    # Sort all gap keys by static gap_score (descending). This determines
    # the processing order. We scan through this list ONCE, skipping gaps
    # that have been covered by previous questions' footprints.
    _sorted_gap_keys = sorted(
        active_keys,
        key=lambda gk: _gap_score(gk),
        reverse=True,
    )
    _cursor_pos = 0  # current position in _sorted_gap_keys

    def _cursor_select_linear(*, restrict_families: set | None = None) -> tuple[Dict[str, Any], Any, int] | None:
        """O(1) amortized gap selection: continue reading from cursor position,
        skip already-covered gaps, pick first feasible plan."""
        nonlocal _cursor_pos

        while _cursor_pos < len(_sorted_gap_keys):
            gk = _sorted_gap_keys[_cursor_pos]
            _cursor_pos += 1
            # Already covered by a previous question's footprint? → skip
            if gk not in active_keys:
                continue
            result = _pick_plan(gk, allowed_families=restrict_families)
            if result is None:
                continue
            plan, pi, l2_gain = result
            return (pool_index[gk], plan, pi)
        return None

    def emit_qa_records(qas: List[Dict[str, Any]], *, write_header_state: List[bool]) -> None:
        for qa in qas:
            if max_questions is not None and len(out) >= max_questions:
                break
            qa["question_id"] = str(len(out) + 1)
            family = qa.pop("_family", qa.get("l2_family", ""))
            # Determine phase: primary if family is within its target quota,
            # otherwise coverage_backfill
            if family_cap_blocked(family, used_counts, max(len(out), 1)):
                phase = "coverage_backfill"
            else:
                phase = "primary"
            qa["selection_phase"] = phase
            qa = normalize_and_validate(qa)
            out.append(qa)
            attempt_key = str(qa.get("plan_attempt_key") or "")
            if attempt_key:
                selected_attempts[attempt_key] = {
                    "order_index": len(out),
                    "selection_phase": phase,
                    "family": family,
                }

            coverage.mark(qa.get("coverage_footprint") or {})
            # Prune: remove gaps whose canonical L2 key is now covered
            fp_l2 = set(str(x) for x in (qa.get("coverage_footprint") or {}).get("l2", []))
            active_keys.difference_update(fp_l2)
            if len(out) <= 3 or len(out) % 5000 == 0:
                log_stage(f"generate Q{len(out)} active_keys={len(active_keys)} coverage.l2={len(coverage.l2)}/{len(pool)}")
            used_counts[family] = used_counts.get(family, 0) + 1
            if phase != "primary":
                backfill_counts[family] = backfill_counts.get(family, 0) + 1



    write_header_state = [True]

    # ── M3: Unified single-round generation (Phase 1 + Phase 2) ──────────
    # Phase 1 (coverage < K%): greedy converge+diverge only (high coverage families)
    # Phase 2 (coverage >= K%): balanced 4-slot selection (min-count-first)
    #
    # Key difference from old R1/R2:
    #   - No second pass over the entire pool; everything is one continuous loop.
    #   - Phase 2 tracks delta_l2 and removes covered gaps, just like Phase 1.
    #   - 4-slot balancing ensures type diversity without producing N questions per gap.

    from gap_pipeline.l2_question_realizer import (
        direction_chain_question, distance_chain_question, viewpoint_transfer_question,
    )
    from gap_pipeline.l2_question_graph import chain_graph
    from gap_pipeline.l2_geometry import point_from_obj, viewpoint_left_right

    # Compute plateau window from fixed window setting
    PHASE1_PLATEAU_WINDOW = int(os.environ.get("ADVTEST_PLATEAU_WINDOW") or 10)
    _plateau_window = PHASE1_PLATEAU_WINDOW
    log_stage(f"generate M3 unified: pool={len(pool)} plateau_window={_plateau_window} phase2_slots={list(PHASE2_SLOTS.keys())}")

    # Phase 2 slot counters
    _slot_counts: Dict[str, int] = {slot: 0 for slot in PHASE2_SLOTS}
    _phase2_rng = random.Random(seed + 42)

    # Build per-family plan index for quick slot-based lookup
    # gap_key -> {family: [plans]}
    _gap_family_plans: Dict[str, Dict[str, list]] = {}
    for gk, (_, plans) in plan_cache.items():
        by_fam: Dict[str, list] = {}
        for plan in plans:
            by_fam.setdefault(plan.family.value, []).append(plan)
        _gap_family_plans[gk] = by_fam

    def _compute_delta_l2(footprint: Dict[str, Any]) -> int:
        """Count how many new L2 gaps this footprint covers (not yet in coverage)."""
        fp_l2 = footprint.get("l2", [])
        return sum(1 for x in fp_l2 if str(x) not in coverage.l2)


    def _try_cheap_family(g: Dict[str, Any], family: str) -> Dict[str, Any] | None:
        """Try to generate a cheap (no constraint) question for a gap + family.
        Used in Phase 2 for chain/viewpoint families that may not be in plan_cache.
        """
        a_id, b_id, c_id = g["a_id"], g["b_id"], g["c_id"]
        frame_idx_val = int(frame_id) if str(frame_id).isdigit() else None

        if family == "direction_chain":
            dir_ab = _gi_dir(a_id, b_id)
            dir_bc = _gi_dir(b_id, c_id)
            if dir_ab is not None and dir_bc is not None:
                q = direction_chain_question(a_id, b_id, c_id)
                fp = chain_graph(a_id, b_id, c_id, family="direction_chain").footprint().as_dict()
                return {
                    "question_id": "0", "scene_name": scene_id, "frame_idx": frame_idx_val,
                    "topology_level": "L2", "template_id": "direction_chain",
                    "constraint_trace": [], "constraint_count": 0, "constraint_types": [],
                    "candidate_before": 0, "candidate_after": 0, "unique_check": True,
                    "generation_backend": "programmatic", "llm_model": "",
                    "raw_llm_output": {}, "token_prompt": 0, "token_completion": 0,
                    "logic_verification": "IN_MEMORY_VERIFIED", "is_unique": True,
                    "n_interference_siblings": 0,
                    "question": q.question, "answer": (dir_ab == dir_bc),
                    "answer_type": q.answer_type,
                    "path_pattern": f"{a_id}|{b_id}|{c_id}",
                    "footprint_nodes": [a_id, b_id, c_id],
                    "coverage_footprint": fp, "verify_payload": {},
                    "l2_refactor": True, "l2_family": "direction_chain", "l2_score": 1.0,
                    "_family": "direction_chain",
                    "timestamp_start": utc_now_iso(), "timestamp_end": utc_now_iso(),
                    "generation_elapsed_ms": 0,
                    "plan_attempt_key": f"p2_{l2_key(a_id, b_id, c_id)}_dc",
                }

        if family == "distance_chain":
            d_ab = _gi_dist(a_id, b_id)
            d_bc = _gi_dist(b_id, c_id)
            if d_ab is not None and d_bc is not None and d_ab != d_bc:
                q = distance_chain_question(a_id, b_id, c_id)
                fp = chain_graph(a_id, b_id, c_id, family="distance_chain").footprint().as_dict()
                answer = a_id if d_ab < d_bc else c_id
                return {
                    "question_id": "0", "scene_name": scene_id, "frame_idx": frame_idx_val,
                    "topology_level": "L2", "template_id": "distance_chain",
                    "constraint_trace": [], "constraint_count": 0, "constraint_types": [],
                    "candidate_before": 0, "candidate_after": 0, "unique_check": True,
                    "generation_backend": "programmatic", "llm_model": "",
                    "raw_llm_output": {}, "token_prompt": 0, "token_completion": 0,
                    "logic_verification": "IN_MEMORY_VERIFIED", "is_unique": True,
                    "n_interference_siblings": 0,
                    "question": q.question, "answer": answer,
                    "answer_type": q.answer_type,
                    "path_pattern": f"{a_id}|{b_id}|{c_id}",
                    "footprint_nodes": [a_id, b_id, c_id],
                    "coverage_footprint": fp, "verify_payload": {},
                    "l2_refactor": True, "l2_family": "distance_chain", "l2_score": 1.0,
                    "_family": "distance_chain",
                    "timestamp_start": utc_now_iso(), "timestamp_end": utc_now_iso(),
                    "generation_elapsed_ms": 0,
                    "plan_attempt_key": f"p2_{l2_key(a_id, b_id, c_id)}_dist",
                }

        if family == "viewpoint_transfer":
            gap_key = l2_key(a_id, b_id, c_id)
            cached = plan_cache.get(gap_key)
            if not cached:
                return None
            data = cached[0]
            pa = point_from_obj(data.a_obj)
            pb = point_from_obj(data.b_obj)
            pc = point_from_obj(data.c_obj)
            if pa is not None and pb is not None and pc is not None:
                ans = viewpoint_left_right(pa, pb, pc)
                if ans is not None:
                    q = viewpoint_transfer_question(a_id, b_id, c_id)
                    fp = chain_graph(a_id, b_id, c_id, family="viewpoint_transfer").footprint().as_dict()
                    return {
                        "question_id": "0", "scene_name": scene_id, "frame_idx": frame_idx_val,
                        "topology_level": "L2", "template_id": "viewpoint_transfer",
                        "constraint_trace": [], "constraint_count": 0, "constraint_types": [],
                        "candidate_before": 0, "candidate_after": 0, "unique_check": True,
                        "generation_backend": "programmatic", "llm_model": "",
                        "raw_llm_output": {}, "token_prompt": 0, "token_completion": 0,
                        "logic_verification": "IN_MEMORY_VERIFIED", "is_unique": True,
                        "n_interference_siblings": 0,
                        "question": q.question, "answer": ans,
                        "answer_type": q.answer_type,
                        "path_pattern": f"{a_id}|{b_id}|{c_id}",
                        "footprint_nodes": [a_id, b_id, c_id],
                        "coverage_footprint": fp, "verify_payload": {},
                        "l2_refactor": True, "l2_family": "viewpoint_transfer", "l2_score": 1.0,
                        "_family": "viewpoint_transfer",
                        "timestamp_start": utc_now_iso(), "timestamp_end": utc_now_iso(),
                        "generation_elapsed_ms": 0,
                        "plan_attempt_key": f"p2_{gap_key}_vp",
                    }
        return None

    def _try_gap_for_slot(g: Dict[str, Any], slot: str) -> List[Dict[str, Any]]:
        """Try to generate a QA for the gap using the given slot's family preference.
        Returns list of QA records (0 or 1 element)."""
        gap_key = l2_key(g["a_id"], g["b_id"], g["c_id"])
        families = PHASE2_SLOTS[slot]
        for family in families:
            # First: try from plan_cache (covers converge/diverge + any cached cheap plans)
            fam_plans = _gap_family_plans.get(gap_key, {}).get(family, [])
            for plan in fam_plans:
                try:
                    qas = process_gap(g, preferred_plan=plan)
                    if qas:
                        return qas
                except Exception:
                    continue
            # Second: try cheap inline generation (direction_chain, distance_chain, viewpoint_transfer)
            if family in AUXILIARY_FAMILIES:
                qa = _try_cheap_family(g, family)
                if qa is not None:
                    return [qa]
        return []

    # ── Phase 1: Greedy coverage with converge+diverge ──
    # Exit condition: L2 coverage ratio reaches K_THRESHOLD (default 25%)
    K_THRESHOLD = float(os.environ.get("ADVTEST_K_THRESHOLD") or 0.25)
    stall_counter = 0
    max_stall = len(pool)
    _phase1_count = 0
    _delta_l2_streak = 0  # consecutive questions with delta_l2 == 1
    _phase1_switch_reason = "pool_exhausted"
    _phase1_delta_l2_history: List[int] = []  # for diagnostics

    while (max_questions is None or len(out) < max_questions) and len(coverage.l2) < len(pool):
        # Exit Phase 1 if the K threshold is reached or plateau streak is reached
        current_ratio = _coverage_ratio()
        if current_ratio >= K_THRESHOLD or _delta_l2_streak >= _plateau_window:
            if _delta_l2_streak >= _plateau_window:
                _phase1_switch_reason = f"plateau_reached(streak={_delta_l2_streak}, window={_plateau_window})"
            else:
                _phase1_switch_reason = f"k_threshold_reached(ratio={current_ratio:.4f}, threshold={K_THRESHOLD:.4f})"
            log_stage(
                f"generate phase1 exit at Q{len(out)}: reason={_phase1_switch_reason} "
                f"coverage={len(coverage.l2)}/{len(pool)} ({current_ratio*100:.1f}%), switching to phase2."
            )
            break

        if stall_counter > max_stall:
            _phase1_switch_reason = f"stall_limit(stall={stall_counter})"
            log_stage(f"generate phase1 stall_limit reached stall={stall_counter}")
            break
        selected = _cursor_select_linear(restrict_families=_PHASE1_FAMILIES)
        if selected is None:
            # Cursor exhausted for Phase 1 families — move to Phase 2
            _phase1_switch_reason = "cursor_exhausted"
            log_stage(f"generate phase1 cursor exhausted at Q{len(out)} coverage={len(coverage.l2)}/{len(pool)}")
            break
        g, selected_plan, plan_idx = selected
        gap_key = l2_key(g["a_id"], g["b_id"], g["c_id"])
        _tried_fast.add((gap_key, plan_idx))
        tried.add(plan_attempt_key(gap_key, selected_plan))
        try:
            qas = process_gap(g, preferred_plan=selected_plan)
        except Exception as exc:
            log_stage(f"generate phase1 skip gap={gap_key} error={type(exc).__name__}: {exc}")
            stall_counter += 1
            continue
        if not qas:
            failed_family = selected_plan.family.value
            note_candidate_failure(failed_family, last_failure_detail.pop(failed_family, "invalid_or_no_qa"))
            stall_counter += 1
            continue
        stall_counter = 0

        # Compute delta_l2 BEFORE emit (which updates coverage)
        qa_delta_l2 = 0
        for qa in qas:
            fp = qa.get("coverage_footprint") or {}
            qa_delta_l2 += _compute_delta_l2(fp)

        # Track plateau
        _phase1_delta_l2_history.append(qa_delta_l2)
        if qa_delta_l2 <= 1:
            _delta_l2_streak += 1
        else:
            _delta_l2_streak = 0

        # Tag phase
        for qa in qas:
            qa["generation_phase"] = 1
        emit_qa_records(qas, write_header_state=write_header_state)
        _phase1_count += len(qas)

    _t_phase1_end = _time.perf_counter()
    _phase1_switch_coverage = len(coverage.l2) / max(len(pool), 1)
    log_stage(
        f"generate phase1 DONE generated={_phase1_count} "
        f"switch_reason={_phase1_switch_reason} "
        f"coverage={len(coverage.l2)}/{len(pool)} ({_phase1_switch_coverage*100:.1f}%) "
        f"elapsed={int((_t_phase1_end-_t3)*1000)}ms"
    )

    # ── Phase 2: Balanced 4-slot selection ──
    # Compensate Phase 2 slots by inheriting Phase 1 Slot A question counts
    _slot_counts["A"] = _phase1_count
    # Re-sort remaining uncovered gaps for Phase 2 traversal
    _phase2_gap_keys = sorted(
        (gk for gk in active_keys),
        key=lambda gk: _gap_score(gk),
        reverse=True,
    )
    _phase2_idx = 0
    _phase2_count = 0
    _phase2_skipped = 0

    while (max_questions is None or len(out) < max_questions) and _phase2_idx < len(_phase2_gap_keys):
        gk = _phase2_gap_keys[_phase2_idx]
        _phase2_idx += 1

        # Skip if already covered by a previous question's footprint
        if gk not in active_keys:
            continue

        g = pool_index.get(gk)
        if g is None:
            continue

        # Pick slot with minimum count (ties broken randomly)
        min_count = min(_slot_counts.values())
        candidates_slots = [s for s, c in _slot_counts.items() if c == min_count]
        slot = _phase2_rng.choice(candidates_slots)

        # Try preferred slot
        qas = _try_gap_for_slot(g, slot)

        # Fallback: try other slots in ascending count order
        if not qas:
            fallback_order = sorted(_slot_counts.keys(), key=lambda s: (_slot_counts[s], s))
            for fb_slot in fallback_order:
                if fb_slot == slot:
                    continue
                qas = _try_gap_for_slot(g, fb_slot)
                if qas:
                    slot = fb_slot
                    break

        if qas:
            # Tag phase
            for qa in qas:
                qa["generation_phase"] = 2
            emit_qa_records(qas, write_header_state=write_header_state)
            _slot_counts[slot] += 1
            _phase2_count += 1
        else:
            _phase2_skipped += 1

    _t_phase2_end = _time.perf_counter()
    log_stage(
        f"generate phase2 DONE generated={_phase2_count} skipped={_phase2_skipped} "
        f"slot_counts={_slot_counts} "
        f"coverage={len(coverage.l2)}/{len(pool)} ({len(coverage.l2)/max(len(pool),1)*100:.1f}%) "
        f"elapsed={int((_t_phase2_end-_t_phase1_end)*1000)}ms"
    )

    # ── Backward-compatible round tags ──
    # Map generation_phase to generation_round for downstream compatibility
    for qa in out:
        qa["generation_round"] = qa.get("generation_phase", 1)


    formal_selected_count = sum(1 for r in out if r.get("selection_phase") == "primary")
    formal_covered_gap_count = len(coverage.l2)

    if artifacts:
        update_plan_status(artifacts.root, artifacts.scene_id, artifacts.frame_id, "generate", "DONE")
    _t_gen_end = _time.perf_counter()
    _gen_ms = int((_t_gen_end - _t3) * 1000)
    _neo4j_verify_ms = sum(q.get("verify_elapsed_ms", 0) for q in out if q.get("verify_elapsed_ms"))
    log_stage(
        f"generate DONE scene={scene_id} frame={frame_id} "
        f"generated={len(out)} tried={len(tried)} pool_size={len(pool)} | "
        f"timing: precompute={int((_t1-_t0)*1000)}ms "
        f"plan_cache={int((_t3-_t2)*1000)}ms(pre_verify_filtered={_pre_verify_filtered}/{_pre_verify_total}) "
        f"selection+gen={_gen_ms}ms(neo4j_verify={_neo4j_verify_ms}ms)"
    )
    ended_at = utc_now_iso()
    elapsed_ms = int((datetime.now(timezone.utc) - start_dt).total_seconds() * 1000)
    generated_count = max(len(out), 1)
    formal_count_denominator = max(formal_selected_count, 1)
    family_policy = {
        "desired_ratio": FORMAL_FAMILY_RATIO,
        "max_ratio": FORMAL_FAMILY_MAX_RATIO,
        "selection_objective": "m3_unified_phase1_greedy_phase2_balanced_4slot",

        "priority_weight": FORMAL_FAMILY_PRIORITY_WEIGHT,
        "redistribution_order": FORMAL_REDISTRIBUTION_ORDER,
        "availability": available_family_counts,
        "coverage_backfill_target": coverage_targets,

        "failed_candidate_counts": failed_candidate_counts,
        "failed_candidate_detail_counts": failed_candidate_detail_counts,
        "converge_failure_samples": converge_failure_samples,

        # M3 phase metadata
        "phase1_plateau_window": _plateau_window,
        "phase1_switch_reason": _phase1_switch_reason,
        "phase1_switch_coverage_pct": round(_phase1_switch_coverage * 100, 2),
        "phase1_delta_l2_history": _phase1_delta_l2_history,
        "phase1_count": _phase1_count,
        "phase2_count": _phase2_count,
        "phase2_slot_counts": dict(_slot_counts),
        "phase2_skipped": _phase2_skipped,

        "effective_target": family_targets,
        "feasible_gap_count": feasible_gap_count,
        "unavailable_gap_count": unavailable_gap_count,
        "formal_actual": dict(used_counts),
        "formal_actual_ratio": {fam: used_counts.get(fam, 0) / formal_count_denominator for fam in FORMAL_FAMILY_RATIO},
        "formal_share_of_total_generated": {fam: used_counts.get(fam, 0) / generated_count for fam in FORMAL_FAMILY_RATIO},
    }
    universe_stats = {
        "neo4j": neo4j_graph_stats,
        "formal_selected_count": formal_selected_count,
        "formal_covered_gap_count": formal_covered_gap_count,
        "coverage_backfill_count": len(out) - formal_selected_count,
        "formal_actual": dict(used_counts),
        "coverage_backfill_actual": dict(backfill_counts),
        "backfill_balance_relaxed": False,
        "initial_coverage": initial_coverage_summary,



        "total_gap_count": len(pool),
        "feasible_gap_count": feasible_gap_count,
        "unavailable_gap_count": unavailable_gap_count,
    }
    # Finalize pipeline timing
    _stage_ts["selection_gen_ms"] = _gen_ms
    _stage_ts["neo4j_verify_ms"] = _neo4j_verify_ms
    _stage_ts["selection_start"] = _stage_ts["plan_cache_done"]
    _stage_ts["pipeline_end"] = ended_at
    _stage_ts["total_ms"] = elapsed_ms
    summary = build_summary(out, coverage, tried=len(tried), pool_size=len(pool), pool_source=pool_source, started_at=started_at, ended_at=ended_at, elapsed_ms=elapsed_ms, family_policy=family_policy, universe_stats=universe_stats)
    summary["pipeline_timing"] = _stage_ts
    # Incremental coverage CSV (for plotting coverage curves)
    emit_incremental_coverage_report(out, summary, artifacts=artifacts, selected_attempts=selected_attempts)
    # NOTE: candidate_potential report disabled (too large for production)
    # emit_candidate_potential_report(plan_cache, selected_attempts, artifacts=artifacts)

    summary_row = {
        "run_id": f"{scene_id}_frame{frame_id}_{started_at}",
        "scene_id": scene_id,
        "frame_id": frame_id,
        "timestamp_start": started_at,
        "timestamp_end": ended_at,
        "elapsed_ms": elapsed_ms,
        "precompute_ms": _stage_ts["precompute_ms"],
        "plan_cache_ms": _stage_ts["plan_cache_ms"],
        "selection_gen_ms": _stage_ts["selection_gen_ms"],
        "neo4j_verify_ms": _stage_ts["neo4j_verify_ms"],
        "pre_verify_filtered": _stage_ts["pre_verify_filtered"],
        "pre_verify_total": _stage_ts["pre_verify_total"],
        "generated": summary.get("generated", 0),
        "tried_candidate_count": summary.get("tried_candidate_count", 0),
        "pool_source": summary.get("pool_source", ""),
        "pool_size": summary.get("pool_size", 0),
        "total_gap_count": summary.get("total_gap_count", 0),
        "covered_gap_count": summary.get("covered_gap_count", 0),
        "uncovered_gap_count": summary.get("uncovered_gap_count", 0),
        "failed_candidate_count": summary.get("failed_candidate_count", 0),
        "feasible_gap_count": universe_stats.get("feasible_gap_count", 0),
        "unavailable_gap_count": universe_stats.get("unavailable_gap_count", 0),
        "neo4j_object_count": neo4j_graph_stats.get("object_count", 0),
        "neo4j_relationship_count": neo4j_graph_stats.get("relationship_count", 0),
        "coverage_l0": summary.get("coverage", {}).get("l0", 0),
        "coverage_l1": summary.get("coverage", {}).get("l1", 0),
        "coverage_l2": summary.get("coverage", {}).get("l2", 0),
        "families_json": summary.get("families", {}),
        "family_policy_json": summary.get("family_policy", {}),
        "universe_stats_json": summary.get("universe_stats", {}),
        "verification_json": summary.get("verification", {}),
    }
    if artifacts:
        # ── Primary output: single merged question bank ──
        # Phase 1/2 records are distinguished by the "generation_phase" field
        # inside each record; no need for separate round1/round2 files.
        write_jsonl(artifacts.generated_jsonl, out)

        # Summary (small, for aggregation)
        write_summary(artifacts.summary_file, summary)
        write_summary_csv(artifacts.summary_csv, summary_row)
        write_manifest(artifacts, summary=summary)

        log_stage(f"output total={len(out)} slot_counts={_slot_counts}")
    else:
        emit_records(out, output)
        write_summary(output, summary)

    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Clean unified-L2 pipeline entry point")
    p.add_argument("--initial-qa", action="append", default=[], help="Existing QA json/jsonl for initial coverage")
    p.add_argument("--initial-coverage-llm", action="store_true", help="Use LLM to infer coverage footprint for original QA")
    p.add_argument("--plan", type=str, default="full", help="llm_ping|prepare_scene_graph|prepare_initial_coverage|generate|full")
    p.add_argument("--use-llm", action="store_true")
    p.add_argument("--concurrency", type=int, default=4)

    p.add_argument("--scene-id", type=str, default="global")
    p.add_argument("--frame-id", type=str, default="all")

    p.add_argument("--output", type=str, default="")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument(
        "--selection-policy",
        choices=("advtest", "random_full"),
        default="advtest",
        help="ADVTEST coverage-guided selection or coverage-blind random full coverage",
    )
    p.add_argument(
        "--random-run-id",
        type=str,
        default="",
        help="Isolate random_full checkpoints and summaries for one formal run.",
    )
    p.add_argument("--checkpoint-interval", type=int, default=1000)
    p.add_argument(
        "--max-draws",
        type=int,
        default=None,
        help="Watchdog only; reaching it is a failed/incomplete random run",
    )

    p.add_argument("--plan-file", type=str, default="")
    p.add_argument("--frame-index", type=int, default=0)

    p.add_argument("--artifact-root", type=str, default="", help="Directory for staged v7 artifacts")

    args = p.parse_args()
    output = Path(args.output) if args.output else None
    plan = args.plan.strip().lower()

    if plan:
        if not args.artifact_root:
            p.error("planned execution requires --artifact-root")
        root = Path(args.artifact_root)
        initial_qa = default_initial_qa_paths() + [Path(p) for p in args.initial_qa]
        initial_coverage_env = os.environ.get("ADVTEST_INITIAL_COVERAGE_LLM", read_env_file_value("ADVTEST_INITIAL_COVERAGE_LLM") or "")
        initial_coverage_llm = args.initial_coverage_llm or truthy(initial_coverage_env)
        log_stage(f"config ADVTEST_ORIGINAL_QA={read_env_file_value('ADVTEST_ORIGINAL_QA') or os.environ.get('ADVTEST_ORIGINAL_QA', '')}")
        log_stage(f"config ADVTEST_INITIAL_COVERAGE_LLM={initial_coverage_env!r} resolved={initial_coverage_llm}")
        scene_id = args.scene_id
        frame_id = args.frame_id
        if plan == "llm_ping":
            advtest_env.load_advtest_env()
            try:
                llm_ping(LLMClient.from_env())
            except Exception as exc:
                print(f"[v7][offline] ERROR {exc}", flush=True)
                raise SystemExit(2)
            return

        scene_graph_source = None

        if args.plan_file:
            frame_meta = load_frame_from_plan(Path(args.plan_file), frame_index=args.frame_index)
            scene_id = str(frame_meta["scene_id"])
            frame_id = str(frame_meta["frame_id"])
            initial_qa.extend(resolve_initial_qa_paths(frame_meta, Path(args.plan_file)))

            try:
                scene_graph_source = resolve_scene_graph_path(frame_meta, Path(args.plan_file))
            except (FileNotFoundError, ValueError):
                scene_graph_source = generate_scene_graph_from_legacy(frame_meta, Path(args.plan_file))


        gap_limit = 0
        if plan == "prepare_scene_graph":
            plan_prepare_scene_graph(root, scene_id=scene_id, frame_id=frame_id, gap_limit=gap_limit, scene_graph_source=scene_graph_source)
        elif plan == "prepare_initial_coverage":
            plan_prepare_initial_coverage(root, scene_id=scene_id, frame_id=frame_id, initial_qa=initial_qa, use_llm=initial_coverage_llm, concurrency=args.concurrency)
        elif plan == "generate":
            run_neo4j(
                output,
                seed=args.seed,
                artifact_root=root,
                scene_id=scene_id,
                frame_id=frame_id,
                use_llm=args.use_llm,
                selection_policy=args.selection_policy,
                random_run_id=args.random_run_id,
                checkpoint_interval=args.checkpoint_interval,
                max_draws=args.max_draws,
            )
        elif plan == "full":
            run_offline_artifacts(root, scene_id=scene_id, frame_id=frame_id, gap_limit=gap_limit, initial_qa=initial_qa, scene_graph_source=scene_graph_source, initial_coverage_llm=initial_coverage_llm, concurrency=args.concurrency)
            run_neo4j(
                output,
                seed=args.seed,
                artifact_root=root,
                scene_id=scene_id,
                frame_id=frame_id,
                use_llm=args.use_llm,
                selection_policy=args.selection_policy,
                random_run_id=args.random_run_id,
                checkpoint_interval=args.checkpoint_interval,
                max_draws=args.max_draws,
            )
        else:
            p.error("Unknown --plan value")
        return

    p.error("Use --plan full")


if __name__ == "__main__":
    main()
