# RQ3 执行手册

本文档按实际执行顺序编写。所有生成物写入
`E:\Project\ADVTEST\scratch\rq3_vlm_repair`，禁止提交模型权重、拼接图、
raw checkpoint 和逐题输出。

## 0. 固定变量

Windows PowerShell：

```powershell
$root = 'E:\Project\ADVTEST'
$py = "$root\.venv310\Scripts\python.exe"
$rq3 = "$root\1号机代码\DATA_new\analysis\rq3_vlm_repair"
$eval = "$root\1号机代码\DATA_new\analysis\rq1_error_detection\run_suite_evaluation.py"
$model = 'E:\hf_cache\modelscope\iic\mPLUG-Owl2'
```

服务器将 `$py`、`$root`、`$model` 换成服务器实际路径，其他参数不变。
正式训练要求 Linux GPU 显存至少 24GB。

当前 checkpoint 缺少 visual abstractor 的 12 个位置参数。训练和评测入口均先用
固定种子 `20260715` 初始化这些缺失参数，再恢复训练种子 `42/43/44`。不要删除
`--rq3_base_init_seed`，否则不同实验可能从不同的临时基模参数开始。

## 1. 冻结场景划分

```powershell
& $py "$rq3\prepare_data.py" split
```

检查
`scratch\rq3_vlm_repair\data\splits\split_manifest.json`：训练
`128/4961`、验证 `14/542`、测试 `8/264`、正式测试帧 `308`，并且
`scene_overlap_count=0`。

## 2. 构建三套主训练集

```powershell
& $py "$rq3\prepare_data.py" build --kind main `
  --output-dir "$root\scratch\rq3_vlm_repair\data\source_main_v1"
```

必须得到 `advtest_10k`、`random_10k`、`official_qa_10k` 各 10000 题。
ADVTEST 和 Random 的逐帧、逐题型题数必须一致；脚本发现不一致会直接退出。

导出共用拼接图、开放训练版、选择训练版和评测 suite：

```powershell
$src = "$root\scratch\rq3_vlm_repair\data\source_main_v1\sources"
$sft = "$root\scratch\rq3_vlm_repair\data\sft_main_v1"
& $py "$rq3\prepare_data.py" export `
  --source "advtest_10k=$src\advtest_10k_source.jsonl" `
  --source "random_10k=$src\random_10k_source.jsonl" `
  --source "official_qa_10k=$src\official_qa_10k_source.jsonl" `
  --output-dir $sft
```

逐组验证：

```powershell
& $py "$rq3\prepare_data.py" validate `
  --dataset "$sft\datasets\advtest_10k_open.json" `
  --paired-dataset "$sft\datasets\advtest_10k_choice.json" `
  --image-root $sft --expected-count 10000 --structural `
  --output-manifest "$sft\advtest_validation.json"

& $py "$rq3\prepare_data.py" validate `
  --dataset "$sft\datasets\random_10k_open.json" `
  --paired-dataset "$sft\datasets\random_10k_choice.json" `
  --image-root $sft --expected-count 10000 --structural `
  --output-manifest "$sft\random_validation.json"

& $py "$rq3\prepare_data.py" validate `
  --dataset "$sft\datasets\official_qa_10k_open.json" `
  --paired-dataset "$sft\datasets\official_qa_10k_choice.json" `
  --image-root $sft --expected-count 10000 `
  --output-manifest "$sft\official_validation.json"
```

## 3. 构建固定验证集

验证集为六类结构题各 100 题，加 400 道官方题：

```powershell
$valSrc = "$root\scratch\rq3_vlm_repair\data\validation_source_v1"
$valSft = "$root\scratch\rq3_vlm_repair\data\validation_sft_v1"
& $py "$rq3\prepare_data.py" build --kind validation --output-dir $valSrc
& $py "$rq3\prepare_data.py" export `
  --source "validation_1000=$valSrc\sources\validation_1000_source.jsonl" `
  --output-dir $valSft
& $py "$rq3\prepare_data.py" validate `
  --dataset "$valSft\datasets\validation_1000_open.json" `
  --paired-dataset "$valSft\datasets\validation_1000_choice.json" `
  --image-root $valSft --expected-count 1000 --validation `
  --output-manifest "$valSft\validation_manifest.json"
```

## 4. 构建 ADVTEST-hard

先生成固定的约 32000 道候选：

```powershell
$hardSrc = "$root\scratch\rq3_vlm_repair\data\hard_candidates_v1"
$hardSft = "$root\scratch\rq3_vlm_repair\data\hard_candidates_sft_v1"
& $py "$rq3\prepare_data.py" build --kind hard-candidates --output-dir $hardSrc
& $py "$rq3\prepare_data.py" export `
  --source "advtest_hard_candidates=$hardSrc\sources\advtest_hard_candidates_source.jsonl" `
  --output-dir $hardSft
