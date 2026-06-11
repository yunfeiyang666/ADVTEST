"""Inspect key spatial relations in scene-0553_frame8 for Q8-style questions.

We print all edges of the following forms:
- (pedestrianX -> busY)
- (busY -> pedestrianX)
- (trailer* -> busY)
- (busY -> trailer*)

for the regenerated source-centric scene graph, including direction_8,
direction_4, and angle/distance. This helps verify whether the encoded
relations match our BEV / intuitive expectations for Q8.
"""

from pathlib import Path
import json

SCENE_GRAPH_PATH = Path("output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json")


def load_scene_graph(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    if not SCENE_GRAPH_PATH.exists():
        print(f"Scene graph not found: {SCENE_GRAPH_PATH}")
        return

    sg = load_scene_graph(SCENE_GRAPH_PATH)
    nodes = {n["unique_id"]: n for n in sg.get("nodes", [])}
    edges = sg.get("edges", [])

    print(f"Scene: {sg.get('scene_name')} frame {sg.get('frame_idx')}")
    print(f"Total nodes: {len(nodes)}, edges: {len(edges)}\n")

    def is_ped(nid):
        return nodes.get(nid, {}).get("type") == "pedestrian"

    def is_bus(nid):
        return nodes.get(nid, {}).get("type") == "bus"

    def is_trailer(nid):
        cat = nodes.get(nid, {}).get("category", "")
        return "trailer" in cat

    def is_bicycle_with_rider(nid):
        n = nodes.get(nid, {})
        return n.get("type") == "bicycle" and n.get("status") == "with_rider"

    def is_car(nid):
        return nodes.get(nid, {}).get("type") == "car"

    print("[Pedestrian -> Bus edges] (for 'bus to the DIR of pedestrian')\n")
    for e in edges:
        s, t = e["source"], e["target"]
        if is_ped(s) and is_bus(t):
            m = e.get("metrics", {})
            print(f"{s} -> {t}: dir8={e.get('direction_8')}, dir4={e.get('direction_4')}, "
                  f"angle={m.get('angle')}, dist={m.get('distance')}")
    print("\n[Bus -> Pedestrian edges] (for 'pedestrian to DIR of bus' sanity)\n")
    for e in edges:
        s, t = e["source"], e["target"]
        if is_bus(s) and is_ped(t):
            m = e.get("metrics", {})
            print(f"{s} -> {t}: dir8={e.get('direction_8')}, dir4={e.get('direction_4')}, "
                  f"angle={m.get('angle')}, dist={m.get('distance')}")

    print("\n[Trailer -> Bus edges] (for 'bus to the DIR of trailer')\n")
    for e in edges:
        s, t = e["source"], e["target"]
        if is_trailer(s) and is_bus(t):
            m = e.get("metrics", {})
            print(f"{s} -> {t}: dir8={e.get('direction_8')}, dir4={e.get('direction_4')}, "
                  f"angle={m.get('angle')}, dist={m.get('distance')}")

    print("\n[Bus -> Trailer edges] (for completeness)\n")
    for e in edges:
        s, t = e["source"], e["target"]
        if is_bus(s) and is_trailer(t):
            m = e.get("metrics", {})
            print(f"{s} -> {t}: dir8={e.get('direction_8')}, dir4={e.get('direction_4')}, "
                  f"angle={m.get('angle')}, dist={m.get('distance')}")

    # --- Q11: stopped trailer vs with_rider bicycles front-left ---
    print("\n[Trailer (stopped) -> Bicycle(with_rider) edges] (for Q11)\n")
    for e in edges:
        s, t = e["source"], e["target"]
        if is_trailer(s) and is_bicycle_with_rider(t):
            m = e.get("metrics", {})
            trailer_status = nodes[s].get("status")
            print(f"{s} (status={trailer_status}) -> {t} (status={nodes[t].get('status')}): "
                  f"dir8={e.get('direction_8')}, dir4={e.get('direction_4')}, "
                  f"angle={m.get('angle')}, dist={m.get('distance')}")

    # --- Q13: with_rider ref -> truck(front-left), then cars with same status ---
    print("\n[With_rider ref -> Truck edges] (front-left candidates for Q12/Q13)\n")
    for e in edges:
        s, t = e["source"], e["target"]
        if is_bicycle_with_rider(s) and nodes.get(t, {}).get("type") == "truck":
            m = e.get("metrics", {})
            print(f"{s} (status={nodes[s].get('status')}) -> {t} (status={nodes[t].get('status')}): "
                  f"dir8={e.get('direction_8')}, dir4={e.get('direction_4')}, "
                  f"angle={m.get('angle')}, dist={m.get('distance')}")

    print("\n[Cars by status] (for Q13 same-status check)\n")
    for nid, n in nodes.items():
        if is_car(nid):
            print(f"{nid}: status={n.get('status')}")


if __name__ == "__main__":
    main()
