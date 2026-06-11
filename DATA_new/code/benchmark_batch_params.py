#!/usr/bin/env python3
"""
benchmark_batch_params.py - 批处理参数基准测试

测试不同的 BATCH_SIZE 和 N_WORKERS 配置，找到最优组合
目标：平均每题时间 ≈ 1秒
"""
import time
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent / "code" / "official_pipeline"))

from run_gap_pipeline_v6 import run_v6_pipeline


def benchmark_config(batch_size: int, n_workers: int, n_questions: int = 50):
    """测试特定配置的性能"""
    print(f"\n{'='*60}")
    print(f"Testing: BATCH_SIZE={batch_size}, N_WORKERS={n_workers}")
    print(f"{'='*60}")

    start_time = time.time()

    try:
        # 运行pipeline生成n_questions个问题
        stats = run_v6_pipeline(
            neo4j_uri="bolt://localhost:7687",
            neo4j_user="neo4j",
            neo4j_password="87017563",
            l2a_cells=n_questions // 2,
            l2b_cells=n_questions // 2,
            scene_name="scene-0916",
            frame_idx=8,
            output_path=f"output/benchmark_b{batch_size}_w{n_workers}.json",
            csv_path=f"output/benchmark_b{batch_size}_w{n_workers}.csv",
            debug_log=f"output/benchmark_b{batch_size}_w{n_workers}.log",
            batch_size=batch_size,
            n_workers=n_workers,
        )

        elapsed = time.time() - start_time

        # 从stats中获取实际生成的问题数
        actual_questions = stats.get("n_qa_generated", n_questions)
        avg_time = elapsed / actual_questions if actual_questions > 0 else 0

        print(f"\nResults:")
        print(f"  Total time: {elapsed:.2f}s")
        print(f"  Questions generated: {actual_questions}")
        print(f"  Avg time per question: {avg_time:.3f}s")
        print(f"  Questions per second: {actual_questions/elapsed:.2f}")

        return {
            "batch_size": batch_size,
            "n_workers": n_workers,
            "total_time": elapsed,
            "questions": actual_questions,
            "avg_time": avg_time,
            "qps": actual_questions / elapsed if elapsed > 0 else 0,
            "success": True
        }

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()

        elapsed = time.time() - start_time
        return {
            "batch_size": batch_size,
            "n_workers": n_workers,
            "total_time": elapsed,
            "questions": 0,
            "avg_time": 0,
            "qps": 0,
            "success": False,
            "error": str(e)
        }


def main():
    print("="*60)
    print("Batch Parameter Benchmark")
    print("="*60)
    print("Goal: Find optimal BATCH_SIZE and N_WORKERS for ~1s/question")
    print()

    # 测试配置矩阵
    configs = [
        (8, 4),   # 小批次，少线程
        (8, 8),   # 小批次，多线程
        (12, 8),  # 当前配置
        (16, 8),  # 中批次
        (24, 8),  # 大批次
        (16, 12), # 中批次，更多线程
        (32, 8),  # 超大批次
    ]

    results = []
    for batch_size, n_workers in configs:
        result = benchmark_config(batch_size, n_workers, n_questions=50)
        results.append(result)

        # 短暂休息，避免API限流
        time.sleep(2)

    # 输出汇总
    print(f"\n{'='*80}")
    print("Summary")
    print(f"{'='*80}")
    print(f"{'BATCH_SIZE':<12} {'N_WORKERS':<12} {'Questions':<12} {'Avg Time':<12} {'QPS':<12} {'Status':<12}")
    print("-" * 80)

    for r in results:
        status = "OK" if r["success"] else "FAILED"
        print(f"{r['batch_size']:<12} {r['n_workers']:<12} "
              f"{r['questions']:<12} {r['avg_time']:.3f}s{' '*6} "
              f"{r['qps']:.2f}{' '*6} {status:<12}")

    # 找到最接近1s的配置
    successful = [r for r in results if r["success"] and r["avg_time"] > 0]
    if successful:
        best = min(successful, key=lambda x: abs(x['avg_time'] - 1.0))
        print(f"\n{'='*80}")
        print("Best config for ~1s/question:")
        print(f"  BATCH_SIZE={best['batch_size']}, N_WORKERS={best['n_workers']}")
        print(f"  Avg time: {best['avg_time']:.3f}s")
        print(f"  QPS: {best['qps']:.2f}")
        print(f"{'='*80}")
    else:
        print("\nNo successful runs to analyze.")


if __name__ == "__main__":
    main()
