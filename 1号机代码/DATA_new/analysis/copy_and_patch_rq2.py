import shutil
import re
from pathlib import Path

src_dir = Path("E:/Project/ADVTEST/1号机代码/DATA_new/official_pipeline/rq2_plots")
dst_dir = Path("E:/Project/ADVTEST/1号机代码/DATA_new/analysis")

print("Copying and patching files...")

# 1. rq2_analysis_config.py
config_content = (src_dir / "rq2_analysis_config.py").read_text(encoding="utf-8")
config_content = config_content.replace(
    'OUTPUTS_ROOT = "/mnt/data4/yunyang/ADVTEST_DATA/outputs"',
    'OUTPUTS_ROOT = "E:/Project/ADVTEST/1号机代码/DATA_new/outputs"'
)
config_content = config_content.replace(
    'EXTRACTED_R1 = PLOTS_DIR / "extracted_v2_r1"',
    'EXTRACTED_R1 = PLOTS_DIR / "data_cache/extracted_v2_r1"'
)
config_content = config_content.replace(
    'EXTRACTED_FULL = PLOTS_DIR / "extracted_v2"',
    'EXTRACTED_FULL = PLOTS_DIR / "data_cache/extracted_v2"'
)
config_content = config_content.replace(
    'OUT_DIR = PLOTS_DIR / "2026.5.15.19.09"',
    'OUT_DIR = PLOTS_DIR / "figures"'
)
(dst_dir / "rq2_analysis_config.py").write_text(config_content, encoding="utf-8")
print("  rq2_analysis_config.py copied and patched.")

# 2. extract_rq2_data.py
extract_content = (src_dir / "extract_rq2_data.py").read_text(encoding="utf-8")
extract_content = extract_content.replace(
    'OUTPUTS_ROOT = "/mnt/data4/yunyang/ADVTEST_DATA/outputs"',
    'OUTPUTS_ROOT = "E:/Project/ADVTEST/1号机代码/DATA_new/outputs"'
)
extract_content = extract_content.replace(
    'DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "extracted")',
    'DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "data_cache", "extracted_v2_r1")'
)
(dst_dir / "extract_rq2_data.py").write_text(extract_content, encoding="utf-8")
print("  extract_rq2_data.py copied and patched.")

# 3. rq2_phase1_collect.py
collect_content = (src_dir / "rq2_phase1_collect.py").read_text(encoding="utf-8")
(dst_dir / "rq2_phase1_collect.py").write_text(collect_content, encoding="utf-8")
print("  rq2_phase1_collect.py copied.")

# 4. rq2_phase2_fixed.py
phase2_content = (src_dir / "rq2_phase2_fixed.py").read_text(encoding="utf-8")
phase2_content = phase2_content.replace(
    '"> Scope: 5767 valid frames, S/M/L/All groups",',
    '"> Scope: 6011 frames (5768 valid frames, 243 trivial frames), S/M/L/All groups",\n          "> Included: scene-0105_frame33 (with 83160 L2 gaps, 100% covered), 0/0 small frames (treated as init_rate=1.0)",'
)
(dst_dir / "rq2_phase2_fixed.py").write_text(phase2_content, encoding="utf-8")
print("  rq2_phase2_fixed.py copied and patched.")

print("All files copied and patched successfully!")
