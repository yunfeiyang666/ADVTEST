import json, os

d = json.load(open(r'e:\Project\ADVTEST\DATA_new\official_pipeline\plans\plan_B_remote1.json', encoding='utf-8'))
frames = d.get('frames', d.get('selected_frames', []))
plan_b_dirs = set()
for f in frames:
    key = f"{f['scene_id']}_frame{f['frame_id']}"
    plan_b_dirs.add(key)

out_dir = r'e:\Project\ADVTEST\DATA_new\outputs'
existing = [d for d in os.listdir(out_dir) if os.path.isdir(os.path.join(out_dir, d)) and d in plan_b_dirs]
print(f'Plan B frames needing cleanup: {len(existing)}')
if existing:
    for d in sorted(existing)[:10]:
        print(f'  {d}')
    if len(existing) > 10:
        print(f'  ... and {len(existing)-10} more')
else:
    print('  (none found)')
