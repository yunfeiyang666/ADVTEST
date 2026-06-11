# Fixed-Budget RQ1 Trial

- Shared frame pool: 30 frames
- Question budget: 1000 per method
- Per-frame range: 20-100

| Method | Suite | Frames | Micro L2 | Macro L2 | L2/Q | AUC Micro L2 |
|---|---:|---:|---:|---:|---:|---:|
| advtest | 1000 | 11 | 0.0048 | 0.0958 | 2.5900 | 0.0022 |
| random | 1000 | 11 | 0.0029 | 0.0867 | 1.5840 | 0.0014 |
| qatest | 1000 | 11 | 0.0027 | 0.0846 | 1.4320 | 0.0013 |
| qaasker | 1000 | 11 | 0.0014 | 0.0474 | 0.7770 | 0.0007 |

## Switch Reasons

- **advtest**: {"full_coverage": 2, "frame_cap": 8, "global_budget": 1}
- **random**: {"full_coverage": 2, "frame_cap": 8, "global_budget": 1}
- **qatest**: {"full_coverage": 2, "frame_cap": 8, "global_budget": 1}
- **qaasker**: {"candidate_exhausted": 2, "frame_cap": 8, "global_budget": 1}
