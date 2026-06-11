"""
coverage_tracker_patch.py
=========================
给 coverage_tracker.CoverageTracker 加一个 dump_universe_snapshot() 方法,
在 init_from_session() 之后立即调用, 把那一帧的「全集快照」落盘成 JSON。

为什么需要这个:
  CoverageTracker 的 self._L0/_L1/_L2A/_L2B 是进程内存, 每帧跑完就丢。
  后期画覆盖率曲线时, 必须知道每帧的「分母」(全集大小), 否则只有
  Excel 里命中的题目而没有总量, 算不出占比。

  这个 snapshot 一帧只写一次, ~几十 KB, 6011 帧累计 ~300 MB,
  完全离线, 不依赖 Neo4j。

集成方式: 在原 coverage_tracker.py 末尾追加这个方法即可,
或者用 monkey-patch 方式在 import 后接上。

使用示例 (建议在 run_v17_production.py 或 run_method_a.py 里加):

    from coverage_tracker import CoverageTracker
    from coverage_tracker_patch import dump_universe_snapshot
    CoverageTracker.dump_universe_snapshot = dump_universe_snapshot

    tracker = CoverageTracker()
    with driver.session() as sess:
        tracker.init_from_session(sess)
    # 立即落盘全集快照, 此后即使 Neo4j 被清也无影响
    tracker.dump_universe_snapshot(
        scene_id=scene_id,
        frame_id=frame_id,
        out_dir="output/coverage_snapshots",
    )
"""
from __future__ import annotations

import json
import logging
import pathlib
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def dump_universe_snapshot(
    self,
    scene_id: str,
    frame_id: int,
    out_dir: str = "output/coverage_snapshots",
) -> pathlib.Path:
    """
    把当前 tracker 持有的 L0/L1/L2A/L2B 全集 keys 落盘为 JSON。

    必须在 init_from_session() 之后、record_from_qa() 之前调用,
    确保落下的是「纯全集」, 没有被 hit_count 污染。
    (注: 即使在生成期间调用也只看 keys, 不看 hit_count, 所以重复调用是幂等的)

    Returns
    -------
    snapshot 文件路径
    """
    out_path_dir = pathlib.Path(out_dir)
    out_path_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_path_dir / f"{scene_id}_frame{frame_id}_universe.json"

    snapshot = {
        "scene_id": scene_id,
        "frame_id": frame_id,
        "L0":  sorted(self._L0.keys()),
        "L1":  sorted(self._L1.keys()),
        "L2A": sorted(self._L2A.keys()),
        "L2B": sorted(self._L2B.keys()),
        "totals": {
            "L0":  len(self._L0),
            "L1":  len(self._L1),
            "L2A": len(self._L2A),
            "L2B": len(self._L2B),
            "L2_combined": len(self._L2A) + len(self._L2B),
        },
    }

    out_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    logger.info(
        "[OK] universe snapshot dumped: %s  (L0=%d L1=%d L2A=%d L2B=%d)",
        out_path.name,
        snapshot["totals"]["L0"], snapshot["totals"]["L1"],
        snapshot["totals"]["L2A"], snapshot["totals"]["L2B"],
    )
    return out_path


def install_patch():
    """Monkey-patch CoverageTracker class with the dump method."""
    from gap_pipeline.coverage_tracker import CoverageTracker
    CoverageTracker.dump_universe_snapshot = dump_universe_snapshot
    logger.info("CoverageTracker.dump_universe_snapshot installed")


if __name__ == "__main__":
    install_patch()
    print("Patch ready. Import this module before using CoverageTracker.")
