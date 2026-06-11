# Fixed-Budget RQ1 Trial

- Shared frame pool: 30 frames
- Question budget: 1000 per method
- Per-frame range: 20-50

| Method | Suite | Frames | Micro L2 | Macro L2 | L2/Q | AUC Micro L2 |
|---|---:|---:|---:|---:|---:|---:|
| advtest | 1000 | 20 | 0.0052 | 0.0750 | 2.8090 | 0.0025 |
| random | 1000 | 20 | 0.0045 | 0.0627 | 2.4410 | 0.0021 |
| qatest | 1000 | 20 | 0.0045 | 0.0600 | 2.4230 | 0.0020 |
| qaasker | 1000 | 20 | 0.0023 | 0.0341 | 1.2650 | 0.0011 |

## Switch Reasons

- **advtest**: {"frame_cap": 19, "global_budget": 1}
- **random**: {"frame_cap": 19, "global_budget": 1}
- **qatest**: {"frame_cap": 19, "global_budget": 1}
- **qaasker**: {"frame_cap": 19, "global_budget": 1}