& $py "$rq3\prepare_data.py" validate `
  --dataset "$hardSft\datasets\advtest_hard_candidates_open.json" `
  --paired-dataset "$hardSft\datasets\advtest_hard_candidates_choice.json" `
  --image-root $hardSft --expected-count 32000 --hard-candidates `
  --output-manifest "$hardSft\validation_manifest.json"
```

只用冻结基模评测候选选择题：

```powershell
$hardEval = "$root\scratch\rq3_vlm_repair\hard_screen\batch0_eval"
& $py $eval --mode MPLUG `
  --suite-dir "$hardSft\eval_suites" `
  --methods advtest_hard_candidates_choice `
  --model-path $model --output-dir $hardEval --resume
```

任务中断后原命令重跑即可。`--resume` 会验证已有逐题结果是当前 suite 的严格
前缀；题目、场景或 source ID 任一不一致都会立即退出，禁止错位续跑。

从同一次真实调用的错题中筛 10000 题。训练 GT 始终取源问题 GT，不取模型预测：

```powershell
& $py "$rq3\prepare_data.py" screen-hard `
  --source-suite "$hardSrc\sources\advtest_hard_candidates_source.jsonl" `
  --raw-results "$hardEval\advtest_hard_candidates_choice_suite_raw_results.jsonl" `
  --output-suite "$root\scratch\rq3_vlm_repair\data\advtest_hard_10k_source.jsonl" `
  --output-manifest "$root\scratch\rq3_vlm_repair\data\advtest_hard_10k_manifest.json"
```

若某类不足，建立一个 JSON，例如只补 `viewpoint_transfer` 2000 题：

```json
{"viewpoint_transfer": 2000}
```

然后使用新 seed 和新目录执行 `build --kind hard-candidates --quotas-json ...`，
评测新 batch。再次 `screen-hard` 时重复传入多组 `--source-suite` 和
`--raw-results`。脚本会跨 batch 去重，不能复制题目补足。

## 5. 本机 8GB smoke

本机 smoke 固定为 4-bit、LoRA r=8、batch 1、梯度累积 8、visual
abstractor 关闭、32 条唯一问题、20 step：

```powershell
$smoke = "$root\scratch\rq3_vlm_repair\training\smoke_advtest_r8_s42"
& $py "$rq3\run_training.py" prepare --profile smoke `
  --dataset "$sft\datasets\advtest_10k_open.json" `
  --image-root $sft --model $model --seed 42 --run-dir $smoke `
  --python-executable $py
& $py "$rq3\run_training.py" execute --config "$smoke\run_config.json"
```

验收 `training_result.json`：返回码 0、loss 全部有限且末值低于首值、
LoRA adapter 存在、重新加载后生成答案非空。训练启动日志必须显示
`vision_model=0`、`forbidden_base=0`，且只列出 LoRA；正式配置还应列出
visual abstractor。

## 6. 生成正式训练矩阵

hard 集完成后先导出其开放/选择版本，再生成 9 个主实验和 2 个消融配置：

```powershell
$matrix = "$root\scratch\rq3_vlm_repair\training\formal_matrix_v1"
& $py "$rq3\run_training.py" matrix `
  --dataset "advtest_10k=$sft\datasets\advtest_10k_open.json" `
  --dataset "random_10k=$sft\datasets\random_10k_open.json" `
  --dataset "official_qa_10k=$sft\datasets\official_qa_10k_open.json" `
  --hard-dataset '<advtest_hard_10k_open.json>' `
  --hard-image-root '<hard-sft-export-dir>' `
  --choice-dataset "$sft\datasets\advtest_10k_choice.json" `
  --image-root $sft --model $model --output-dir $matrix `
  --python-executable $py
