#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实时监控Server 3批量运行进度 - V19版本（Windows）"""
import re
import time
import sys
from pathlib import Path
from datetime import datetime

def parse_log(log_path):
    """解析日志文件提取关键指标"""
    if not Path(log_path).exists():
        return None

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        try:
            with open(log_path, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception:
            return None

    # 检测启动阶段
    stage = "未启动"
    if "Loading plan" in content or "加载计划" in content or "Plan loaded" in content:
        stage = "加载计划中"
    if "Connecting to Neo4j" in content or "连接Neo4j" in content or "Neo4j connected" in content:
        stage = "连接数据库"
    if "Baseline audit" in content or "加载原题库" in content:
        stage = "分析原题库"
    if "帧" in content and "/600:" in content:
        stage = "生成问题中"

    # 原题库分析进度
    baseline_progress = None
    matches = re.findall(r'\[audit\s+(\d+)/(\d+)\]', content)
    if matches:
        last_match = matches[-1]
        baseline_progress = f"{last_match[0]}/{last_match[1]}"

    # 提取已完成帧数（V19格式：帧 120/600）
    completed = 0
    frame_matches = re.findall(r'帧\s+(\d+)/600:', content)
    if frame_matches:
        completed = int(frame_matches[-1])

    # 提取当前帧信息
    current_frame = None
    match = re.search(r'\[([^\]]+/f\d+)\]', content)
    if match:
        current_frame = match.group(1)
    else:
        match = re.search(r'帧\s+\d+/600:\s+(scene-[^/]+)/frame-(\d+)', content)
        if match:
            current_frame = f"{match.group(1)}/f{match.group(2)}"

    # 提取当前轮次和问题数
    round_matches = re.findall(r'\[Round (\d+)\]\s+batch=(\d+)', content)
    current_round = 0
    total_questions = 0
    if round_matches:
        current_round = int(round_matches[-1][0])
        total_questions = sum(int(q) for _, q in round_matches)

    # 提取覆盖率
    coverage = {}
    for level in ['L0', 'L1', 'L2A', 'L2B']:
        match = re.search(rf'{level}\s*:\s*\d+\s+gap\s*/\s*(\d+)\s+total\s*\(covered=(\d+)', content)
        if match:
            total = int(match.group(1))
            covered = int(match.group(2))
            coverage[level] = {'covered': covered, 'total': total}

    # 提取任务量
    task_volume = None
    matches = re.findall(r'batch=\d+\s+\(L2B=(\d+),\s*L2A=(\d+)\)', content)
    if matches:
        l2b_sum = sum(int(m[0]) for m in matches)
        l2a_sum = sum(int(m[1]) for m in matches)
        task_volume = l2b_sum + l2a_sum

    # 计算平均速度
    time_matches = re.findall(r'dt=(\d+)ms', content)
    if time_matches and total_questions > 0:
        total_time_ms = sum(int(t) for t in time_matches)
        avg_time = total_time_ms / total_questions / 1000
    else:
        avg_time = None

    last_update = "刚刚"

    return {
        'stage': stage,
        'baseline_progress': baseline_progress,
        'completed': completed,
        'current_frame': current_frame,
        'current_round': current_round,
        'total_questions': total_questions,
        'coverage': coverage,
        'task_volume': task_volume,
        'avg_time': avg_time,
        'last_update': last_update
    }

def draw_progress_bar(covered, total, width=40):
    """绘制进度条"""
    if total == 0:
        return ' ' * width + ' 0.0%'

    ratio = covered / total
    filled = int(width * ratio)
    bar = '#' * filled + '-' * (width - filled)
    return f"{bar} {ratio*100:.1f}%"

def format_time(seconds):
    """格式化时间"""
    if seconds is None:
        return 'N/A'
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h}h{m}m{s}s"

def main():
    log_path = Path('E:/本科生万云扬实验/ADVTEST/DATA_new/v19_server3.log')
    start_time = datetime.now()

    print("Server 3 实时监控启动 (V19 - Windows)...")
    print("日志文件:", log_path)
    print("任务: 大节点帧（25-40节点），共600帧")
    print("=" * 80)
    time.sleep(2)

    try:
        while True:
            try:
                data = parse_log(log_path)
            except Exception as e:
                print(f"\n[ERROR] 解析日志失败: {e}")
                time.sleep(5)
                continue

            current_time = datetime.now()
            elapsed = current_time - start_time

            print("\n" + "=" * 80)
            print(f"[Server 3 - V19] 运行时间: {str(elapsed).split('.')[0]}")
            print("=" * 80)

            if data is None:
                print("状态: 等待日志文件生成...")
            else:
                print(f"状态: {data['stage']}")
                if data['baseline_progress']:
                    print(f"原题库分析: {data['baseline_progress']}")
                print(f"已完成帧数: {data['completed']}/600")
                print(f"当前帧: {data['current_frame'] or 'N/A'}")
                print(f"当前轮次: Round {data['current_round']}")
                print(f"已生成问题: {data['total_questions']}")
                if data['task_volume']:
                    print(f"当前帧任务量: {data['task_volume']} (L2A+L2B)")

                print("-" * 80)
                print("覆盖率:")
                for level in ['L0', 'L1', 'L2A', 'L2B']:
                    if level in data['coverage']:
                        cov = data['coverage'][level]
                        bar = draw_progress_bar(cov['covered'], cov['total'])
                        print(f"  {level:4s} {bar} ({cov['covered']}/{cov['total']})")

                print("-" * 80)
                print("速度统计:")
                if data['avg_time']:
                    print(f"  平均每题: {data['avg_time']:.2f}s")
                    if data['completed'] > 0:
                        avg_frame_time = data['total_questions'] * data['avg_time'] / data['completed']
                        remaining_frames = 600 - data['completed']
                        total_remaining = remaining_frames * avg_frame_time
                        print(f"  全部任务预计剩余: {format_time(total_remaining)}")

            print("=" * 80)
            print(f"刷新时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}  (按 Ctrl+C 退出)")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n监控已停止")
        sys.exit(0)

if __name__ == '__main__':
    main()
