import json, csv

# 1. generated.jsonl: show first record's keys
with open(r'E:\Project\ADVTEST\1号机代码\DATA_new\outputs\scene-0003_frame1\generation\qa\scene-0003_frame1_generated.jsonl', encoding='utf-8') as f:
    rec = json.loads(f.readline())
print('=== generated.jsonl fields ===')
for k in sorted(rec.keys()):
    v = rec[k]
    vtype = type(v).__name__
    if isinstance(v, (dict, list)):
        vstr = f'{vtype}({len(v)} items)'
    else:
        vstr = str(v)[:80]
    print(f'  {k}: {vstr}')

# 2. incremental_coverage.csv: show columns + first 3 rows
print('\n=== incremental_coverage.csv columns ===')
with open(r'E:\Project\ADVTEST\1号机代码\DATA_new\outputs\scene-0003_frame1\reports\scene-0003_frame1_incremental_coverage.csv', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    print('  Columns:', list(reader.fieldnames))
    for i, row in enumerate(reader):
        if i < 3:
            print(f'  row{i+1}: order={row["order_index"]} phase={row["selection_phase"]} family={row["l2_family"]} delta_l2={row["delta_l2"]} cum_l2={row["cum_l2"]} rate={row["coverage_rate_l2"]}')
        else:
            break

# 3. summary.json: show key stats
print('\n=== summary.json key stats ===')
with open(r'E:\Project\ADVTEST\1号机代码\DATA_new\outputs\scene-0003_frame1\reports\scene-0003_frame1_summary.json', encoding='utf-8') as f:
    s = json.load(f)
print(f'  generated: {s.get("generated_count")}')
print(f'  pool_size: {s.get("total_gap_count")}')
print(f'  coverage: {s.get("coverage")}')
print(f'  families: {s.get("families")}')
timing = s.get("pipeline_timing", {})
print(f'  timing: precompute={timing.get("precompute_ms")}ms plan_cache={timing.get("plan_cache_ms")}ms')
