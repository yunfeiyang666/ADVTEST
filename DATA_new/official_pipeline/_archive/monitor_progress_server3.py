#!/usr/bin/env python3
"""实时监控Server 3批量运行进度"""
import re
import time
import sys
from pathlib import Path
from datetime import datetime

def parse_log(log_path):
    """解析日志文件提取关键指标"""
    if not Path(log_path).exists():
        return None

    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检测启动阶段
    stage = "未启动"
    if "Loading plan" in content or "加载计划" in content:
        stage = "加载计划中"
    if "Connecting to Neo4j" in content or "连接Neo4j" in content:
        stage = "连接数据库"
    if "Loading baseline" in content or "加载原题库" in content:
        stage = "分析原题库"
    if "Baseline analysis complete" in content or "原题库分析完成" in content:
        stage = "原题库分析完成"
    if "[Frame Start]" in content:
        stage = "生成问题中"

    # 原题库分析进度
    baseline_progress = None
    match = re.search(r'Baseline.*?(\d+)/(\d+)', content)
    if match:
        baseline_progress = f"{match.group(1)}/{match.group(2)}"

    # 提取已完成帧数
    completed = len(re.findall(r'\[Frame Complete\]', content))

    # 提取当前帧信息
    current_frame = None
    match = re.search(r'\[Frame Start\] scene=([^\s]+) frame=(\d+)', content)
    if match:
        current_frame = f"{match.group(1)}/f{match.group(2)}"

    # 提取当前轮次和问题数
    round_match = re.findall(r'\[Round (\d+)\].*?questions=(\d+)', content)
    current_round = 0
    total_questions = 0
    if round_match:
        current_round = int(round_match[-1][0])
        total_questions = sum(int(q) for _, q in round_match)

    # 提取覆盖率
    coverage = {}
    for level in ['L0', 'L1', 'L2A', 'L2B']:
        match = re.search(rf'\[{level}\] covered=(\d+)/(\d+)', content)
        if match:
            covered = int(match.group(1))
            total = int(match.group(2))
            coverage[level] = {'covered': covered, 'total': total}

    # 提取任务量
    task_volume = None
    match = re.search(r'L2A=(\d+) L2B=(\d+)', content)
    if match:
        task_volume = int(match.group(1)) + int(match.group(2))

    # 计算平均速度
    time_matches = re.findall(r'elapsed=(\d+)ms', content)
    if time_matches and total_questions > 0:
        total_time_ms = sum(int(t) for t in time_matches)
        avg_time = total_time_ms / total_questions / 1000  # 转换为秒
    else:
        avg_time = None

    # 检查最后一行时间，判断是否卡住
    lines = content.strip().split('\n')
    last_update = "未知"
    if lines:
        for line in reversed(lines[-10:]):
            if line.strip():
                last_update = "刚刚"
                break

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
        return '░' * width + ' 0.0%'

    ratio = covered / total
    filled = int(width * ratio)
    bar = '█' * filled + '░' * (width - filled)
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
    log_path = Path.home() / 'ADVTEST' / 'DATA_new' / 'v18_server3.log'
    start_time = datetime.now()

    print("\033[2J\033[H", end='')
    print("Server 3 实时监控启动...")
    print("日志文件:", log_path)
    print("任务: 大节点帧（25-40节点），共600帧")
    print("=" * 80)
    time.sleep(2)

    try:
        while True:
            data = parse_log(log_path)
            current_time = datetime.now()
            elapsed = current_time - start_time

            print("\033[H", end='')

            print("=" * 80)
            print(f"【Server 3 - 大节点任务】 运行时间: {str(elapsed).split('.')[0]}")
            print("=" * 80)

            if data is None:
                print("状态: 等待日志文件生成...                                    ")
                print(" " * 80)
            else:
                print(f"状态: {data['stage']:30s}                    ")

                if data['baseline_progress']:
                    print(f"原题库分析: {data['baseline_progress']:20s}                    ")
                else:
                    print(" " * 80)

                print(f"已完成帧数: {data['completed']}/600                                    ")
                print(f"当前帧: {data['current_frame'] or 'N/A':30s}                    ")
                print(f"当前轮次: Round {data['current_round']:4d}                                    ")
                print(f"已生成问题: {data['total_questions']:8d}                                    ")

                if data['task_volume']:
                    print(f"当前帧任务量: {data['task_volume']} (L2A+L2B)                                    ")
                else:
                    print(" " * 80)

                print("-" * 80)
                print("覆盖率:                                                                    ")

                for level in ['L0', 'L1', 'L2A', 'L2B']:
                    if level in data['coverage']:
                        cov = data['coverage'][level]
                        bar = draw_progress_bar(cov['covered'], cov['total'])
                        print(f"  {level:4s} {bar} ({cov['covered']}/{cov['total']})                    ")
                    else:
                        print(f"  {level:4s} " + " " * 60)

                print("-" * 80)
                print("速度统计:                                                                    ")

                if data['avg_time']:
                    print(f"  平均每题: {data['avg_time']:.2f}s                                    ")

                    if data['task_volume'] and data['total_questions'] > 0:
                        remaining = data['task_volume'] - data['total_questions']
                        est_time = remaining * data['avg_time']
                        print(f"  当前帧预计剩余: {format_time(est_time):20s}                    ")
                    else:
                        print(" " * 80)

                    if data['completed'] > 0:
                        avg_frame_time = data['total_questions'] * data['avg_time'] / data['completed']
                        remaining_frames = 600 - data['completed']
                        total_remaining = remaining_frames * avg_frame_time
                        print(f"  全部任务预计剩余: {format_time(total_remaining):20s}                    ")
                    else:
                        print(" " * 80)
                else:
                    print("  平均每题: N/A                                                        ")
                    print(" " * 80)
                    print(" " * 80)

            print("=" * 80)
            print(f"刷新时间: {current_time.strftime('%Y-%m-%d %H:%M:%S')}  (按 Ctrl+C 退出)        ")
            print(" " * 80)
            print(" " * 80)

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n监控已停止")
        sys.exit(0)

if __name__ == '__main__':
    main()
