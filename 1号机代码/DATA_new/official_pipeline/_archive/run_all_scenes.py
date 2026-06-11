#!/usr/bin/env python3
"""
全量场景运行脚本
自动扫描filtered_scene_graphs目录，遍历所有场景和帧
"""
import os
import sys
import re
import subprocess
from pathlib import Path
from datetime import datetime

# 配置
FILTERED_SG_DIR = Path(__file__).parent.parent.parent.parent / "filtered_scene_graphs"
RUN_METHOD_A = Path(__file__).parent / "run_method_a.py"

def get_all_scene_frames():
    """扫描filtered_scene_graphs目录，获取所有场景和帧"""
    scene_frames = []

    if not FILTERED_SG_DIR.exists():
        print(f"错误: 目录不存在 {FILTERED_SG_DIR}")
        return scene_frames

    pattern = re.compile(r'scene-(\d+)_frame(\d+)_scene_graph\.json')

    for file in FILTERED_SG_DIR.glob("*.json"):
        match = pattern.match(file.name)
        if match:
            scene_id = f"scene-{match.group(1)}"
            frame_id = int(match.group(2))
            scene_frames.append((scene_id, frame_id, file.name))

    # 按场景和帧排序
    scene_frames.sort(key=lambda x: (x[0], x[1]))

    return scene_frames

def modify_run_method_a(scene_id, frame_id):
    """修改run_method_a.py中的SCENE_ID和FRAME_ID"""
    content = RUN_METHOD_A.read_text(encoding='utf-8')

    # 替换SCENE_ID和FRAME_ID
    content = re.sub(
        r'SCENE_ID\s*=\s*"scene-\d+"',
        f'SCENE_ID    = "{scene_id}"',
        content
    )
    content = re.sub(
        r'FRAME_ID\s*=\s*\d+',
        f'FRAME_ID    = {frame_id}',
        content
    )

    RUN_METHOD_A.write_text(content, encoding='utf-8')
    print(f"  [Config] Updated: SCENE_ID={scene_id}, FRAME_ID={frame_id}")

def run_scene_frame(scene_id, frame_id, sg_file):
    """运行单个场景帧"""
    print(f"\n{'='*70}")
    print(f"  Running: {scene_id} frame {frame_id}")
    print(f"  File: {sg_file}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    # 修改配置
    try:
        modify_run_method_a(scene_id, frame_id)
    except Exception as e:
        print(f"✗ Failed to modify config: {e}")
        return False

    # 设置环境变量
    env = os.environ.copy()
    env.update({
        'VQA_CONTEXT_CYPHER_MODE': 'batch_llm',
        'VQA_CTX_BATCH_STRATEGY': 'hybrid',
        'VQA_CTX_HINT_MAX_TOKENS': '1280',
        'VQA_CTX_BATCH_CHUNK_SIZE': '8',
        'VQA_CTX_BATCH_N_WORKERS': '4',
        'VQA_QUESTION_MODE': 'llm_batch',
        'VQA_EXCEL_BATCH_WRITE': 'true',
        'VQA_Q_LLM_CHUNK_SIZE': '16',
        'VQA_LLM_TIMEOUT_READ': '240',
    })

    # 运行
    log_file = Path(__file__).parent / f"logs/run_{scene_id}_f{frame_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log_file.parent.mkdir(exist_ok=True)

    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            result = subprocess.run(
                [sys.executable, str(RUN_METHOD_A)],
                env=env,
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=7200  # 2小时超时
            )

        if result.returncode == 0:
            print(f"✓ {scene_id} frame {frame_id} completed")
            print(f"  Log: {log_file}")
            return True
        else:
            print(f"✗ {scene_id} frame {frame_id} failed (exit code: {result.returncode})")
            print(f"  Log: {log_file}")
            return False
    except subprocess.TimeoutExpired:
        print(f"✗ {scene_id} frame {frame_id} timeout (>2h)")
        print(f"  Log: {log_file}")
        return False
    except Exception as e:
        print(f"✗ {scene_id} frame {frame_id} error: {e}")
        print(f"  Log: {log_file}")
        return False

def main():
    print("="*70)
    print("  全量场景运行")
    print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    # 获取所有场景帧
    scene_frames = get_all_scene_frames()

    if not scene_frames:
        print("错误: 未找到任何场景图文件")
        return

    print(f"\n找到 {len(scene_frames)} 个场景帧:")
    for scene_id, frame_id, sg_file in scene_frames:
        print(f"  - {scene_id} frame {frame_id} ({sg_file})")

    # 运行所有场景
    success_count = 0
    fail_count = 0

    for i, (scene_id, frame_id, sg_file) in enumerate(scene_frames, 1):
        print(f"\n[{i}/{len(scene_frames)}] Processing {scene_id} frame {frame_id}...")

        if run_scene_frame(scene_id, frame_id, sg_file):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n{'='*70}")
    print(f"  全量运行完成")
    print(f"  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  成功: {success_count}/{len(scene_frames)}")
    print(f"  失败: {fail_count}/{len(scene_frames)}")
    print("="*70)

if __name__ == '__main__':
    main()
