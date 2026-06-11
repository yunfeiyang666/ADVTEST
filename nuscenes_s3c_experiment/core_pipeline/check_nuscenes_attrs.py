"""查询 NuScenes 官方定义的全部 attribute 和 category"""
import sys
sys.path.insert(0, r"E:\Project\ADVTEST\nuscenes_s3c_experiment")

from nuscenes.nuscenes import NuScenes

nusc = NuScenes(version='v1.0-mini', dataroot=r'E:\Project\ADVTEST\data\nuscenes', verbose=False)

print("=== ALL ATTRIBUTES ===")
for a in nusc.attribute:
    print(f"  {a['name']}")
print(f"Total: {len(nusc.attribute)}")

print("\n=== ALL CATEGORIES ===")
for c in nusc.category:
    print(f"  {c['name']}")
print(f"Total: {len(nusc.category)}")

# Check if any annotation has color or visual appearance info
print("\n=== SAMPLE ANNOTATION KEYS ===")
sample_ann = nusc.sample_annotation[0]
print(sorted(sample_ann.keys()))

print("\n=== SAMPLE ANNOTATION ===")
for k, v in sample_ann.items():
    if k != 'token' and k != 'prev' and k != 'next' and k != 'sample_token':
        print(f"  {k}: {v}")
