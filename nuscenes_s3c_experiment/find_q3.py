import json
data = json.load(open('output/coverage_analysis/failed_samples_detailed_batch1.json'))
for s in data['failed_samples']:
    q = s['question'].lower()
    if 'pedestrian' in q and 'truck' in q:
        print(f"Q: {s['question']}")
        print(f"Expected: {s['expected_answer']}")
        print(f"Pipeline: {s['pipeline_answer']}")
        print()
