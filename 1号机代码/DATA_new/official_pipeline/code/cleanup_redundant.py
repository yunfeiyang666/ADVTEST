"""
Clean redundant output files from already-generated frames.
Removes: round1/round2/all (jsonl+csv), generated.csv, generated_meta.csv,
         coverage_state/, candidate_potential (jsonl+csv), incremental_coverage.jsonl
Keeps: _generated.jsonl, _summary.json, _summary.csv, manifest.json, _incremental_coverage.csv
"""
import os
import re
from pathlib import Path

OUTPUTS_ROOT = Path(r"E:\Project\ADVTEST\1号机代码\DATA_new\outputs")

# Patterns of files to DELETE
DELETE_PATTERNS = [
    r"_round1\.(jsonl|csv)$",
    r"_round2\.(jsonl|csv)$",
    r"_all\.(jsonl|csv)$",
    r"_generated\.csv$",
    r"_generated_meta\.csv$",
    r"_coverage_state\.json$",
    r"_candidate_potential\.(jsonl|csv)$",
    r"_incremental_coverage\.jsonl$",
]

DELETE_RE = re.compile("|".join(f"({p})" for p in DELETE_PATTERNS))

# Also delete empty coverage_state directories
def clean_frame(frame_dir: Path) -> int:
    """Remove redundant files from a single frame. Returns bytes freed."""
    freed = 0
    gen_dir = frame_dir / "generation"
    reports_dir = frame_dir / "reports"
    
    for search_dir in [gen_dir, reports_dir]:
        if not search_dir.exists():
            continue
        for f in search_dir.rglob("*"):
            if f.is_file() and DELETE_RE.search(f.name):
                size = f.stat().st_size
                f.unlink()
                freed += size
    
    # Remove empty coverage_state dir
    cs_dir = gen_dir / "coverage_state"
    if cs_dir.exists():
        try:
            # Remove all files in it
            for f in cs_dir.iterdir():
                if f.is_file():
                    freed += f.stat().st_size
                    f.unlink()
            cs_dir.rmdir()
        except OSError:
            pass
    
    return freed


def main():
    total_freed = 0
    cleaned = 0
    
    for entry in sorted(OUTPUTS_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        gen_dir = entry / "generation"
        if not gen_dir.exists():
            continue
        
        freed = clean_frame(entry)
        if freed > 0:
            cleaned += 1
            total_freed += freed
            if cleaned <= 5 or cleaned % 50 == 0:
                print(f"  Cleaned {entry.name}: freed {freed/1024/1024:.1f} MB", flush=True)
    
    print(f"\n[cleanup] Done: {cleaned} frames cleaned, {total_freed/1024/1024/1024:.2f} GB freed", flush=True)


if __name__ == "__main__":
    main()
