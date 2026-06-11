import os
import json
import argparse
from collections import Counter, defaultdict

SECTORS = [
    'front', 'front-left', 'left', 'back-left', 'back', 'back-right', 'right', 'front-right'
]
DIST_BINS = ['very_close', 'close', 'medium', 'far']


def short_cat(cat: str) -> str:
    if not cat:
        return ''
    parts = cat.split('.')
    if parts[0] in ('vehicle', 'human') and len(parts) > 1:
        return parts[1]
    return parts[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jsonl', type=str, required=True)
    ap.add_argument('--out_dir', type=str, required=True)
    ap.add_argument('--max_frames', type=int, default=None)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    # Counters
    node_cov = Counter()                # (cat, sector, dist)
    node_cov_cat = Counter()            # (cat)
    edge_cov_rel = Counter()            # (relation_type)
    edge_cov_same = Counter()           # (same_lane)
    edge_cov_adj = Counter()            # (adjacent_lane True/False/None)
    edge_cov_pair = Counter()           # (relation_type, same_lane, adj)

    frames = 0
    nodes_total = 0
    edges_total = 0

    with open(args.jsonl, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if args.max_frames is not None and idx >= args.max_frames:
                break
            fr = json.loads(line)
            frames += 1

            # nodes
            for n in fr['nodes']:
                if n['id'] == 'ego':
                    continue
                nodes_total += 1
                cat = short_cat(n.get('category_name',''))
                sector = (n.get('bins') or {}).get('sector8')
                dist = (n.get('bins') or {}).get('distance')
                node_cov_cat[(cat,)] += 1
                if sector in SECTORS and dist in DIST_BINS:
                    node_cov[(cat, sector, dist)] += 1

            # edges
            for e in fr['edges']:
                edges_total += 1
                rel = e.get('relation_type')
                edge_cov_rel[(rel,)] += 1
                same = bool(e.get('same_lane', False))
                adj = e.get('adjacent_lane', None)
                edge_cov_same[(same,)] += 1
                edge_cov_adj[(adj,)] += 1
                edge_cov_pair[(rel, same, adj)] += 1

    # write CSVs
    def write_csv(path, header, rows):
        with open(path, 'w', encoding='utf-8') as fw:
            fw.write(','.join(header) + '\n')
            for r in rows:
                fw.write(','.join(str(x) for x in r) + '\n')

    write_csv(os.path.join(args.out_dir, 'nodes_coverage.csv'),
              ['category','sector','distance','count'],
              [(c[0], c[1], c[2], v) for c, v in sorted(node_cov.items())])

    write_csv(os.path.join(args.out_dir, 'nodes_by_category.csv'),
              ['category','count'],
              [(c[0], v) for c, v in sorted(node_cov_cat.items())])

    write_csv(os.path.join(args.out_dir, 'edges_by_relation.csv'),
              ['relation_type','count'],
              [(c[0], v) for c, v in sorted(edge_cov_rel.items())])

    write_csv(os.path.join(args.out_dir, 'edges_same_lane.csv'),
              ['same_lane','count'],
              [(c[0], v) for c, v in sorted(edge_cov_same.items())])

    write_csv(os.path.join(args.out_dir, 'edges_adjacent_lane.csv'),
              ['adjacent_lane','count'],
              [(c[0], v) for c, v in sorted(edge_cov_adj.items())])

    write_csv(os.path.join(args.out_dir, 'edges_relation_same_adj.csv'),
              ['relation_type','same_lane','adjacent_lane','count'],
              [(c[0], c[1], c[2], v) for c, v in sorted(edge_cov_pair.items())])

    # overview json
    overview = {
        'frames': frames,
        'nodes_total': nodes_total,
        'edges_total': edges_total,
        'unique_node_triplets': len(node_cov),
        'unique_categories': len(node_cov_cat),
        'unique_relation_types': len(edge_cov_rel)
    }
    with open(os.path.join(args.out_dir, 'overview.json'), 'w', encoding='utf-8') as fw:
        json.dump(overview, fw, indent=2)

    print(f"Wrote coverage report to {args.out_dir}")


if __name__ == '__main__':
    main()
