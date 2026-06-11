import os
import json
import csv
import time
import collections
from pathlib import Path
from multiprocessing import Pool, cpu_count
import pandas as pd

OUTPUTS = Path("E:/Project/ADVTEST/1号机代码/DATA_new/outputs")

def process_single_frame(frame_dir_path):
    try:
        frame_dir = Path(frame_dir_path)
        frame_name = frame_dir.name
        
        init_file = frame_dir / "offline" / "initial_coverage" / f"{frame_name}_initial_coverage.jsonl"
        gen_file = frame_dir / "generation" / "qa" / f"{frame_name}_generated.jsonl"
        summary_file = frame_dir / "reports" / f"{frame_name}_summary.json"
        summary_csv = frame_dir / "reports" / f"{frame_name}_summary.csv"
        ic_csv = frame_dir / "reports" / f"{frame_name}_incremental_coverage.csv"
        manifest_file = frame_dir / "manifest.json"
        
        # 1. Load initial coverage
        init_l0 = set()
        init_l1 = set()
        init_l2 = set()
        init_count = 0
        if init_file.exists():
            with open(init_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    fp = data.get("coverage_footprint") or {}
                    init_l0.update(fp.get("l0") or [])
                    init_l1.update(fp.get("l1") or [])
                    init_l2.update(fp.get("l2") or [])
                    init_count += 1
                    
        # 2. Load generated QA
        if not gen_file.exists():
            return {"frame_name": frame_name, "status": "missing_generated_qa", "before": 0, "after": 0}
            
        generated_qas = []
        with open(gen_file, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                generated_qas.append(json.loads(line))
                
        # 3. Filter
        seen_l0 = set(init_l0)
        seen_l1 = set(init_l1)
        seen_l2 = set(init_l2)
        pruned_qas = []
        
        for qa in generated_qas:
            fp = qa.get("coverage_footprint") or {}
            l2 = fp.get("l2") or []
            new_l2 = {str(x) for x in l2} - seen_l2
            if new_l2:
                pruned_qas.append(qa)
                seen_l0.update(fp.get("l0") or [])
                seen_l1.update(fp.get("l1") or [])
                seen_l2.update(fp.get("l2") or [])
                
        discarded = len(generated_qas) - len(pruned_qas)
        
        # 4. Overwrite generated QA
        for idx, qa in enumerate(pruned_qas, start=1):
            qa["question_id"] = str(idx)
            
        with open(gen_file, "w", encoding="utf-8") as f:
            for qa in pruned_qas:
                f.write(json.dumps(qa, ensure_ascii=False) + "\n")
                
        # 5. Load and update summary.json
        if summary_file.exists():
            with open(summary_file, "r", encoding="utf-8") as f:
                summary = json.load(f)
                
            summary["generated"] = len(pruned_qas)
            summary["covered_gap_count"] = len(seen_l2)
            summary["uncovered_gap_count"] = max(summary.get("pool_size", 0) - len(seen_l2), 0)
            
            families_counts = collections.Counter(r.get("l2_family", r.get("template_id", "")) for r in pruned_qas)
            summary["families"] = dict(families_counts)
            
            summary["coverage"] = {
                "l0": len(seen_l0),
                "l1": len(seen_l1),
                "l2": len(seen_l2)
            }
            
            init_cov_summary = {
                "records": init_count,
                "coverage": {
                    "l0": len(init_l0),
                    "l1": len(init_l1),
                    "l2": len(init_l2)
                }
            }
            summary.setdefault("universe_stats", {})["initial_coverage"] = init_cov_summary
            
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        else:
            summary = {}
            init_cov_summary = {}

        # 6. Load and update summary.csv
        if summary_csv.exists():
            try:
                sdf = pd.read_csv(summary_csv)
                if not sdf.empty:
                    sdf.loc[0, "generated"] = len(pruned_qas)
                    sdf.loc[0, "covered_gap_count"] = len(seen_l2)
                    sdf.loc[0, "uncovered_gap_count"] = max(sdf.loc[0, "pool_size"] - len(seen_l2), 0)
                    sdf.loc[0, "coverage_l0"] = len(seen_l0)
                    sdf.loc[0, "coverage_l1"] = len(seen_l1)
                    sdf.loc[0, "coverage_l2"] = len(seen_l2)
                    families_counts = collections.Counter(r.get("l2_family", r.get("template_id", "")) for r in pruned_qas)
                    sdf.loc[0, "families_json"] = json.dumps(dict(families_counts))
                    sdf.to_csv(summary_csv, index=False)
            except Exception:
                pass

        # 7. Update manifest.json
        if manifest_file.exists():
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                manifest.setdefault("summary", {})["initial_coverage"] = init_cov_summary
                with open(manifest_file, "w", encoding="utf-8") as f:
                    json.dump(manifest, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        # 8. Re-generate incremental_coverage.csv
        if ic_csv.exists() or len(pruned_qas) > 0:
            total_l0 = len(seen_l0)
            total_l1 = len(seen_l1)
            total_l2 = summary.get("pool_size") or (summary.get("coverage") or {}).get("l2") or len(seen_l2)
            total_l0 = max(total_l0, 1)
            total_l1 = max(total_l1, 1)
            total_l2 = max(total_l2, 1)
            
            seen_l0_cum = set(init_l0)
            seen_l1_cum = set(init_l1)
            seen_l2_cum = set(init_l2)
            
            rows = []
            for idx, qa in enumerate(pruned_qas, start=1):
                fp = qa.get("coverage_footprint") or {}
                l0 = {str(x) for x in fp.get("l0", [])}
                l1 = {str(x) for x in fp.get("l1", [])}
                l2 = {str(x) for x in fp.get("l2", [])}
                
                new_l0 = l0 - seen_l0_cum
                new_l1 = l1 - seen_l1_cum
                new_l2 = l2 - seen_l2_cum
                
                seen_l0_cum.update(l0)
                seen_l1_cum.update(l1)
                seen_l2_cum.update(l2)
                
                rows.append({
                    "order_index": idx,
                    "question_id": str(idx),
                    "selection_phase": qa.get("selection_phase", ""),
                    "l2_family": qa.get("l2_family", qa.get("template_id", "")),
                    "timestamp_start": qa.get("timestamp_start", ""),
                    "timestamp_end": qa.get("timestamp_end", ""),
                    "generation_elapsed_ms": qa.get("generation_elapsed_ms", 0),
                    "question": qa.get("question", ""),
                    "raw_l0": len(l0),
                    "raw_l1": len(l1),
                    "raw_l2": len(l2),
                    "delta_l0": len(new_l0),
                    "delta_l1": len(new_l1),
                    "delta_l2": len(new_l2),
                    "cum_l0": len(seen_l0_cum),
                    "cum_l1": len(seen_l1_cum),
                    "cum_l2": len(seen_l2_cum),
                    "coverage_rate_l0": len(seen_l0_cum) / total_l0,
                    "coverage_rate_l1": len(seen_l1_cum) / total_l1,
                    "coverage_rate_l2": len(seen_l2_cum) / total_l2,
                })
                
            if rows:
                with open(ic_csv, "w", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
                    
        return {"frame_name": frame_name, "status": "success", "before": len(generated_qas), "after": len(pruned_qas)}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return {"frame_name": frame_dir_path, "status": f"error: {str(e)}\n{tb}", "before": 0, "after": 0}


def main():
    t0 = time.time()
    
    frame_dirs = []
    for d in sorted(OUTPUTS.iterdir()):
        if d.is_dir() and "_frame" in d.name:
            frame_dirs.append(str(d))
            
    total_frames = len(frame_dirs)
    print(f"Starting pruning and patching of {total_frames} frames using multiprocessing...")
    
    num_workers = max(1, cpu_count() - 1)
    print(f"Using {num_workers} processes.")
    
    total_before = 0
    total_after = 0
    success_count = 0
    error_count = 0
    
    with Pool(num_workers) as pool:
        results = pool.imap_unordered(process_single_frame, frame_dirs, chunksize=10)
        
        for idx, res in enumerate(results, start=1):
            status = res["status"]
            frame_name = res["frame_name"]
            before = res["before"]
            after = res["after"]
            
            if status == "success":
                total_before += before
                total_after += after
                success_count += 1
            else:
                print(f"[{idx}/{total_frames}] Error on frame {frame_name}: {status}")
                error_count += 1
                
            if idx % 500 == 0:
                print(f"Processed {idx}/{total_frames} frames... (current total questions: {total_before} -> {total_after})", flush=True)
                
    elapsed = time.time() - t0
    print("\n=== Pruning and Patching Finished ===")
    print(f"Processed: {success_count} success, {error_count} error")
    print(f"Total questions before: {total_before:,}")
    print(f"Total questions after:  {total_after:,}")
    print(f"Pruned questions:       {total_before - total_after:,}")
    print(f"Elapsed time:           {elapsed:.1f}s")

if __name__ == "__main__":
    main()
