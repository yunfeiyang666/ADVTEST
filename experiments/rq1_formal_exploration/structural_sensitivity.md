# RQ1 Structural Sensitivity

## Frame-Cap Decision

- Recommended cap: 50
- Micro-L2 delta (100 - 50): -0.001071
- AUC delta (100 - 50): -0.000543
- Rule: cap100 gains are negligible

## External Generation Capacity

| Method | Requested | Actual | Run |
|---|---:|---:|---|
| official_qa | 1000 | 1000 | official-capacity1000 |
| qatest | 1000 | 1000 | official-capacity1000 |

## Random Stability

| Cap | Seeds | Micro-L2 Mean | Std | Min | Max |
|---:|---:|---:|---:|---:|---:|
| 50 | 3 | 0.002759 | 0.000030 | 0.002737 | 0.002801 |
| 100 | 3 | 0.002503 | 0.000006 | 0.002497 | 0.002510 |
