# RQ1 正式探究记录

## 目标

在固定的 100 帧顺序和每方法 1000 题生成预算下，比较每帧上限
`50/100` 对结构覆盖的影响，并检查 Random 的多种子稳定性以及 Official
NuScenes-QA/QATest 的实际题目容量。

本阶段不调用真实 VLM。

## 代码版本

- 实验记录器：`69f16ca`
- 敏感性汇总器：`a127e84`
- 记录器工作目录修复：`7f4d69f`
- 分支：`codex/rq1-experiment-boundaries`

所有成功运行都基于 `7f4d69f`。输入帧缓存 SHA-256 均为：

```text
6a76177b6d3bbb9c52159933680527caf03862dd78b3f237176dda54e0a0c797
```

## 实验矩阵

| 条件 | 种子 | 生成预算 | 帧池 | 状态 |
|---|---|---:|---:|---|
| cap 50 | 42, 43, 44 | 1000 | 100 | 完成 |
| cap 100 | 42, 43, 44 | 1000 | 100 | 完成 |
| Official QA/QATest 容量 | 42 | 1000 | 100 | 完成 |

结构运行使用 `--question-load-limit 200`，每帧最多加载 200 个候选。
确定性方法只使用 seed 42 进入最终表；Random 保留三个种子。

## 操作命令

工作目录：

```powershell
cd E:\Project\ADVTEST\1号机代码\DATA_new\analysis\rq1_error_detection
```

结构运行模板：

```powershell
python run_recorded_experiment.py `
  --run-id structural-cap50-seed42-retry1 `
  --purpose "100-frame structural sensitivity cap=50 seed=42" `
  --run-root E:\Project\ADVTEST\scratch\rq1_formal_exploration\runs `
  --input-file E:\Project\ADVTEST\1号机代码\DATA_new\analysis\data_cache\rq1_100_eval_frames.json `
  --parameter generation_budget=1000 `
  --parameter max_questions=50 `
  --parameter seed=42 `
  --parameter frame_pool_size=100 `
  -- python fixed_budget_experiment.py `
    --generation-budget 1000 `
    --frame-pool-size 100 `
    --max-questions 50 `
    --question-load-limit 200 `
    --seed 42 `
    --output-dir E:\Project\ADVTEST\scratch\rq1_formal_exploration\runs\structural-cap50-seed42-retry1\results
```

其余结构运行只替换 run ID、`max_questions` 和 seed。

外部容量运行：

```powershell
python run_recorded_experiment.py `
  --run-id official-capacity1000 `
  --purpose "100-frame Official QA and QATest generation capacity" `
  --run-root E:\Project\ADVTEST\scratch\rq1_formal_exploration\runs `
  --input-file E:\Project\ADVTEST\1号机代码\DATA_new\analysis\data_cache\rq1_100_eval_frames.json `
  --parameter generation_budget=1000 `
  --parameter seed=42 `
  --parameter frame_pool_size=100 `
  -- python official_qa_experiment.py `
    --methods official_qa qatest `
    --generation-budget 1000 `
    --frame-pool-size 100 `
    --seed 42 `
    --output-dir E:\Project\ADVTEST\scratch\rq1_formal_exploration\runs\official-capacity1000\results
```

汇总命令：

```powershell
python structural_sensitivity.py `
  --structural-run-dir <六个成功结构运行目录，各参数重复一次> `
  --external-run-dir E:\Project\ADVTEST\scratch\rq1_formal_exploration\runs\official-capacity1000 `
  --output-dir E:\Project\ADVTEST\experiments\rq1_formal_exploration
```

## 结果

ADVTEST：

| 每帧上限 | 访问帧数 | Micro-L2 | L2/Q | AUC Micro-L2 |
|---:|---:|---:|---:|---:|
| 50 | 20 | 0.004383 | 4.508 | 0.002064 |
| 100 | 11 | 0.003311 | 3.406 | 0.001521 |

从 cap 50 切换到 cap 100：

- Micro-L2 变化：`-0.001071`
- AUC Micro-L2 变化：`-0.000543`
- 推荐：`cap=50`

相同 1000 题下，cap 50 让问题分布到更多帧，并覆盖更多唯一 L2 项。该结果
支持把每帧 50 题作为后续正式生成实验的默认上限。

Random 稳定性：

| 每帧上限 | 种子数 | Micro-L2 均值 | 标准差 | 最小 | 最大 |
|---:|---:|---:|---:|---:|---:|
| 50 | 3 | 0.002759 | 0.000030 | 0.002737 | 0.002801 |
| 100 | 3 | 0.002503 | 0.000006 | 0.002497 | 0.002510 |

外部题目容量：

| 方法 | 请求题数 | 实际唯一题数 |
|---|---:|---:|
| Official QA | 1000 | 1000 |
| QATest | 1000 | 1000 |

与 11 帧试验中的 Official QA `164/1000` 不同，100 帧上 Official QA 已能提供
至少 1000 道唯一题。因此正式实验中不需要循环重复 Official QA。

## 失败与修复记录

第一次 cap 50 运行使用以下 ID：

```text
structural-cap50-seed42
structural-cap50-seed43
structural-cap50-seed44
```

三条运行均以退出码 2 在约 0.1 秒内失败。记录器错误地把子命令工作目录固定到
仓库根目录，导致相对路径 `fixed_budget_experiment.py` 无法找到。

修复过程：

1. 保留三个失败 run 目录及其 manifest、stdout、stderr。
2. 新增失败测试，证明 CLI 默认目录与调用者目录不一致。
3. 将默认 `cwd` 改为 `Path.cwd()`。
4. 运行 5 个记录器测试并通过。
5. 提交修复 `7f4d69f`。
6. 使用 `-retry1` 新 run ID 重试，未覆盖失败证据。

## 文件位置

- 跟踪摘要：`experiments/rq1_formal_exploration/structural_sensitivity.json`
- 阅读版摘要：`experiments/rq1_formal_exploration/structural_sensitivity.md`
- 运行索引：`experiments/rq1_formal_exploration/run_index.json`
- 原始运行目录：`scratch/rq1_formal_exploration/runs/`
