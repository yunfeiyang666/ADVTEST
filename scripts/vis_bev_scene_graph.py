import os
import json
import argparse
import math
from typing import Tuple, List

import numpy as np
import matplotlib
matplotlib.use('Agg')  # non-interactive backend for safe batch rendering
import matplotlib.pyplot as plt


CAT_COLORS = {
    'vehicle': '#e41a1c',
    'human': '#377eb8',
    'animal': '#4daf4a',
    'movable_object': '#984ea3',
    'static_object': '#ff7f00',
    'flat': '#a65628',
    'vehicle.ego': '#1f78b4'
}


def _cat_color(category_name: str) -> str:
    if category_name == 'vehicle.ego':
        return CAT_COLORS['vehicle.ego']
    prefix = category_name.split('.')[0] if '.' in category_name else category_name
    return CAT_COLORS.get(prefix, '#555555')


def box2d_corners(center: np.ndarray, yaw: float, w: float, l: float) -> np.ndarray:
    # center: (x, y), yaw in rad, ego frame; size: w along y, l along x (nuscenes definition)
    dx = l / 2.0
    dy = w / 2.0
    pts = np.array([
        [ dx,  dy],
        [ dx, -dy],
        [-dx, -dy],
        [-dx,  dy]
    ], dtype=float)
    c, s = math.cos(yaw), math.sin(yaw)
    R = np.array([[c, -s], [s, c]], dtype=float)
    return (pts @ R.T) + center[None, :]


def draw_box(ax, corners2d: np.ndarray, color: str, lw: float = 1.0, fill: bool = False, alpha: float = 0.2):
    poly = np.vstack([corners2d, corners2d[0]])
    ax.plot(poly[:, 0], poly[:, 1], color=color, linewidth=lw)
    if fill:
        ax.fill(poly[:, 0], poly[:, 1], color=color, alpha=alpha)


def draw_arrow(ax, start: np.ndarray, vec: np.ndarray, color: str, scale: float = 1.0, width: float = 0.003):
    ax.arrow(start[0], start[1], vec[0] * scale, vec[1] * scale, head_width=0.8, head_length=1.2, fc=color, ec=color, length_includes_head=True, lw=0.5)


def plot_frame(frame: dict, out_path: str, xlim: Tuple[float, float], ylim: Tuple[float, float],
               show_edges_from_ego: bool, k_nearest: int, draw_vel: bool):
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_aspect('equal', adjustable='box')
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.set_xlabel('x (forward, m)')
    ax.set_ylabel('y (left, m)')
    ax.set_title(f"sample: {frame.get('sample_token','')}  t: {frame.get('timestamp','')}")

    nodes = frame['nodes']
    node_by_id = {n['id']: n for n in nodes}

    # centers for edges
    centers = {n['id']: np.array(n['pose']['ego']['center'][:2], dtype=float) if n['pose']['ego']['center'] is not None else np.zeros(2) for n in nodes}

    # draw nodes
    for n in nodes:
        nid = n['id']
        cat = n['category_name']
        color = _cat_color(cat)
        center = np.array(n['pose']['ego']['center'][:2], dtype=float) if n['pose']['ego']['center'] is not None else np.zeros(2)
        if cat == 'vehicle.ego':
            # draw ego as a fixed small box and heading arrow
            c2d = box2d_corners(center, 0.0, w=2.0, l=4.0)
            draw_box(ax, c2d, color=color, lw=2.0, fill=True, alpha=0.15)
            draw_arrow(ax, center, np.array([3.0, 0.0]), color)
        else:
            size = n.get('size') or {}
            wlh = size.get('wlh') if size else None
            yaw = float(n['pose']['ego'].get('yaw', 0.0))
            if wlh is not None:
                w, l = float(wlh[0]), float(wlh[1])
                box = box2d_corners(center, yaw, w=w, l=l)
                draw_box(ax, box, color=color, lw=1.2, fill=False)
            else:
                ax.plot(center[0], center[1], marker='o', color=color, markersize=3)

            if draw_vel:
                v = np.array(n['velocity']['ego'][:2], dtype=float)
                if np.linalg.norm(v) > 0.05:
                    draw_arrow(ax, center, v, color=color, scale=1.0)

    # draw edges (from ego or k-nearest by distance to ego)
    edges = frame['edges']
    if show_edges_from_ego:
        for e in edges:
            a, b = e['from'], e['to']
            if a == 'ego' or b == 'ego':
                p = centers[a]
                q = centers[b]
                ax.plot([p[0], q[0]], [p[1], q[1]], color='#999999', alpha=0.6, linewidth=0.8)
    else:
        # only draw k nearest to ego
        ego_c = centers.get('ego', np.zeros(2))
        others = [(nid, np.linalg.norm(c - ego_c)) for nid, c in centers.items() if nid != 'ego']
        others.sort(key=lambda x: x[1])
        keep = set([nid for nid, _ in others[:max(1, k_nearest)]])
        for e in edges:
            a, b = e['from'], e['to']
            if a in keep or b in keep:
                p = centers[a]
                q = centers[b]
                ax.plot([p[0], q[0]], [p[1], q[1]], color='#bbbbbb', alpha=0.5, linewidth=0.6)

    # legend proxy
    for k, v in CAT_COLORS.items():
        ax.plot([], [], color=v, label=k)
    ax.legend(loc='upper right', fontsize=8, ncol=2)

    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--jsonl', type=str, required=True, help='Path to scene graph jsonl')
    ap.add_argument('--out_dir', type=str, required=True, help='Where to save BEV images')
    ap.add_argument('--max_frames', type=int, default=10, help='Render at most N frames')
    ap.add_argument('--xlim', type=float, nargs=2, default=[-20, 80], help='x axis range (m)')
    ap.add_argument('--ylim', type=float, nargs=2, default=[-40, 40], help='y axis range (m)')
    ap.add_argument('--only_ego_edges', action='store_true', help='Draw only edges connected to ego')
    ap.add_argument('--k_nearest', type=int, default=30, help='When not only_ego_edges, draw edges for k nearest nodes to ego')
    ap.add_argument('--draw_vel', action='store_true', help='Draw velocity arrows')
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    with open(args.jsonl, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if idx >= args.max_frames:
                break
            frame = json.loads(line)
            sample_token = frame.get('sample_token', f'{idx:06d}')
            out_path = os.path.join(args.out_dir, f"{idx:06d}_{sample_token}.png")
            plot_frame(frame, out_path, tuple(args.xlim), tuple(args.ylim), args.only_ego_edges, args.k_nearest, args.draw_vel)

    print(f"Saved BEV images to {args.out_dir}")


if __name__ == '__main__':
    main()
