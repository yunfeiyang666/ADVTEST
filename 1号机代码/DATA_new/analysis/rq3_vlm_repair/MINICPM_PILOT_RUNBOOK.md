# MiniCPM-o 2.6 微调试跑手册

这轮只验证微调链路，不使用 RQ1 冻结测试题。训练数据固定为六类各 50 道，共 300 道；开放版用于训练，选择版保留作后续消融。

## 1. 构建训练题

```powershell
$root = 'E:\Project\ADVTEST'
$rq3 = "$root\1号机代码\DATA_new\analysis\rq3_vlm_repair"
$deps = "$root\scratch\rq3_vlm_repair\python_deps"
$env:PYTHONPATH = $deps

python "$rq3\prepare_data.py" build --kind minicpm-pilot `
  --output-dir "$root\scratch\rq3_vlm_repair\data\source_minicpm_pilot_300_v1" `
  --frame-pool-size 600 --per-frame-candidate-limit 300
```

固定随机种子为 `20260716`。程序只读取训练场景，得到 L0、L1、converge、direction_chain、distance_chain、viewpoint_transfer 各 50 道。

## 2. 导出和验证

```powershell
$source = "$root\scratch\rq3_vlm_repair\data\source_minicpm_pilot_300_v1\sources\advtest_minicpm_pilot_300_source.jsonl"
$sft = "$root\scratch\rq3_vlm_repair\data\sft_minicpm_pilot_300_v1"

python "$rq3\prepare_data.py" export `
  --source "advtest_minicpm_pilot_300=$source" `
  --output-dir $sft --seed 20260716

python "$rq3\prepare_data.py" validate `
  --dataset "$sft\datasets\advtest_minicpm_pilot_300_open.json" `
  --paired-dataset "$sft\datasets\advtest_minicpm_pilot_300_choice.json" `
  --image-root $sft --expected-count 300 --minicpm-pilot `
  --output-manifest "$sft\validation_manifest.json"
```

正式开始训练前必须确认验证结果为：300 个唯一题号、六类各 50、`test_scene_leakage=0`、`validation_errors={}`。

## 3. 训练环境

本机隔离环境位于：

```text
E:\Project\ADVTEST\scratch\rq3_vlm_repair\venv_minicpm
```

LLaMA-Factory 固定为 `v0.9.2`（commit `e2299e261be852304bb1d370515078193ab12bd8`）。该版本官方支持 MiniCPM-o 2.6。环境使用 CUDA PyTorch `2.1.2+cu121`、Transformers `4.45.2`、PEFT `0.12.0`、Accelerate `1.2.1`、bitsandbytes `0.43.3`。

## 4. 32 题 smoke

```powershell
$train = "$rq3\run_minicpm_training.py"
python $train prepare
python $train preflight
python $train launch
python $train verify
```

`preflight` 会读取 `model.safetensors.index.json` 并检查四个权重分片全部存在。缺少任何分片都会立即退出，不允许使用空模型、MOCK 或静默降级。

模型完整权重目录固定为 `E:\hf_cache\huggingface\openbmb\MiniCPM-o-2_6`。旧的 ModelScope 目录只有配置文件，不作为训练输入。

smoke 固定参数：32 道题、4-bit QLoRA、LoRA `r=8/alpha=16/dropout=0.05`、视觉编码器和多模态投影层冻结、batch 1、梯度累积 8、20 step、学习率 `1e-4`、最大长度 512。

验收文件：

- `run_manifest.json`：输入数据、模型和环境记录。
- `train_smoke.log`：完整训练日志。
- `adapter/adapter_model.safetensors`：LoRA 权重。
- `adapter_verification.json`：adapter 哈希和逐步 loss。

本机只有 8GB 显存。如果模型在 4-bit 加载阶段仍 OOM，记录为本机硬件限制，服务器保持同一数据、LoRA 参数和随机种子运行，不能针对某一实验组单独降低配置。
