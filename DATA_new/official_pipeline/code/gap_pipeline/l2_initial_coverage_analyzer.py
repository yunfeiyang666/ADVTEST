"""Initial coverage extraction from existing QA files for v7 unified L2."""
from __future__ import annotations

import json
import ast
import csv
import os
import re

from datetime import datetime, timezone

from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed


from pathlib import Path
from typing import Any, Dict, Iterable, List

from gap_pipeline.l2_artifacts import write_coverage_state, write_jsonl


from gap_pipeline.l2_question_graph import QuestionGraph
from gap_pipeline.l2_neo4j_coverage import footprint_from_cypher


def _loads_maybe(value: Any) -> Any:
    if not isinstance(value, str) or not value.strip():
        return value
    text = value.strip()
    try:
        return json.loads(text)
    except Exception:
        try:
            return ast.literal_eval(text)
        except Exception:
            return value



def _footprint_from_explicit_graph(nodes: Iterable[str], edges: Iterable[tuple[str, str]], *, family: str = "initial_coverage") -> Dict[str, Any]:
    graph = QuestionGraph(template_family=family)
    for node in nodes:
        graph.add_node(str(node))
    for a, b in edges:
        graph.add_edge(str(a), str(b), source="original_qa")
    return graph.footprint().as_dict()

from gap_pipeline.l2_gap_selector import L2CoverageState, l1_key, l2_key



_RECORD_CACHE: Dict[str, List[Dict[str, Any]]] = {}

def _default_sample_map_path() -> Path | None:
    raw = os.environ.get("ADVTEST_SAMPLE_TOKEN_MAP")
    if raw:
        return Path(raw)
    root = os.environ.get("ADVTEST_ROOT")
    if root:
        candidate = Path(root) / "data" / "test6019_bundle" / "sample_token_to_scene.json"
        if candidate.exists():
            return candidate
    return None


def _load_sample_token_map(path: Path | None = None) -> Dict[str, Dict[str, Any]]:
    path = path or _default_sample_map_path()
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}



def _read_records(path: Path) -> Iterable[Dict[str, Any]]:
    key = str(path.resolve())
    if key in _RECORD_CACHE:
        return _RECORD_CACHE[key]
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            records = [{k: _loads_maybe(v) for k, v in row.items()} for row in csv.DictReader(f)]
    elif path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        payload = json.loads(text)
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = []
            for field in ("records", "questions", "qa", "data"):
                if isinstance(payload.get(field), list):
                    records = payload[field]
                    break
            if not records:
                records = [payload]
        else:
            records = []
    _RECORD_CACHE[key] = records
    return records


def _footprint_from_record(record: Dict[str, Any]) -> Dict[str, Any]:
    fp = record.get("coverage_footprint")
    if isinstance(fp, dict):
        return {"l0": list(fp.get("l0", [])), "l1": list(fp.get("l1", [])), "l2": list(fp.get("l2", []))}
    l0_nodes = record.get("l0_nodes") or record.get("L0_Nodes")
    l1_edges = record.get("l1_edges") or record.get("L1_Edges")
    l2_paths = record.get("l2_paths") or record.get("L2_Paths")
    if isinstance(l0_nodes, list) or isinstance(l1_edges, list) or isinstance(l2_paths, list):
        l0_set = {str(x) for x in (l0_nodes or [])}
        edge_pairs = []
        for e in (l1_edges or []):
            if isinstance(e, dict):
                a, b = str(e.get("source")), str(e.get("target"))
                edge_pairs.append((a, b))
                l0_set.update([a, b])
        l0 = sorted(l0_set)
        l1 = sorted({l1_key(a, b) for a, b in edge_pairs} | {str(e) for e in (l1_edges or []) if not isinstance(e, dict)})
        l2: List[str] = []
        for item in (l2_paths or []):
            if isinstance(item, dict):
                ids = item.get("nodes") or item.get("path") or []
                if len(ids) == 3:
                    l2.append(l2_key(str(ids[0]), str(ids[1]), str(ids[2])))
            elif isinstance(item, list) and len(item) == 3:
                l2.append(l2_key(str(item[0]), str(item[1]), str(item[2])))
            else:
                l2.append(str(item))
        if not l2 and edge_pairs:
            return _footprint_from_explicit_graph(l0, edge_pairs)
        return {"l0": l0, "l1": l1, "l2": l2}

    path = record.get("path_pattern") or record.get("Footprint_Nodes") or record.get("footprint_nodes")
    if isinstance(path, list):
        ids = [str(x) for x in path]
    elif isinstance(path, str) and "|" in path:
        ids = [p for p in path.split("|") if p]
    else:
        ids = []
    if len(ids) == 3:
        a, b, c = ids
        return {"l0": [a, b, c], "l1": [l1_key(a, b), l1_key(b, c)], "l2": [l2_key(a, b, c)]}
    if len(ids) == 2:
        a, b = ids
        return {"l0": [a, b], "l1": [l1_key(a, b)], "l2": []}
    if len(ids) == 1:
        return {"l0": ids, "l1": [], "l2": []}
    return {"l0": [], "l1": [], "l2": []}



def _norm_text(value: Any) -> str:
    return str(value or "").lower().replace("_", " ").replace("-", " ").strip()


def _node_id(node: Dict[str, Any]) -> str:
    return str(node.get("unique_id") or node.get("id") or "")


