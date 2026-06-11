#!/usr/bin/env python3
"""
两帧完整测试 - 使用完整的official_pipeline流程
"""
import sys
import subprocess
import re
from pathlib import Path
from datetime import datetime

OFFICIAL_PIPELINE_DIR = Path(__file__).parent / "official_pipeline"
RUN_METHOD_A = OFFICIAL_PIPELINE_DIR / "run_method_a.py"

def modify_run_method_a(scene_id: str, frame_id: int):
    print(f"\n修改配置: {scene_id} frame {frame_id}")
    content = RUN_METHOD_A.read_text(encoding='utf-8')
    sg_filename = f"{scene_id}_frame{frame_id}_scene_graph.json"
    content = re.sub(r'TARGET_SG\s*=\s*"scene-\d+_frame\d+_scene_graph\.json"', f'TARGET_SG   = "{sg_filename}"', content)
    content = re.sub(r'SCENE_ID\s*=\s*"scene-\d+"', f'SCENE_ID    = "{scene_id}"', content)
    content = re.sub(r'FRAME_ID\s*=\s*\d+', f'FRAME_ID    = {frame_id}', content)
    RUN_METHOD_A.write_text(content, encoding='utf-8')
    print(f"  ✓ 配置已更新")

def run_frame(scene_id: str, frame_id: int):
    print("\n" + "="*80)
    print(f"运行完整流程: {scene_id} frame {frame_id}")
    print("="*80)
    try:
        modify_run_method_a(scene_id, frame_id)
    except Exception as e:
        print(f"✗ 配置修改失败: {e}")
        return False
    print(f"\n执行: python {RUN_METHOD_A.name}")
    try:
        result = subprocess.run([sys.executable, str(RUN_METHOD_A)], cwd=str(OFFICIAL_PIPELINE_DIR), timeout=3600)
        if result.returncode == 0:
            print(f"✓ {scene_id} frame {frame_id} 完成")
            return True
        else:
            print(f"✗ {scene_id} frame {frame_id} 失败")
            return False
    except Exception as e:
        print(f"✗ {scene_id} frame {frame_id} 异常: {e}")
        return False

def main():
    print("="*80)
    print("两帧完整测试 - scene-0916 frames 8 and 10")
    print("="*80)
    if not RUN_METHOD_A.exists():
        print(f"✗ 找不到: {RUN_METHOD_A}")
        return 1
    success1 = run_frame("scene-0916", 8)
    success2 = run_frame("scene-0916", 10)
    print("\n结果:")
    print(f"  Frame 8:  {'✓' if success1 else '✗'}")
    print(f"  Frame 10: {'✓' if success2 else '✗'}")
    return 0 if (success1 and success2) else 1

if __name__ == "__main__":
    sys.exit(main())
