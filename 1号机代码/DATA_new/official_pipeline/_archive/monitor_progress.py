#!/usr/bin/env python3
"""实时监控批量运行进度"""
import re
import time
import sys
from pathlib import Path

def parse_log(log_path):
    """解析日志文件提取关键指标"""
    if not Path(log_path).exists():
        return None

    with open(log_path, 'r', encoding='utf-8') as f:
        content = f.read()

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

    return {
        'completed': completed,
        'current_frame': current_frame,
        'current_round': current_round,
        'total_questions': total_questions,
        'coverage': coverage,
        'task_volume': task_volume,
        'avg_time': avg_time
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
    log_path = Path.home() / 'ADVTEST' / 'DATA_new' / 'v18_12h_run.log'

    print("实时监控启动...")
    print("日志文件:", log_path)
    print("=" * 80)

    try:
        while True:
            data = parse_log(log_path)

            # 清屏
            print("\033[2J\033[H", end='')

            if data is None:
                print("等待日志文件...")
                time.sleep(5)
                continue

            print("=" * 80)
            print(f"已完成帧数: {data['completed']}")
            print(f"当前帧: {data['current_frame'] or 'N/A'}")
            print(f"当前轮次: Round {data['current_round']}")
            print(f"已生成问题: {data['total_questions']}")
            if data['task_volume']:
                print(f"任务量: {data['task_volume']} (L2A+L2B)")
            print("=" * 80)

            # 覆盖率
            print("\n覆盖率:")
            for level in ['L0', 'L1', 'L2A', 'L2B']:
                if level in data['coverage']:
                    cov = data['coverage'][level]
                    bar = draw_progress_bar(cov['covered'], cov['total'])
                    print(f"  {level:4s} {bar} ({cov['covered']}/{cov['total']})")

            # 速度统计
            print("\n速度统计:")
            if data['avg_time']:
                print(f"  平均每题: {data['avg_time']:.2f}s")
                if data['task_volume'] and data['total_questions'] > 0:
                    remaining = data['task_volume'] - data['total_questions']
                    est_time = remaining * data['avg_time']
                    print(f"  预计剩余: {format_time(est_time)}")
            else:
                print("  平均每题: N/A")

            print("\n" + "=" * 80)
            print("按 Ctrl+C 退出监控")

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n监控已停止")
        sys.exit(0)

if __name__ == '__main__':
    main()