def _node_type_text(node: Dict[str, Any]) -> str:
    return _norm_text(" ".join(str(node.get(k) or "") for k in ("unique_id", "type", "category", "status")))


def _load_ground_graph(path: Path | None) -> Dict[str, Any]:
    if not path or not path.exists():
        return {"nodes": [], "edges": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _matches_type(node: Dict[str, Any], label: str) -> bool:
    text = _node_type_text(node)
    label = _norm_text(label)
    if label in {"thing", "things", "object", "objects"}:
        return _node_id(node) != "ego"
    aliases = {
        "cars": "car", "traffic cones": "traffic cone", "pedestrians": "pedestrian",
        "buss": "bus", "busses": "bus", "buses": "bus",
        "trucks": "truck", "bicycles": "bicycle", "motorcycles": "motorcycle",
        "barriers": "barrier", "trailers": "trailer",
        "construction vehicles": "construction vehicle",
        "construction_vehicle": "construction vehicle",
        "traffic_cone": "traffic cone",
    }
    label = aliases.get(label, label)
    # Also check category field for NuScenes-style categories
    category = _norm_text(str(node.get("category") or ""))
    if label == "traffic cone" and ("trafficcone" in category or "traffic_cone" in text or "traffic cone" in text):
        return True
    if label == "construction vehicle" and ("construction" in category or "construction" in text):
        return True
    return label in text


def _matches_status(node: Dict[str, Any], status: str) -> bool:
    status = _norm_text(status)
    if not status:
        return True
    text = _node_type_text(node)
    node_status = _norm_text(str(node.get("status") or ""))
    if status == "not standing":
        return node_status != "standing" and "pedestrian" in text
    # Normalize status aliases
    status_aliases = {
        "without rider": "without_rider",
        "with rider": "with_rider",
    }
    status = status_aliases.get(status, status)
    # Check both the combined text and the node_status field directly
    if status.replace(" ", "_") == node_status.replace(" ", "_"):
        return True
    return status in text


def _edge_relation(edge: Dict[str, Any]) -> str:
    vals = [edge.get("direction_6"), edge.get("direction_official")] + (edge.get("predicates") or [])
    return " ".join(_norm_text(v) for v in vals if v)


def _edges_from(graph: Dict[str, Any], source: str, relation: str = "") -> List[Dict[str, Any]]:
    rel = _norm_text(relation)
    out = []
    for edge in graph.get("edges") or graph.get("relationships") or []:
        if str(edge.get("source")) != source:
            continue
        if rel and rel not in _edge_relation(edge):
            continue
        out.append(edge)
    return out


def _footprint_from_directed_edges(nodes: Iterable[str], edges: Iterable[Dict[str, Any]], *, status: str) -> Dict[str, Any]:
    edge_pairs = [(str(e.get("source")), str(e.get("target"))) for e in edges if e.get("source") and e.get("target")]
    l0 = sorted({str(x) for x in nodes if x} | {x for pair in edge_pairs for x in pair})
    fp = _footprint_from_explicit_graph(l0, edge_pairs, family="initial_deterministic")
    fp["_grounding_status"] = status
    fp["_grounded_nodes"] = l0
    fp["_grounded_edges"] = [f"{a}|{b}" for a, b in edge_pairs]
    return fp


def _find_anchor_by_relation_count(graph: Dict[str, Any], *, anchor_type: str, anchor_status: str, relation: str, expected_count: int) -> tuple[Dict[str, Any] | None, List[Dict[str, Any]]]:
    candidates = [n for n in graph.get("nodes", []) if _matches_type(n, anchor_type) and _matches_status(n, anchor_status)]
    matches: List[tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    for anchor in candidates:
        edges = _edges_from(graph, _node_id(anchor), relation)
        non_ego_edges = [e for e in edges if str(e.get("target")) != "ego"]
        if len(non_ego_edges) == expected_count:
            matches.append((anchor, non_ego_edges))
    if len(matches) == 1:
        return matches[0]
    return None, []




def _answer_to_int(answer: str) -> int | None:
    try:
        return int(str(answer).strip())
    except Exception:
        return None


def _parse_direction(text: str) -> str:
    """Extract direction_6 keyword from question text."""
    text = text.replace("_", " ")
    # Order matters: longer patterns first (compound directions before simple)
    for phrase, d6 in [
        ("to the front left of", "front_left"), ("to the front right of", "front_right"),
        ("to the back left of", "back_left"), ("to the back right of", "back_right"),
        ("front left", "front_left"), ("front right", "front_right"),
        ("back left", "back_left"), ("back right", "back_right"),
        ("to the front of", "front"), ("to the back of", "back"),
        ("to the left of", "front_left"), ("to the right of", "front_right"),
        ("in front of", "front"), ("behind", "back"),
    ]:
        if phrase in text:
            return d6
    return ""


def _parse_type_status(text: str) -> tuple[str, str]:
    """Extract (type, status) from a NuScenesQA noun phrase like 'moving car', 'parked thing', 'not standing pedestrian'."""
    text = _norm_text(text)
    # Strip leading "other" (e.g. "other buss" → "buss")
    if text.startswith("other "):
        text = text[6:].strip()
    status = ""
    # Order matters: longer compound phrases first
    if "without rider" in text:
        status = "without_rider"
        text = text.replace("without rider", "").strip()
    elif "with rider" in text:
        status = "with_rider"
        text = text.replace("with rider", "").strip()
    elif "not standing" in text:
        status = "not standing"
        text = text.replace("not standing", "").strip()
    elif "standing" in text:
        status = "standing"
        text = text.replace("standing", "").strip()
    elif "moving" in text:
        status = "moving"
        text = text.replace("moving", "").strip()
    elif "parked" in text:
        status = "parked"
        text = text.replace("parked", "").strip()
    elif "stopped" in text:
        status = "stopped"
        text = text.replace("stopped", "").strip()
    # Remaining text is the type
    obj_type = text.strip()
    if obj_type in ("thing", "things", "object", "objects", "it"):
        obj_type = ""  # any type
    return obj_type, status


def _find_objects(nodes: Dict[str, Dict[str, Any]], obj_type: str, status: str) -> List[str]:
    """Find objects matching type and status constraints."""
    result = []
    for uid, n in nodes.items():
        if uid == "ego":
            continue
        if obj_type and not _matches_type(n, obj_type):
            continue
        if status == "not standing":
            if not _matches_status(n, "not standing"):
                continue
        elif status and not _matches_status(n, status):
            continue
        result.append(uid)
    return result


def _find_targets_by_direction(graph: Dict[str, Any], source: str, direction: str,
                                nodes: Dict[str, Dict[str, Any]],
                                target_type: str = "", target_status: str = "") -> tuple[List[str], List[tuple[str, str]]]:
    """Find targets from source in given direction, optionally filtered by type/status.
    Returns (target_ids, edge_pairs)."""
    edges = _edges_from(graph, source, direction)
    targets = []
    pairs = []
    for e in edges:
        tgt = str(e.get("target") or "")
        if tgt not in nodes or tgt == "ego":
            continue
        if target_type and not _matches_type(nodes.get(tgt, {}), target_type):
            continue
        if target_status == "not standing":
            if not _matches_status(nodes.get(tgt, {}), "not standing"):
                continue
        elif target_status and not _matches_status(nodes.get(tgt, {}), target_status):
            continue
        targets.append(tgt)
        pairs.append((source, tgt))
    return targets, pairs


def _ground_original_question(record: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any] | None:
    """Deterministic grounding of NuScenesQA questions using scene graph.
    
    Produces coverage_footprint with proper L0/L1 using the same edge format
    as the generation phase. L2 is computed automatically by QuestionGraph.footprint()
    from the adjacency of L1 edges (requires 2+ edges sharing a pivot node).
    """
    q = _norm_text(record.get("question"))
    answer = _norm_text(record.get("answer"))
    template_type = record.get("template_type", "")
    num_hop = record.get("num_hop", 0)
    all_nodes = {_node_id(n): n for n in (graph.get("nodes") or graph.get("objects") or []) if _node_id(n)}
    if not all_nodes:
        return None

    def fp(ids: List[str], edge_pairs: List[tuple[str, str]], status: str, computed: Any = "") -> Dict[str, Any]:
        base: Dict[str, Any] = _footprint_from_explicit_graph(ids, edge_pairs, family="initial_coverage_grounded")
        base["_grounding_status"] = status
        base["_computed_answer"] = str(computed)
        return base

    # ── 0-hop: no spatial relations ──
    if num_hop == 0:
        # "Are any X visible?" / "What number of X?" / pure existence/count
        # No spatial edge → L0 only (the specific objects), no L1/L2
        if template_type == "exist":
            # Parse: "Are any [status] [type] visible?"
            q_clean = q.replace("are any ", "").replace("are there any ", "").replace(" visible?", "").replace(" visible", "").strip().rstrip("?")
            obj_type, status_filter = _parse_type_status(q_clean)
            matched = _find_objects(all_nodes, obj_type, status_filter)
            answer_bool = answer in ("yes", "true")
            computed_bool = len(matched) > 0
            if answer_bool == computed_bool:
                return fp(matched if answer_bool else [], [], "answer_match", computed_bool)
            else:
                return fp([], [], "answer_mismatch", computed_bool)

        if template_type == "count":
            # "What number of X are there?" / "How many X?"
            q_clean = q.replace("what number of ", "").replace("how many ", "").replace(" are there?", "").replace(" are there", "").strip().rstrip("?")
            obj_type, status_filter = _parse_type_status(q_clean)
            matched = _find_objects(all_nodes, obj_type, status_filter)
            expected = _answer_to_int(answer)
            if expected is not None and len(matched) == expected:
                return fp(matched, [], "answer_match", len(matched))
            else:
                return fp([], [], "answer_mismatch", len(matched))

        # Other 0-hop: generic, just mark ego
        return fp([], [], "0hop_unmatched")

    # ── 1-hop: anchor → direction → target(s) ──
    # Parse direction from question
    direction = _parse_direction(q)
    if not direction:
        return None  # can't parse spatial relation

    # Determine anchor: "of me" → ego, "of the [status] [type]" → find object
    anchor_id = None
    target_type = ""
    target_status = ""

    if "of me" in q:
        anchor_id = "ego"
    else:
        # Strategy 1: "to the [dir] of the [status] [type]" — most common
        m = re.search(r"(?:to the \w+(?:\s+\w+)? of|of) the (.+?)(?:\?|;|$)", q)
        if m:
            anchor_desc = m.group(1).strip()
            anchor_type, anchor_status = _parse_type_status(anchor_desc)
            candidates = _find_objects(all_nodes, anchor_type, anchor_status)
            if len(candidates) == 1:
                anchor_id = candidates[0]
            elif len(candidates) > 1:
                anchor_id = candidates[0]  # take first as best effort

        # Strategy 2: "There is a [status] [type]; ...of it?" — indirect anchor
        if not anchor_id and "of it" in q:
            m_there = re.search(r"there is a (.+?)[;,]", q)
            if m_there:
                anchor_desc = m_there.group(1).strip()
                # Remove trailing spatial phrase if present: "...that is to the front of the X"
                anchor_desc = re.sub(r"\s+(?:that is |)to the .*", "", anchor_desc).strip()
                anchor_type, anchor_status = _parse_type_status(anchor_desc)
                candidates = _find_objects(all_nodes, anchor_type, anchor_status)
                if len(candidates) == 1:
                    anchor_id = candidates[0]
                elif len(candidates) > 1:
                    anchor_id = candidates[0]

        # Strategy 3: "The [desc] to the [dir] of the [anchor] is what?" — subject-position anchor
        if not anchor_id:
            m_subj = re.search(r"(?:the .+? (?:that is )?to the \w+(?:\s+\w+)? of) the (.+?)(?:\s+is\b|\?|$)", q)
            if m_subj:
                anchor_desc = m_subj.group(1).strip()
                anchor_type, anchor_status = _parse_type_status(anchor_desc)
                candidates = _find_objects(all_nodes, anchor_type, anchor_status)
                if len(candidates) == 1:
                    anchor_id = candidates[0]
                elif len(candidates) > 1:
                    anchor_id = candidates[0]

    if not anchor_id:
        return None

    # ── exist: "Are there any [target_type] to the [dir] of [anchor]?" ──
    if template_type == "exist":
        # Parse target type from beginning: "are there any [status] [type] to the..."
        m = re.search(r"(?:are there any|are any|is there another)\s+(.+?)\s+(?:that is |)to the", q)
        if m:
            target_type, target_status = _parse_type_status(m.group(1))
        targets, pairs = _find_targets_by_direction(graph, anchor_id, direction, all_nodes, target_type, target_status)
        answer_bool = answer in ("yes", "true")
        computed_bool = len(targets) > 0
        if answer_bool == computed_bool:
            ids = [anchor_id] + targets if answer_bool else [anchor_id]
            return fp(ids, pairs if answer_bool else [], "answer_match", computed_bool)
        else:
            return fp([anchor_id], [], "answer_mismatch", computed_bool)

    # ── count: "How many [type] are to the [dir] of [anchor]?" ──
    if template_type == "count":
        m = re.search(r"(?:what number of|how many)\s+(.+?)\s+(?:are |is )?to the", q)
        if not m:
            # "There is a X; what number of things are to the [dir] of it?"
            m = re.search(r"(?:what number of|how many)\s+(.+?)\s+(?:are |is )?to the", q)
        if m:
            target_type, target_status = _parse_type_status(m.group(1))
        targets, pairs = _find_targets_by_direction(graph, anchor_id, direction, all_nodes, target_type, target_status)
        expected = _answer_to_int(answer)
        if expected is not None and len(targets) == expected:
            return fp([anchor_id] + targets, pairs, "answer_match", len(targets))
        else:
            return fp([anchor_id], [], "answer_mismatch", len(targets))

    # ── object: "There is a [type] to the [dir] of [anchor]; what is it?" ──
    if template_type == "object":
        # Parse target description
        m = (re.search(r"there is a (.+?) (?:that is )?(?:both )?to the", q)
             or re.search(r"the (.+?) (?:that is )?to the", q))
        if m:
            target_type, target_status = _parse_type_status(m.group(1))
        targets, pairs = _find_targets_by_direction(graph, anchor_id, direction, all_nodes, target_type, target_status)
        # answer should be a type name
        # Normalize answer for matching (e.g. "construction vehicle" → "construction_vehicle")
        answer_norm = answer.replace(" ", "_")
        matched_answer = [t for t in targets if _matches_type(all_nodes.get(t, {}), answer) or _matches_type(all_nodes.get(t, {}), answer_norm)]
        if matched_answer:
            return fp([anchor_id] + matched_answer, [(anchor_id, t) for t in matched_answer], "answer_match", answer)
        elif targets:
            return fp([anchor_id] + targets, pairs, "answer_partial", [all_nodes.get(t, {}).get("type") for t in targets])
        else:
            return fp([anchor_id], [], "answer_mismatch", "no_targets")

    # ── status: "What is the status of the [type] to the [dir] of [anchor]?" ──
    if template_type == "status":
        m = (re.search(r"(?:status of |status is )?the (.+?) (?:that is )?to the", q)
             or re.search(r"there is a (.+?) to the", q)
             or re.search(r"the (.+?) to the", q))
        if m:
            target_type, target_status_dummy = _parse_type_status(m.group(1))
        targets, pairs = _find_targets_by_direction(graph, anchor_id, direction, all_nodes, target_type, "")
        # Normalize answer status for comparison
        answer_n = answer.replace(" ", "_")
        matched_status = [t for t in targets if _norm_text(all_nodes.get(t, {}).get("status", "")).replace(" ", "_") == answer_n or _norm_text(all_nodes.get(t, {}).get("status", "")) == answer]
        if matched_status:
            return fp([anchor_id] + matched_status, [(anchor_id, t) for t in matched_status], "answer_match", answer)
        elif targets:
            return fp([anchor_id] + targets, pairs, "answer_partial", [all_nodes.get(t, {}).get("status") for t in targets])
        else:
            return fp([anchor_id], [], "answer_mismatch", "no_targets")

    # ── comparison: involves 2 spatial paths from same/different anchors ──
    if template_type == "comparison":
        # Parse comparison structure: extract the two objects being compared and their spatial edges
        # Pattern 1: "Does the X have the same status as the Y to the [dir] of the [anchor]?"
        # Pattern 2: "There is a X to the [dir] of the Y; is its status the same as the Z?"
        # Pattern 3: "Does the X to the [dir1] of the [anchor1] have the same status as the Y to the [dir2] of the [anchor2]?"
        comp_targets = []
        comp_pairs = []

        # Extract ALL spatial references in the question
        # Find all "[type] to the [dir] of the [anchor]" patterns
        spatial_refs = re.findall(r"(?:the |a )(.+?)\s+(?:that is )?to the\s+(\w+(?:\s+\w+)?)\s+of\s+(?:the |)(.+?)(?:\?|;|,|$)", q)
        for target_desc, dir_text, anchor_desc in spatial_refs:
            ref_dir = _parse_direction(f"to the {dir_text} of")
            if not ref_dir:
                continue
            t_type, t_status = _parse_type_status(target_desc)
            a_type, a_status = _parse_type_status(anchor_desc)
            # Find anchor
            a_candidates = _find_objects(all_nodes, a_type, a_status)
            for a_cand in a_candidates:
                tgts, prs = _find_targets_by_direction(graph, a_cand, ref_dir, all_nodes, t_type, t_status)
                if tgts:
                    comp_targets.extend(tgts)
                    comp_pairs.extend(prs)
                    comp_targets.append(a_cand)
                    break

        if not comp_targets:
            # Fallback: find edges from anchor in the mentioned direction
            for d6 in ["front_left", "front_right", "back_left", "back_right", "front", "back"]:
                if d6.replace("_", " ") in q:
                    targets, pairs = _find_targets_by_direction(graph, anchor_id, d6, all_nodes)
                    # Only take the first matching target, not all
                    if targets:
                        comp_targets.append(targets[0])
                        comp_pairs.append(pairs[0])
                        break

        if comp_targets:
            all_ids = list(set([anchor_id] + comp_targets))
            return fp(all_ids, list(set(comp_pairs)), "comparison_grounded", answer)
        else:
            return fp([anchor_id], [], "comparison_no_targets", answer)

    return None




def _footprint_relevant_scene_context(record: Dict[str, Any], graph: Dict[str, Any] | None, base_context: str, *, max_edges: int = 80) -> str:
    if not graph:
        return base_context
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or graph.get("relationships") or []
    question = _norm_text(record.get("question") or record.get("Question") or "")
    answer = _norm_text(record.get("answer") or record.get("Answer") or "")
    terms = {t for t in ["car", "truck", "barrier", "traffic", "cone", "pedestrian", "thing", "object", "moving", "stopped", "parked", "standing", "sitting"] if t in question or t in answer}
    direction_terms = [d for d in ["front_left", "front_right", "back_left", "back_right", "front", "back"] if d in question.replace(" ", "_")]
    relevant_ids: set[str] = set()
    for n in nodes:
        text = _norm_text(" ".join(str(n.get(k) or "") for k in ("unique_id", "type", "category", "status")))
        if not terms or any(t in text for t in terms):
            relevant_ids.add(str(n.get("unique_id")))
    rel_lines: List[str] = []
    for e in edges:
        src = str(e.get("source")); tgt = str(e.get("target")); direction = str(e.get("direction_6") or "")
        if direction_terms and direction not in direction_terms:
            continue
        if src in relevant_ids or tgt in relevant_ids:
            rel_lines.append(f"{src}->{tgt}: direction_6={direction}")
        if len(rel_lines) >= max_edges:
            break
    if not rel_lines:
        return base_context
    return base_context + "\nRelevant relation edges:\n" + "\n".join(rel_lines)

def _footprint_from_llm(record: Dict[str, Any], *, llm_client: Any, object_ids: List[str], scene_context: str = "", graph: Dict[str, Any] | None = None) -> Dict[str, Any]:
    question = record.get("question") or record.get("Question") or record.get("Q") or ""
    answer = record.get("answer") or record.get("Answer") or record.get("A") or ""
    enforce_caps = _norm_text(os.environ.get("LLM_FOOTPRINT_ENFORCE_CAPS") or "false") in {"1", "true", "yes"}
    max_nodes = int(os.environ.get("LLM_FOOTPRINT_MAX_NODES") or 9999)
    max_edges = int(os.environ.get("LLM_FOOTPRINT_MAX_EDGES") or 9999)
    no_max_edges = int(os.environ.get("LLM_FOOTPRINT_NO_MAX_EDGES") or 9999)
    prompt = (
        "Extract the TRUE initial coverage footprint for an autonomous-driving QA item. Correctness is more important than efficiency. "
        "You are NOT answering the question and NOT writing Cypher.\n"
        "Return strict JSON only with schema: {\"status\":\"grounded|unresolved|ambiguous|inconsistent\", \"nodes\":[\"id\"], \"edges\":[[\"source\",\"target\"]], \"reason\":\"...\"}.\n"
        "Meaning of coverage: nodes and directed relation edges from the provided scene graph that are actually and explicitly needed to justify the given QA pair.\n"
        "Rules:\n"
        "1. Use only object IDs listed in available_object_ids.\n"
        "2. Use only directed edges explicitly listed in scene_context.\n"
        "3. Preserve all constraints in the question, especially object type, status, direction, and uniqueness words like 'the' or 'another'. Do not relax 'parked car' to all cars.\n"
        "4. Use schema aliases: traffic cone / traffic cones match objects whose type is traffic_cone OR whose category contains trafficcone OR whose type is barrier and category contains trafficcone; car matches type car or category vehicle.car.\n"
        "5. If a required anchor object does not exist in the scene graph, return status='unresolved' with empty nodes and edges.\n"
        "5. If the provided answer conflicts with the scene graph evidence, return status='inconsistent' with empty nodes and edges.\n"
        "6. If multiple objects satisfy a singular definite anchor and the question cannot identify one, return status='ambiguous'.\n"
        "7. For answer='no', do NOT include all failed/negative candidates. Include only positive evidence that is actually checked and grounded; if the key anchor is absent, return unresolved.\n"
        "8. For count/list questions, include all graph nodes/edges actually counted or listed, even if there are many.\n"
        "9. Do not try to maximize coverage. Do not include background or merely possible candidates.\n"
        f"available_object_ids={object_ids}\n"
        f"scene_context={scene_context}\n"
        f"question={question}\nanswer={answer}"
    )
    data = llm_client._post_json("/chat/completions", {
        "model": llm_client.model,
        "messages": [
            {"role": "system", "content": "Return strict JSON only. Do not explain."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": int(os.environ.get("LLM_FOOTPRINT_MAX_TOKENS") or os.environ.get("LLM_COVERAGE_MAX_TOKENS") or 512),
        "chat_template_kwargs": {"enable_thinking": False},
        "_timeout_seconds": int(os.environ.get("LLM_FOOTPRINT_TIMEOUT_SECONDS") or os.environ.get("LLM_COVERAGE_TIMEOUT_SECONDS") or 45),
        "_retries": int(os.environ.get("LLM_FOOTPRINT_RETRIES") or os.environ.get("LLM_COVERAGE_RETRIES") or 0),
    })
    msg = data.get("choices", [{}])[0].get("message", {})
    text = msg.get("content") or msg.get("reasoning_content") or ""
    raw_text = str(text)[:2000]
    try:
        clean = str(text).strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        payload = json.loads(clean)
    except Exception:
        payload = {}

    valid_nodes = set(object_ids)
    valid_edges = {(str(e.get("source")), str(e.get("target"))) for e in ((graph or {}).get("edges") or (graph or {}).get("relationships") or [])}
    status = str(payload.get("status") or "grounded").lower()
    reason = str(payload.get("reason") or "")
    requested_nodes = payload.get("nodes") or payload.get("l0") or []
    l0 = {str(x) for x in requested_nodes if str(x) in valid_nodes}
    edges: List[tuple[str, str]] = []
    for item in payload.get("edges") or payload.get("l1") or []:
        if isinstance(item, dict):
            pair = (str(item.get("source")), str(item.get("target")))
        elif isinstance(item, list) and len(item) == 2:
            pair = (str(item[0]), str(item[1]))
        else:
            parts = str(item).replace("|", "->").split("->")
            pair = (parts[0], parts[1]) if len(parts) == 2 else ("", "")
        if pair[0] in valid_nodes and pair[1] in valid_nodes and pair in valid_edges:
            l0.update(pair)
            edges.append(pair)

    rejected = status in {"unresolved", "ambiguous", "overbroad", "inconsistent"}
    if enforce_caps and (len(l0) > max_nodes or len(edges) > max_edges):
        rejected = True
        status = "overbroad"
        reason = reason or "footprint exceeds max_nodes/max_edges"
    if enforce_caps and _norm_text(answer) == "no" and len(edges) > no_max_edges:
        rejected = True
        status = "overbroad_negative"
        reason = reason or "no-answer footprint has too many edges"
    fp: Dict[str, Any] = _footprint_from_explicit_graph([], [], family="initial_coverage_llm_footprint") if rejected else _footprint_from_explicit_graph(l0, edges, family="initial_coverage_llm_footprint")
    fp["_llm_raw"] = raw_text
    fp["_llm_payload"] = payload
    fp["_llm_footprint_status"] = status
    fp["_llm_footprint_reason"] = reason
    fp["_grounded_nodes"] = sorted(l0)
    fp["_grounded_edges"] = [f"{a}|{b}" for a, b in edges]
    return fp


def analyze_initial_coverage(input_files: Iterable[Path], *, scene_id: str | None = None, frame_id: str | None = None, llm_client: Any | None = None, object_ids: List[str] | None = None, scene_context: str = "", ground_graph_path: Path | None = None, concurrency: int = 1) -> tuple[L2CoverageState, List[Dict[str, Any]]]:
    state = L2CoverageState()
    rows: List[Dict[str, Any]] = []
    sample_map = _load_sample_token_map()
    ground_graph = _load_ground_graph(ground_graph_path)
    llm_mode = (os.environ.get("ADVTEST_INITIAL_COVERAGE_MODE") or os.environ.get("LLM_INITIAL_COVERAGE_MODE") or "cypher").strip().lower()

    matched: List[tuple[Path, int, Dict[str, Any], Any]] = []

    for path in input_files:
        for idx, record in enumerate(_read_records(path)):
            rec_scene = record.get("scene_id") or record.get("scene_name") or record.get("Scene_ID")
            rec_frame = record.get("frame_id") or record.get("frame_idx") or record.get("Frame_ID")
            sample_token = record.get("sample_token") or record.get("sample") or record.get("token")
            if sample_token and sample_token in sample_map:
                mapped = sample_map.get(str(sample_token)) or {}
                rec_scene = rec_scene or mapped.get("scene_name") or mapped.get("scene_id")
                rec_frame = rec_frame if rec_frame is not None else mapped.get("frame_idx")
            if scene_id is not None and rec_scene is not None and str(rec_scene) != str(scene_id):
                continue
            if frame_id is not None and rec_frame is not None and str(rec_frame) != str(frame_id):
                continue
            matched.append((path, idx, record, sample_token))

    def build(item: tuple[Path, int, Dict[str, Any], Any], ordinal: int) -> Dict[str, Any]:
        path, idx, record, sample_token = item
        ts_start = datetime.now(timezone.utc).isoformat()
        error = ""
        deterministic = None
        try:
            # Primary: deterministic scene-graph grounding
            deterministic = dict(_ground_original_question(record, ground_graph) or {})
            has_det = bool(deterministic.get("l0") or deterministic.get("l1") or deterministic.get("l2"))

            if has_det:
                fp = deterministic
                status = f"DETERMINISTIC_{str(fp.get('_grounding_status') or 'grounded').upper()}"
            elif deterministic:
                # Matched but empty coverage (e.g. answer_mismatch, 0hop_unmatched)
                fp = deterministic
                status = f"DETERMINISTIC_{str(fp.get('_grounding_status') or 'empty').upper()}"
            elif llm_client:
                # Fallback: LLM if deterministic couldn't parse the template
                print(f"[v7][offline][init_coverage] deterministic failed, LLM fallback {ordinal}/{len(matched)}", flush=True)
                if llm_mode == "footprint":
                    fp = _footprint_from_llm(record, llm_client=llm_client, object_ids=object_ids or [], scene_context=scene_context, graph=ground_graph)
                else:
                    fp = footprint_from_cypher(record, llm_client)
                has_fp = bool(fp.get("l0") or fp.get("l1") or fp.get("l2"))
                status = "LLM_FALLBACK_GROUNDED" if has_fp else "LLM_FALLBACK_EMPTY"
            else:
                # No LLM, no deterministic match → empty
                fp = {"l0": [], "l1": [], "l2": []}
                status = "UNRESOLVED"
        except Exception as exc:
            print(f"[v7][offline][init_coverage] WARNING failed {ordinal}/{len(matched)}: {exc}", flush=True)
            fp = deterministic if deterministic else {"l0": [], "l1": [], "l2": []}
            status = "ERROR"
            error = str(exc)

        ts_end = datetime.now(timezone.utc).isoformat()
        return {"timestamp_start": ts_start, "timestamp_end": ts_end, "source_file": str(path), "index": idx, "question_id": record.get("question_id") or record.get("Question_ID") or "", "scene_id": scene_id or "", "frame_id": frame_id or "", "sample_token": sample_token or "", "question": record.get("question") or record.get("Question") or "", "answer": record.get("answer") or record.get("Answer") or "", "template_type": record.get("template_type") or "", "num_hop": record.get("num_hop") or "", "coverage_footprint": fp, "llm_status": status, "llm_error": error}

    # Run all items — deterministic is fast, no concurrency needed for primary path
    if llm_client and matched:
        print(f"[v7][offline][init_coverage] matched={len(matched)} (deterministic primary, LLM fallback)", flush=True)
        batch_timeout = int(os.environ.get("LLM_COVERAGE_BATCH_TIMEOUT_SECONDS") or max(60, len(matched) * int(os.environ.get("LLM_COVERAGE_TIMEOUT_SECONDS") or 45)))
        executor = ThreadPoolExecutor(max_workers=max(concurrency, 1))
        future_items = {executor.submit(build, item, i + 1): (item, i + 1) for i, item in enumerate(matched)}
        try:
            try:
                for fut in as_completed(future_items, timeout=batch_timeout):
                    rows.append(fut.result())
            except TimeoutError:
                print(f"[v7][offline][init_coverage] WARNING batch timeout after {batch_timeout}s", flush=True)
            for fut, (item, ordinal) in future_items.items():
                if fut.done():
                    continue
                fut.cancel()
                path, idx, record, sample_token = item
                ts = datetime.now(timezone.utc).isoformat()
                fp_empty: Dict[str, Any] = {"l0": [], "l1": [], "l2": []}
                rows.append({"timestamp_start": ts, "timestamp_end": ts, "source_file": str(path), "index": idx, "question_id": record.get("question_id") or record.get("Question_ID") or "", "scene_id": scene_id or "", "frame_id": frame_id or "", "sample_token": sample_token or "", "question": record.get("question") or record.get("Question") or "", "answer": record.get("answer") or record.get("Answer") or "", "template_type": record.get("template_type") or "", "num_hop": record.get("num_hop") or "", "coverage_footprint": fp_empty, "llm_status": "TIMEOUT", "llm_error": f"batch timeout ordinal={ordinal}"})
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    else:
        rows = [build(item, i + 1) for i, item in enumerate(matched)]

    for row in rows:
        fp = row["coverage_footprint"]
        before = (len(state.l0), len(state.l1), len(state.l2))
        state.mark(fp)
        after = (len(state.l0), len(state.l1), len(state.l2))
        row["delta"] = {"l0": after[0] - before[0], "l1": after[1] - before[1], "l2": after[2] - before[2]}

    # ── Phase 2: Infer L2 coverage from accumulated L1 edges ──
    # If L1 edges A|B and B|C both exist (sharing pivot B), then the L2 path A|B|C
    # is implicitly covered by the combination of original questions.
    from collections import defaultdict
    pivot_map: Dict[str, set] = defaultdict(set)  # node -> set of neighbors via L1
    for l1_k in state.l1:
        parts = l1_k.split("|")
        if len(parts) == 2:
            a, b = parts
            pivot_map[a].add(b)
            pivot_map[b].add(a)
    l2_before = len(state.l2)
    for pivot, neighbors in pivot_map.items():
        neighbors_list = sorted(neighbors)
        for i, u in enumerate(neighbors_list):
            for v in neighbors_list[i + 1:]:
                state.l2.add(l2_key(u, pivot, v))
    l2_inferred = len(state.l2) - l2_before
    if l2_inferred > 0:
        print(f"[v7][offline][init_coverage] L2 inferred from L1 edges: +{l2_inferred} (total L2={len(state.l2)})", flush=True)

    return state, rows



def _write_initial_coverage_csv(rows: List[Dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "timestamp_start", "timestamp_end", "scene_id", "frame_id", "sample_token",
        "question_id", "question", "answer", "template_type", "num_hop",
        "source_file", "index", "llm_status", "llm_error",
        "l0_count", "l1_count", "l2_count", "delta_l0", "delta_l1", "delta_l2",
        "l0_nodes", "l1_edges", "l2_paths", "grounded_nodes", "grounded_edges", "coverage_footprint", "llm_cypher", "llm_payload", "llm_raw",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            fp = row.get("coverage_footprint") or {}
            delta = row.get("delta") or {}
            writer.writerow({
                "timestamp_start": row.get("timestamp_start", ""),
                "timestamp_end": row.get("timestamp_end", ""),
                "scene_id": row.get("scene_id", ""),
                "frame_id": row.get("frame_id", ""),
                "sample_token": row.get("sample_token", ""),
                "question_id": row.get("question_id", ""),
                "question": row.get("question", ""),
                "answer": row.get("answer", ""),
                "template_type": row.get("template_type", ""),
                "num_hop": row.get("num_hop", ""),
                "source_file": row.get("source_file", ""),
                "index": row.get("index", ""),
                "llm_status": row.get("llm_status", ""),
                "llm_error": row.get("llm_error", ""),
                "l0_count": len(fp.get("l0") or []),
                "l1_count": len(fp.get("l1") or []),
                "l2_count": len(fp.get("l2") or []),
                "delta_l0": delta.get("l0", 0),
                "delta_l1": delta.get("l1", 0),
                "delta_l2": delta.get("l2", 0),
                "l0_nodes": json.dumps(fp.get("l0") or [], ensure_ascii=False),
                "l1_edges": json.dumps(fp.get("l1") or [], ensure_ascii=False),
                "l2_paths": json.dumps(fp.get("l2") or [], ensure_ascii=False),
                "coverage_footprint": json.dumps(fp, ensure_ascii=False),
                "grounded_nodes": json.dumps(fp.get("_grounded_nodes") or [], ensure_ascii=False),
                "grounded_edges": json.dumps(fp.get("_grounded_edges") or [], ensure_ascii=False),

                "llm_cypher": fp.get("_llm_cypher", ""),
                "llm_payload": json.dumps(fp.get("_llm_payload") or {}, ensure_ascii=False),
                "llm_raw": fp.get("_llm_raw", ""),
            })


def export_initial_coverage(input_files: Iterable[Path], jsonl_path: Path, state_path: Path | None = None, *, scene_id: str | None = None, frame_id: str | None = None, llm_client: Any | None = None, object_ids: List[str] | None = None, scene_context: str = "", ground_graph_path: Path | None = None, concurrency: int = 1) -> Dict[str, Any]:
    state, rows = analyze_initial_coverage(input_files, scene_id=scene_id, frame_id=frame_id, llm_client=llm_client, object_ids=object_ids, scene_context=scene_context, ground_graph_path=ground_graph_path, concurrency=concurrency)
    write_jsonl(jsonl_path, rows)
    if state_path:
        write_coverage_state(state_path, state)
    csv_path = jsonl_path.with_suffix(".csv")
    try:
        _write_initial_coverage_csv(rows, csv_path)
    except PermissionError as exc:
        print(f"[v7][offline] WARNING skip initial coverage CSV because it is locked: {csv_path} ({exc})", flush=True)

    status_counts: Dict[str, int] = {}
    for row in rows:
        status = str(row.get("llm_status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {"records": len(rows), "coverage": {"l0": len(state.l0), "l1": len(state.l1), "l2": len(state.l2)}, "status_counts": status_counts}

