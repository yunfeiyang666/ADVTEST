#!/usr/bin/env python3
"""
将 V17 帧表 JSON 拆成 N 份互不重叠的子表（按原列表顺序连续切分）。

输出文件名（统一约定）：
  {prefix}_w1.json, {prefix}_w2.json, ... {prefix}_wN.json
全量帧表由 build_frame_plan_from_test6019_bundle.py 生成：
  .../nuscenesqa_val_plan_full.json

示例：
  python split_frame_plan.py \\
    --in ../deploy/nuscenesqa_val_plan_full.json \\
    --parts 3 \\
    --out-dir ../deploy \\
    --prefix nuscenesqa_val_plan
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_path", type=Path, required=True, help="全量帧表 JSON")
    ap.add_argument("--parts", type=int, default=3, help="拆成几份（默认 3）")
    ap.add_argument("--out-dir", type=Path, required=True, help="输出目录")
    ap.add_argument(
        "--prefix",
        default="nuscenesqa_val_plan",
        help="输出文件名前缀，生成 nuscenesqa_val_plan_w1.json 等",
    )
    args = ap.parse_args()

    raw = json.loads(args.in_path.read_text(encoding="utf-8"))
    frames = raw.get("frames")
    if not isinstance(frames, list) or not frames:
        raise SystemExit("输入 JSON 需包含非空 frames 数组")

    n = len(frames)
    k = max(1, int(args.parts))
    base, rem = divmod(n, k)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    idx = 0
    for i in range(k):
        sz = base + (1 if i < rem else 0)
        chunk = frames[idx : idx + sz]
        start = idx
        idx += sz
        out_obj = {
            "description": (raw.get("description") or "frame plan") + f" [part {i + 1}/{k}]",
            "source": str(args.in_path.resolve()),
            "part_index": i + 1,
            "part_count": k,
            "global_index_start": start,
            "global_index_end": start + len(chunk),
            "n_frames": len(chunk),
            "frames": chunk,
        }
        name = f"{args.prefix}_w{i + 1}.json"
        out_path = args.out_dir / name
        out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"OK {name}  frames={len(chunk)}  global[{start}:{start + len(chunk)})")


if __name__ == "__main__":
    main()
