from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict

import advtest_env

advtest_env.load_advtest_env()
_base = (os.environ.get("NEO4J_HTTP_URL") or "http://127.0.0.1:7474").rstrip("/")
URL = f"{_base}/db/neo4j/tx/commit"
_user = os.environ.get("NEO4J_USER") or "neo4j"
_password = os.environ.get("NEO4J_PASSWORD") or "87017563"
AUTH = "Basic " + base64.b64encode(f"{_user}:{_password}".encode()).decode()


def post(statements):
    data = json.dumps({"statements": statements}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(URL, data=data, headers={"Content-Type": "application/json", "Authorization": AUTH})
    timeout = int(os.environ.get("NEO4J_IMPORT_TIMEOUT_SECONDS") or os.environ.get("NEO4J_HTTP_TIMEOUT_SECONDS") or 30)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload


def flat_node(o: Dict[str, Any]) -> Dict[str, Any]:
    trans = o.get("translation") or {}
    vel = o.get("velocity") or {}
    size = o.get("size") or {}
    return {
        "unique_id": o.get("unique_id") or o.get("id"),
        "type": o.get("type") or o.get("category") or "object",
        "category": o.get("category") or "",
        "status": o.get("status") or "",
        "is_ego": (o.get("type") == "ego" or o.get("unique_id") == "ego"),
        "translation_x": trans.get("x"),
        "translation_y": trans.get("y"),
        "translation_z": trans.get("z"),
        "velocity_x": vel.get("vx"),
        "velocity_y": vel.get("vy"),
        "width": size.get("width") if isinstance(size, dict) else None,
        "length": size.get("length") if isinstance(size, dict) else None,
        "height": size.get("height") if isinstance(size, dict) else None,
    }


def flat_rel(e: Dict[str, Any]) -> Dict[str, Any]:
    metrics = e.get("metrics") or {}
    return {
        "source": e.get("source"),
        "target": e.get("target"),
        "props": {
            "direction_6": str(e.get("direction_6") or e.get("direction_official") or "").replace("-", "_"),
            "distance": metrics.get("distance") or e.get("distance"),
            "is_nearest": bool(e.get("is_nearest", False)),
            "rank_by_distance": e.get("rank_by_distance") or metrics.get("rank_by_distance"),
        },
    }


def main(path: str):
    sg = json.loads(Path(path).read_text(encoding="utf-8"))
    nodes = [flat_node(o) for o in (sg.get("nodes") or sg.get("objects") or [])]
    rels = [flat_rel(e) for e in (sg.get("edges") or sg.get("relationships") or [])]
    batch_size = int(os.environ.get("NEO4J_IMPORT_BATCH_SIZE") or 100)
    print(f"[import_scene_graph_http] delete old graph url={URL}", flush=True)
    post([{"statement": "MATCH (n) DETACH DELETE n"}])
    for i in range(0, len(nodes), batch_size):
        post([{"statement": "UNWIND $batch AS props CREATE (o:Object) SET o = props", "parameters": {"batch": nodes[i:i+batch_size]}}])
        print(f"[import_scene_graph_http] nodes {min(i+batch_size, len(nodes))}/{len(nodes)}", flush=True)
    for i in range(0, len(rels), batch_size):
        post([{"statement": "UNWIND $batch AS item MATCH (a:Object {unique_id:item.source}) MATCH (b:Object {unique_id:item.target}) CREATE (a)-[r:RELATES_TO]->(b) SET r = item.props", "parameters": {"batch": rels[i:i+batch_size]}}])
        print(f"[import_scene_graph_http] rels {min(i+batch_size, len(rels))}/{len(rels)}", flush=True)
    check = post([{"statement": "MATCH (n:Object) RETURN count(n) AS objects", "resultDataContents": ["row"]}, {"statement": "MATCH ()-[r:RELATES_TO]->() RETURN count(r) AS relationships", "resultDataContents": ["row"]}])
    print(json.dumps(check, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])

