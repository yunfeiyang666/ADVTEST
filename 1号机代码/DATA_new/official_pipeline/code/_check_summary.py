import json, os
out = r'E:\Project\ADVTEST\1号机代码\DATA_new\outputs'
for d in ['scene-0003_frame0', 'scene-0101_frame23', 'scene-0268_frame11']:
    fp = os.path.join(out, d, 'reports', d + '_summary.json')
    if not os.path.exists(fp): continue
    s = json.load(open(fp, encoding='utf-8'))
    us = s.get('universe_stats', {})
    pt = s.get('pipeline_timing', {})
    pool = s["pool_size"]
    gen = s["generated"]
    cov = s["coverage"]
    fam = s["families"]
    ic = us.get("initial_coverage", "N/A")
    fs = us.get("formal_selected_count", "?")
    bf = us.get("coverage_backfill_count", "?")
    pre = pt.get("precompute_ms")
    pc = pt.get("plan_cache_ms")
    sg = pt.get("selection_gen_ms")
    print(f"=== {d} ===")
    print(f"  pool_size={pool} generated={gen} coverage={cov}")
    print(f"  families={fam}")
    print(f"  initial_coverage={ic}")
    print(f"  formal_selected={fs} backfill={bf}")
    print(f"  timing: precompute={pre}ms plan_cache={pc}ms sel_gen={sg}ms")
    print()
