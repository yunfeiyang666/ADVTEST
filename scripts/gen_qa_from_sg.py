import os
import json
import argparse
import random
import math
from typing import List, Dict, Any

SECTORS = [
    'front', 'front-left', 'left', 'back-left', 'back', 'back-right', 'right', 'front-right'
]
DIST_BINS = ['very_close', 'close', 'medium', 'far']
DIST_OPTIONS = ['Very close (0-2m)', 'Close (2-10m)', 'Medium (10-30m)', 'Far (30m+)']


def short_cat(name: str) -> str:
    # e.g., 'vehicle.car' -> 'car'; 'human.pedestrian.adult' -> 'pedestrian'
    if not name:
        return name
    parts = name.split('.')
    if parts[0] == 'vehicle' and len(parts) > 1:
        return parts[1]
    if parts[0] == 'human' and len(parts) > 1:
        return parts[1]
    return parts[-1]


def edges_from_ego(frame: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out = {}
    for e in frame['edges']:
        if e['from'] == 'ego':
            out[e['to']] = e
        elif e['to'] == 'ego':
            # We only created ego as 'from' in generator, but keep fallback
            out[e['from']] = e
    return out


def gen_for_frame(frame: Dict[str, Any], ttc_threshold: float = 2.0, rng: random.Random = None) -> List[Dict[str, Any]]:
    rng = rng or random.Random(0)
    qas = []
    eid = edges_from_ego(frame)
    nodes = [n for n in frame['nodes'] if n['id'] != 'ego']

    # Helper: pick a subset for load control
    rng.shuffle(nodes)
    nodes = nodes[:min(20, len(nodes))]

    # Q1: Distance bin classification per node
    for n in nodes:
        nid = n['id']
        e = eid.get(nid)
        if not e:
            continue
        dbin = n.get('bins', {}).get('distance')
        if dbin not in DIST_BINS:
            continue
        idx = DIST_BINS.index(dbin)
        qas.append({
            'type': 'distance_bin_mc',
            'sample_token': frame['sample_token'],
            'target_id': nid,
            'question': f"How close is the {short_cat(n['category_name'])} (id={nid[:6]}) to the ego vehicle?",
            'options': DIST_OPTIONS,
            'answer_index': idx,
            'answer': DIST_OPTIONS[idx]
        })

    # Q2: Sector classification per node
    for n in nodes:
        sector = n.get('bins', {}).get('sector8')
        if sector in SECTORS:
            qas.append({
                'type': 'sector_mc',
                'sample_token': frame['sample_token'],
                'target_id': n['id'],
                'question': f"Where is the {short_cat(n['category_name'])} (id={n['id'][:6]}) relative to the ego vehicle?",
                'options': SECTORS,
                'answer_index': SECTORS.index(sector),
                'answer': sector
            })

    # Q3: Moving/Standing/Stopped
    for n in nodes:
        attrs = (n.get('attributes') or {})
        if attrs.get('moving') is True:
            qas.append({
                'type': 'yesno_attr',
                'sample_token': frame['sample_token'],
                'target_id': n['id'],
                'question': f"Is the {short_cat(n['category_name'])} (id={n['id'][:6]}) moving?",
                'answer': 'Yes'
            })
        if attrs.get('standing') is True:
            qas.append({
                'type': 'yesno_attr',
                'sample_token': frame['sample_token'],
                'target_id': n['id'],
                'question': f"Is the {short_cat(n['category_name'])} (id={n['id'][:6]}) standing?",
                'answer': 'Yes'
            })
        if attrs.get('stopped') is True:
            qas.append({
                'type': 'yesno_attr',
                'sample_token': frame['sample_token'],
                'target_id': n['id'],
                'question': f"Is the {short_cat(n['category_name'])} (id={n['id'][:6]}) stopped?",
                'answer': 'Yes'
            })

    # Q4: Collision yes/no based on TTC (< threshold)
    for n in nodes:
        e = eid.get(n['id'])
        if not e:
            continue
        ttc = e.get('ttc')
        if ttc is None:
            continue
        will_collide = (ttc < ttc_threshold)
        qas.append({
            'type': 'yesno_ttc',
            'sample_token': frame['sample_token'],
            'target_id': n['id'],
            'question': f"If we keep straight for {ttc_threshold:.1f} seconds, will we collide with the {short_cat(n['category_name'])} (id={n['id'][:6]})?",
            'answer': 'Yes' if will_collide else 'No',
            'evidence': {'ttc': ttc}
        })

    # Q5: Count vehicles in front sector
    veh_ids = [n for n in nodes if (n['category_name'] or '').startswith('vehicle')]
    count_front = sum(1 for n in veh_ids if n.get('bins', {}).get('sector8') == 'front')
    qas.append({
        'type': 'count_mc',
        'sample_token': frame['sample_token'],
        'question': 'How many vehicles are in the front of the ego vehicle?',
        'options': [str(x) for x in range(6)],
        'answer_index': min(count_front, 5),
        'answer': str(count_front)
    })

    return qas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jsonl', type=str, required=True)
    ap.add_argument('--out_path', type=str, required=True)
    ap.add_argument('--max_frames', type=int, default=50)
    ap.add_argument('--ttc_threshold', type=float, default=2.0)
    args = ap.parse_args()

    total = 0
    kept = 0
    with open(args.out_path, 'w', encoding='utf-8') as fw:
        with open(args.jsonl, 'r', encoding='utf-8') as fr:
            for idx, line in enumerate(fr):
                if idx >= args.max_frames:
                    break
                frame = json.loads(line)
                qas = gen_for_frame(frame, ttc_threshold=args.ttc_threshold)
                for qa in qas:
                    fw.write(json.dumps(qa) + '\n')
                    kept += 1
                total += 1
    print(f"Wrote {kept} QA items from {total} frames to {args.out_path}")


if __name__ == '__main__':
    main()
