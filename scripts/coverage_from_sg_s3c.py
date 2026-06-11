#!/usr/bin/env python3

import os
import json
import argparse
from collections import Counter, defaultdict

SECTORS = [
    'front', 'front-left', 'left', 'back-left', 'back', 'back-right', 'right', 'front-right'
]
DIST_BINS = ['very_close', 'close', 'medium', 'far']

# S3C增强字段
S3C_ANGULAR = ['direct_front', 'side_front', 'direct_rear', 'side_rear']
S3C_DISTANCE = ['safe_hazard', 'near_coll', 'super_near', 'very_near', 'near', 'visible', 'far']


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

    # 原有计数器
    node_cov = Counter()                # (cat, sector, dist)
    node_cov_cat = Counter()            # (cat)
    edge_cov_rel = Counter()            # (relation_type)
    edge_cov_same = Counter()           # (same_lane)
    edge_cov_adj = Counter()            # (adjacent_lane True/False/None)
    edge_cov_pair = Counter()           # (relation_type, same_lane, adj)
    
    # S3C增强计数器
    node_cov_s3c_dist = Counter()       # (s3c_distance)
    node_cov_s3c_ang = Counter()        # (s3c_angular)
    node_cov_s3c_full = Counter()       # (cat, s3c_angular, s3c_distance)
    node_cov_sector = Counter()         # (sector8)
    node_cov_distance = Counter()       # (distance)

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
                bins = n.get('bins') or {}
                
                # 原有字段
                sector = bins.get('sector8')
                dist = bins.get('distance')
                node_cov_cat[(cat,)] += 1
                if sector in SECTORS and dist in DIST_BINS:
                    node_cov[(cat, sector, dist)] += 1
                
                # 单独统计扇区和距离
                if sector:
                    node_cov_sector[(sector,)] += 1
                if dist:
                    node_cov_distance[(dist,)] += 1
                
                # S3C增强字段
                s3c_angular = bins.get('s3c_angular')
                s3c_distance = bins.get('s3c_distance')
                
                if s3c_angular:
                    node_cov_s3c_ang[(s3c_angular,)] += 1
                if s3c_distance:
                    node_cov_s3c_dist[(s3c_distance,)] += 1
                
                # S3C完整覆盖率
                if s3c_angular and s3c_distance:
                    node_cov_s3c_full[(cat, s3c_angular, s3c_distance)] += 1

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

    # 原有覆盖率文件
    write_csv(os.path.join(args.out_dir, 'nodes_coverage.csv'),
              ['category','sector','distance','count'],
              [(c[0], c[1], c[2], v) for c, v in sorted(node_cov.items())])

    write_csv(os.path.join(args.out_dir, 'nodes_by_category.csv'),
              ['category','count'],
              [(c[0], v) for c, v in sorted(node_cov_cat.items())])

    write_csv(os.path.join(args.out_dir, 'nodes_by_sector8.csv'),
              ['sector8','count'],
              [(c[0], v) for c, v in sorted(node_cov_sector.items())])

    write_csv(os.path.join(args.out_dir, 'nodes_by_distance.csv'),
              ['distance','count'],
              [(c[0], v) for c, v in sorted(node_cov_distance.items())])

    # S3C增强覆盖率文件
    write_csv(os.path.join(args.out_dir, 'nodes_by_s3c_angular.csv'),
              ['s3c_angular','count'],
              [(c[0], v) for c, v in sorted(node_cov_s3c_ang.items())])

    write_csv(os.path.join(args.out_dir, 'nodes_by_s3c_distance.csv'),
              ['s3c_distance','count'],
              [(c[0], v) for c, v in sorted(node_cov_s3c_dist.items())])

    write_csv(os.path.join(args.out_dir, 'nodes_s3c_coverage.csv'),
              ['category','s3c_angular','s3c_distance','count'],
              [(c[0], c[1], c[2], v) for c, v in sorted(node_cov_s3c_full.items())])

    # 边覆盖率文件
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

    # S3C增强概览
    s3c_overview = {
        'frames': frames,
        'nodes_total': nodes_total,
        'edges_total': edges_total,
        
        # 传统覆盖率
        'unique_node_triplets': len(node_cov),
        'unique_categories': len(node_cov_cat),
        'unique_relation_types': len(edge_cov_rel),
        
        # S3C增强覆盖率
        's3c_coverage': {
            'unique_s3c_angular': len(node_cov_s3c_ang),
            'unique_s3c_distance': len(node_cov_s3c_dist),
            'unique_s3c_triplets': len(node_cov_s3c_full),
            's3c_angular_distribution': {k[0]: v for k, v in node_cov_s3c_ang.items()},
            's3c_distance_distribution': {k[0]: v for k, v in node_cov_s3c_dist.items()}
        },
        
        # 覆盖率完整性分析
        'coverage_completeness': {
            'sector8_coverage': f"{len(node_cov_sector)}/{len(SECTORS)} ({len(node_cov_sector)/len(SECTORS)*100:.1f}%)",
            'distance_coverage': f"{len(node_cov_distance)}/{len(DIST_BINS)} ({len(node_cov_distance)/len(DIST_BINS)*100:.1f}%)",
            's3c_angular_coverage': f"{len(node_cov_s3c_ang)}/{len(S3C_ANGULAR)} ({len(node_cov_s3c_ang)/len(S3C_ANGULAR)*100:.1f}%)",
            's3c_distance_coverage': f"{len(node_cov_s3c_dist)}/{len(S3C_DISTANCE)} ({len(node_cov_s3c_dist)/len(S3C_DISTANCE)*100:.1f}%)"
        }
    }
    
    with open(os.path.join(args.out_dir, 'overview_s3c.json'), 'w', encoding='utf-8') as fw:
        json.dump(s3c_overview, fw, indent=2)

    print(f"Wrote S3C enhanced coverage report to {args.out_dir}")
    print(f"S3C Angular Coverage: {len(node_cov_s3c_ang)}/{len(S3C_ANGULAR)} categories")
    print(f"S3C Distance Coverage: {len(node_cov_s3c_dist)}/{len(S3C_DISTANCE)} categories")


if __name__ == '__main__':
    main()
