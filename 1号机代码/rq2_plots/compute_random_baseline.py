#!/usr/bin/env python3
"""Compute random baseline for RQ2 by shuffling per-question coverage deltas.

For each frame, extract delta coverage from the existing curves, shuffle
the order N times (Monte Carlo), and average. This simulates random question
ordering as a baseline for comparison.

Runs on extracted data (rq2_curves.npz) — no HDD access needed.

Usage:
    python compute_random_baseline.py [--input extracted_r1] [--trials 50]
"""
import argparse
import json
import os
import time
import numpy as np


def compute_random_baseline(curves, n_questions, n_trials=50, seed=42):
    """Shuffle deltas per frame, average over trials.

    Returns: (random_curves_mean, random_curves_std) same shape as curves.
    """
    rng = np.random.RandomState(seed)
    n_frames, curve_len = curves.shape

    # Accumulate stats
    random_sum = np.zeros((n_frames, curve_len), dtype=np.float64)
    random_sq = np.zeros((n_frames, curve_len), dtype=np.float64)

    t0 = time.time()
    for trial in range(n_trials):
        if (trial + 1) % 10 == 0:
            elapsed = time.time() - t0
            print(f"  Trial {trial+1}/{n_trials} ({elapsed:.1f}s)")

        for i in range(n_frames):
            nq = int(n_questions[i])
            if nq == 0:
                # Trivial: constant
                random_sum[i, :] += curves[i, 0]
                random_sq[i, :] += curves[i, 0] ** 2
                continue

            init_cov = float(curves[i, 0])
            # Deltas: coverage gain from each question
            deltas = np.diff(curves[i, :nq + 1]).copy()  # shape (nq,)

            # Shuffle
            rng.shuffle(deltas)

            # Recompute cumulative
            rc = np.empty(curve_len, dtype=np.float64)
            rc[0] = init_cov
            rc[1:nq + 1] = init_cov + np.cumsum(deltas)
            if nq < curve_len - 1:
                rc[nq + 1:] = rc[nq]

            random_sum[i, :] += rc
            random_sq[i, :] += rc ** 2

    mean = (random_sum / n_trials).astype(np.float32)
    var = (random_sq / n_trials) - (random_sum / n_trials) ** 2
    std = np.sqrt(np.clip(var, 0, None)).astype(np.float32)

    return mean, std


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=os.path.join(os.path.dirname(__file__), "extracted_r1"))
    parser.add_argument("--trials", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print(f"Loading curves from {args.input}")
    data = np.load(os.path.join(args.input, "rq2_curves.npz"))
    curves_l0 = data["curves_l0"]
    curves_l1 = data["curves_l1"]
    curves_l2 = data["curves_l2"]
    n_questions = data["n_questions"]
    print(f"Loaded {curves_l2.shape[0]} frames, max_q={curves_l2.shape[1]-1}")

    for level, curves in [("L0", curves_l0), ("L1", curves_l1), ("L2", curves_l2)]:
        print(f"\n=== {level}: {args.trials} trials ===")
        mean, std = compute_random_baseline(curves, n_questions, args.trials, args.seed)

        out_path = os.path.join(args.input, f"random_{level.lower()}_mean.npy")
        np.save(out_path, mean)
        out_path2 = os.path.join(args.input, f"random_{level.lower()}_std.npy")
        np.save(out_path2, std)
        print(f"  Saved {out_path}")

        # Quick stats: avg random curve at a few points
        avg_curve = np.mean(mean, axis=0)
        nq_nz = n_questions[n_questions > 0]
        p50 = int(np.median(nq_nz))
        p90 = int(np.percentile(nq_nz, 90))
        print(f"  Avg random {level} at Q=0: {avg_curve[0]:.4f}")
        print(f"  Avg random {level} at Q=median({p50}): {avg_curve[min(p50, len(avg_curve)-1)]:.4f}")
        print(f"  Avg random {level} at Q=P90({p90}): {avg_curve[min(p90, len(avg_curve)-1)]:.4f}")

    print("\nDone! Now re-run plot_rq2.py with --random flag to overlay.")


if __name__ == "__main__":
    main()
