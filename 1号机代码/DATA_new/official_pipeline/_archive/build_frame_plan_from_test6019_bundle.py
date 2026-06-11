#!/usr/bin/env python3
"""
从 test6019_bundle/sample_token_to_scene.json 生成 V17 用的帧表 JSON
（NuScenes-QA val 去重后约 6011 帧；文件名约定：{scene_name}_frame{frame_idx}_scene_graph.json）

用法示例：
  python build_frame_plan_from_test6019_bundle.py \\
    --bundle-dir /home/yunyang/ADVTEST/DATA_new/data/test6019_bundle \\
     --out /home/yunyang/ADVTEST/DATA_new/code/deploy/nuscenesqa_val_plan_full.json

可选：检查 FILTERED_SG_DIR 下是否已有对应 json：
  python build_frame_plan_from_test6019_bundle.py \\
    --bundle-dir .../test6019_bundle \\
     --out .../nuscenesqa_val_plan_full.json \\
    --check-sg /home/yunyang/ADVTEST/DATA_new/filtered_scene_graphs
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--bundle-dir",
        type=Path,
        required=True,
        help="含 sample_token_to_scene.json 的目录（通常 .../data/test6019_bundle）",
    )
    ap.add_argument(
        "--out",
        type=Path,
        required=True,
        help="输出帧表 JSON（给 ADVTEST_FRAME_PLAN_JSON 使用）",
    )
    ap.add_argument(
        "--check-sg",
        type=Path,
        default=None,
        help="若指定，则检查该目录下是否存在每条 sg_filename",
    )
    args = ap.parse_args()

    src = args.bundle_dir / "sample_token_to_scene.json"
    if not src.is_file():
        raise SystemExit(f"缺少文件: {src}")

    mapping = json.loads(src.read_text(encoding="utf-8"))
    # 按 (scene_name, frame_idx) 去重；同一帧只跑一遍
    seen: set[tuple[str, int]] = set()
    frames: list[dict] = []
    for _tok, info in mapping.items():
        sname = str(info.get("scene_name") or "").strip()
        fidx = int(info.get("frame_idx", -1))
        if not sname or fidx < 0:
            continue
        key = (sname, fidx)
        if key in seen:
            continue
        seen.add(key)
        sg = f"{sname}_frame{fidx}_scene_graph.json"
        frames.append(
            {
                "scene_id": sname,
                "frame_id": fidx,
                "sg_filename": sg,
            }
        )

    frames.sort(key=lambda x: (x["scene_id"], x["frame_id"]))

    out_obj = {
        "description": "NuScenes-QA val 全量帧（由 test6019_bundle/sample_token_to_scene.json 生成）",
        "source": str(src),
        "n_frames": len(frames),
        "frames": frames,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(frames)} 帧 -> {args.out}")

    if args.check_sg:
        d = Path(args.check_sg)
        missing = [f["sg_filename"] for f in frames if not (d / f["sg_filename"]).is_file()]
        print(f"FILTERED_SG 检查: 目录 {d}")
        print(f"  缺失 {len(missing)} / {len(frames)}")
        if missing:
            print("  示例缺失（前 15 个）:")
            for m in missing[:15]:
                print(f"    - {m}")


if __name__ == "__main__":
    main()