```

若 checkpoint 都未通过官方题保持条件，使用新的输出目录，并在同一条矩阵命令
末尾增加 `--learning-rate 5e-5`，整套矩阵统一重建、重跑。若 pilot OOM，整套
矩阵统一增加 `--disable-visual-abstractor`；仍 OOM 时统一设置
`--lora-r 8 --lora-alpha 16`。这些参数会逐组写入 manifest，禁止手工只改某组。

先执行三个 seed=42 pilot，检查 OOM、NaN、解冻边界和 checkpoint 文件；
正常后再执行剩余主实验和消融。任一主组 OOM 时必须统一修改三组配置并
全部重跑，禁止只给某组降低 LoRA r 或关闭 visual abstractor。

Linux 服务器执行顺序：

```bash
bash <matrix-dir>/execute_pilots.sh
# 三个 pilot 都通过后再执行：
bash <matrix-dir>/execute_after_pilots.sh
```

不要直接先跑 `execute_matrix.sh`；否则 pilot 失败时仍会继续浪费其余训练资源。

## 7. 验证与 checkpoint 选择

基模和每个 epoch checkpoint 都评测同一
`validation_1000_choice_suite.jsonl`。adapter 调用必须同时传 base：

```powershell
& $py $eval --mode MPLUG --suite-dir "$valSft\eval_suites" `
  --methods validation_1000_choice --model-path '<adapter-or-checkpoint-dir>' `
  --model-base $model --output-dir '<validation-output-dir>'
```

选择 checkpoint：

```powershell
& $py "$rq3\analyze_results.py" select-checkpoint `
  --base '<base-validation-raw.jsonl>' `
  --candidate 'epoch1=<epoch1-raw.jsonl>' `
  --candidate 'epoch2=<epoch2-raw.jsonl>' `
  --candidate 'epoch3=<epoch3-raw.jsonl>' `
  --output '<checkpoint-selection.json>'
```

没有 checkpoint 满足官方题下降不超过 2 个百分点时，将统一学习率改为
`5e-5` 后重跑该实验矩阵。

## 8. 正式测试与统计

选择题主结果只使用 L0、L1、converge、direction_chain、distance_chain、
viewpoint_transfer，明确排除 mixed。开放问答为次要结果，官方 3503 题为
保持能力。基模与模型输出必须是同一批逐题 ID。

先把同一模型的六类逐题结果和官方题结果合并；可传任意多个 `--input`，
程序会检查重复 ID 并自动排除 mixed：

```powershell
& $py "$rq3\analyze_results.py" merge-predictions `
  --input '<l0-raw.jsonl>' --input '<l1-raw.jsonl>' `
  --input '<converge-raw.jsonl>' --input '<direction-chain-raw.jsonl>' `
  --input '<distance-chain-raw.jsonl>' --input '<viewpoint-raw.jsonl>' `
  --input '<official-3503-raw.jsonl>' `
  --output '<merged-raw.jsonl>' --manifest '<merged-manifest.json>'
```

```powershell
& $py "$rq3\analyze_results.py" compare `
  --base '<base-raw.jsonl>' `
  --model 'advtest=<advtest-raw.jsonl>' `
  --model 'random=<random-raw.jsonl>' `
  --model 'official=<official-raw.jsonl>' `
  --output-dir '<report-dir>'
```

脚本输出 CSV、JSON、Markdown，使用同题配对 bootstrap 10000 次、精确
McNemar 检验和 Holm 校正。三随机种子汇总后执行：

```powershell
& $py "$rq3\analyze_results.py" aggregate-seeds --base '<base.jsonl>' `
  --run 'advtest_10k:42=<path>' --run 'advtest_10k:43=<path>' `
  --run 'advtest_10k:44=<path>' `
  --run 'random_10k:42=<path>' --run 'random_10k:43=<path>' `
  --run 'random_10k:44=<path>' `
  --run 'official_qa_10k:42=<path>' --run 'official_qa_10k:43=<path>' `
  --run 'official_qa_10k:44=<path>' --output '<seed-aggregate.json>'
& $py "$rq3\analyze_results.py" judge-success `
  --aggregate '<seed-aggregate.json>' --output '<success-judgement.json>'
```

## 9. 人工复核表

只准备空白抽样表，不自动填写人工结论：

```powershell
& $py "$rq3\prepare_human_review.py" `
  --source '<formal-eval-suite.jsonl>' --count 100 `
  --output-csv '<human-review.csv>' `
  --output-manifest '<human-review-manifest.json>'
```

`human_valid`、`human_gt_correct`、`human_notes` 必须由人工填写。自动流程
生成的 manifest 固定写 `labels_completed=false`。

## 10. 每阶段提交

只提交代码、schema、文档和小型 manifest。不要提交
`scratch/rq3_vlm_repair`、模型权重、拼接图、raw checkpoint 或逐题预测。
每次提交前运行：

```powershell
& $py -m unittest discover -s $rq3 -p 'test_*.py' -v
git diff --check -- '1号机代码/DATA_new/analysis/rq3_vlm_repair' `
  '1号机代码/DATA_new/analysis/rq1_error_detection/evaluator.py' `
  '1号机代码/DATA_new/analysis/rq1_error_detection/run_suite_evaluation.py'
```
