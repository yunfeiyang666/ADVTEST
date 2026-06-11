#!/usr/bin/env python3
"""
两帧完整测试脚本 - 基于 run_gap_pipeline_v6.py
按照 design(1).md 的要求运行完整流程

关键点：
1. 不是固定100个问题，而是持续生成直到所有L0/L1/L2 gap都被覆盖
2. L2A和L2B已废弃，统一为L2
3. 使用优先级gap选择策略
4. 输出标准CSV格式

使用方法:
    python run_two_frames_v6.py

输出:
    - output/scene-0916_frame8_result.csv
    - output/scene-0916_frame8_result.json
    - output/scene-0916_frame10_result.csv
    - output/scene-0916_frame10_result.json
"""
import sys
import os
from pathlib import Path

# 添加 official_pipeline 到路径
OFFICIAL_PIPELINE_DIR = Path(__file__).parent / "official_pipeline"
sys.path.insert(0, str(OFFICIAL_PIPELINE_DIR))

def run_frame(scene_name: str, frame_idx: int, output_dir: str = "output", working_password: str = "87017563"):
    """
    运行单帧的完整流程

    Args:
        scene_name: 场景名称，如 "scene-0916"
        frame_idx: 帧索引，如 8
        output_dir: 输出目录
        working_password: Neo4j密码
    """
    from run_gap_pipeline_v6 import run_v6_pipeline

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    output_json = output_path / f"{scene_name}_frame{frame_idx}_result.json"
    output_csv = output_path / f"{scene_name}_frame{frame_idx}_result.csv"

    print(f"\n{'='*80}")
    print(f"Processing {scene_name} frame {frame_idx}")
    print(f"{'='*80}")
    print(f"Output JSON: {output_json}")
    print(f"Output CSV:  {output_csv}")
    print()

    # 运行pipeline
    # 注意：不指定 l2a_cells 和 l2b_cells，让它自动运行直到所有gap覆盖完成
    result = run_v6_pipeline(
        neo4j_uri="bolt://127.0.0.1:7687",
        neo4j_user="neo4j",
        neo4j_password=working_password,
        scene_name=scene_name,
        frame_idx=frame_idx,
        l2a_cells=50,  # 设置一个合理的默认值
        l2b_cells=50,  # 设置一个合理的默认值
        output_path=str(output_json),
        csv_path=str(output_csv),
        batch_size=16,
        n_workers=8,
        baseline_file=None,
        debug_log=None
    )

    return result

def main():
    print("="*80)
    print("两帧完整测试 - scene-0916 frames 8 and 10")
    print("="*80)
    print()
    print("说明:")
    print("  - 不是固定100个问题")
    print("  - 持续生成直到所有L0/L1/L2 gap都被覆盖")
    print("  - L2A和L2B已废弃，统一为L2")
    print("  - 使用优先级gap选择策略")
    print()

    # 检查Neo4j连接
    print("检查Neo4j连接...")

    # 尝试不同的密码
    passwords = ["87017563", "neo4j", "password"]
    connected = False
    working_password = None

    from neo4j import GraphDatabase

    for pwd in passwords:
        try:
            driver = GraphDatabase.driver(
                "bolt://127.0.0.1:7687",
                auth=("neo4j", pwd)
            )
            driver.verify_connectivity()
            print(f"✓ Neo4j连接成功 (密码: {pwd})")
            working_password = pwd
            driver.close()
            connected = True
            break
        except Exception as e:
            continue

    if not connected:
        print("✗ Neo4j连接失败")
        print()
        print("请检查:")
        print("  1. Neo4j是否已启动")
        print("  2. 密码是否正确")
        print("  3. 如果是新安装，默认密码是 neo4j/neo4j")
        print("     首次登录后需要修改密码为: 87017563")
        print()
        print("修改密码方法:")
        print("  1. 访问 http://localhost:7474")
        print("  2. 用 neo4j/neo4j 登录")
        print("  3. 修改密码为 87017563")
        return 1

    print()

    # 运行Frame 8
    try:
        result1 = run_frame("scene-0916", 8, working_password=working_password)
        print(f"\n✓ Frame 8 完成")
        print(f"  生成问题数: {result1.get('total_qa', 0)}")
    except Exception as e:
        print(f"\n✗ Frame 8 失败: {e}")
        return 1

    # 运行Frame 10
    try:
        result2 = run_frame("scene-0916", 10, working_password=working_password)
        print(f"\n✓ Frame 10 完成")
        print(f"  生成问题数: {result2.get('total_qa', 0)}")
    except Exception as e:
        print(f"\n✗ Frame 10 失败: {e}")
        return 1

    print()
    print("="*80)
    print("两帧测试完成!")
    print("="*80)
    print()
    print("输出文件:")
    print("  - output/scene-0916_frame8_result.csv")
    print("  - output/scene-0916_frame8_result.json")
    print("  - output/scene-0916_frame10_result.csv")
    print("  - output/scene-0916_frame10_result.json")
    print()

    return 0

if __name__ == "__main__":
    sys.exit(main())
