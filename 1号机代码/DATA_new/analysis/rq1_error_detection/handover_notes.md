# RQ1 主实验交接文档

> **交接时间**: 2026-06-12  
> **项目状态**: 真实 VLM 评测链路已跑通,待讨论实验组设计  
> **工作区**: `E:\Project\ADVTEST`  
> **关键环境**: `.venv310` (Python 3.10.11, torch 2.3.1+cu121, transformers 4.45.2)

---

## 一、当前进度总览

### 已完成(可复现)

#### 1. 真实 VLM 评测链路全通(mPLUG-Owl2)

- **环境修复完成**:
  - torch 2.3.1+cu121 可用,CUDA 正常
  - transformers 4.45.2,支持 Qwen2Config
  - 补齐依赖:torchaudio、soundfile、librosa
  - mPLUG-Owl2 模型加载成功(本地:`E:\hf_cache\modelscope\iic\mPLUG-Owl2`)
  - 自定义模块已补到 `E:\hf_cache\modules\transformers_modules\MiniCPM-o-2_6\`

- **pipeline 已打通**:
  ```text
  fixed-budget suite(JSONL)
    → scene_frame 解析
    → scene_graph 加载
    → sample_token 映射
    → 6 路 camera 图像读取
    → mosaic 拼图渲染(PIL,避开 cv2 中文路径 bug)
    → mPLUG-Owl2 真实推理
    → answer judge(exact/object-id match)
    → per-question raw result(JSONL)
    → suite_eval_report(markdown + CSV + JSON)
  ```

- **性能优化**:
  - nuScenes metadata 改用 mmap 快速查询,避免加载 1.35GB `sample_data.json`
  - mosaic lookup time 从 N/A 降至 0.03s
  - Path.resolve() 改为 Path.absolute(),避开 Windows 慢路径解析

#### 2. 四方法 smoke 已出真实表(limit=20)

运行命令:
```powershell
set PYTHONNOUSERSITE=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONHASHSEED=0
.\.venv310\Scripts\python.exe 1号机代码/DATA_new/analysis/rq1_error_detection/run_suite_evaluation.py ^
  --mode MPLUG ^
  --limit 20 ^
  --methods advtest random qatest qaasker ^
  --suite-dir 1号机代码/DATA_new/analysis/fixed_budget_results ^
  --output-dir 1号机代码/DATA_new/analysis/suite_eval_results/mplug_all_methods_limit20
```

**结果表**(mPLUG-Owl2,真实推理,每方法 20 题):

| Method | Q | Wrong | Fail Rate | Failed L2 | Failed L2/Q | Frames |
|---|---:|---:|---:|---:|---:|---:|
| advtest | 20 | 18 | 0.900 | 25 | 1.250 | 1 |
| qatest | 20 | 15 | 0.750 | 17 | 0.850 | 1 |
| random | 20 | 12 | 0.600 | 16 | 0.800 | 1 |
| qaasker | 20 | 11 | 0.550 | 13 | 0.650 | 1 |

**关键观察**:ADVTEST 在真实 VLM 上显著领先两个核心指标(Fail Rate 0.900 > 次高 0.750,Failed L2/Q 1.250 > 次高 0.850)。

**重要 caveat**:
- 只命中 1 帧(scene-0013_frame31),因为 suite 按帧分块、`--limit 20` 顺序截断
- mPLUG 模型有 partial newly-initialized 权重(visual abstractor pos embed)
- 样本量小,不能作为最终结论

输出目录:`1号机代码/DATA_new/analysis/suite_eval_results/mplug_all_methods_limit20/`

#### 3. 官方 NuScenes-QA vs 我们的题 — 对照分析完成

文档:`1号机代码/DATA_new/analysis/rq1_error_detection/nuscenes_qa_vs_ours.md`

**核心发现**:

官方 NuScenes-QA(val):
- 文件:`1号机代码/DATA_new/data/NuScenes_val_questions.json`(24.3 MB)
- 总题数:83,337,覆盖 6,011 个 key-frame
- 答案空间仅 30 种:yes/no 占 45%,其余是类别词(car/pedestrian...)、数字 0-10、状态(moving/parked)
- 题型:exist 30% / object 21% / count 20% / comparison 15% / status 14%
- 全是 0~1 hop 简单关系

我们的题(object-instance 级):
- 每方法 1000 题,覆盖 11 帧
- 答案空间 62~74 种,且是实例级:car5、bicycle2、car4、ego
- 题型:converge / viewpoint_transfer / distance_chain / direction_chain 等多跳关系链

**结论**:两套题标答粒度差一个量级(官方"答 car 就对",我们"必须答 car5"),同一 VLM 在两套题上的 fail rate 天然不在一个量纲,直接比不公平。

#### 4. GitHub 仓库推送成功

- 远端:`https://github.com/yunfeiyang666/ADVTEST.git`
- 最新 commit:`96da684 docs: add repository readme`
- 分支:`main`(干净版,已移除 2.48GB `DATA_new/outputs.tar`)
- 完整历史备份:`local-history-backup`

---

## 二、代码路径和关键文件

### 主要代码

```text
1号机代码/DATA_new/analysis/rq1_error_detection/
├── run_suite_evaluation.py           suite 评测主入口
├── evaluator.py                      VLM evaluator 实现(MPLUG/MINICPM/API/MOCK)
├── rq1_selectors.py                  四方法选题策略(当前有争议,见下文)
├── selectors_qatest.py               QATest 变异逻辑
├── selectors_qaasker.py              QAAskeR recursive asking 逻辑
├── run_minicpm_smoke.py              MiniCPM 最小 smoke 脚本(独立于 argparse)
├── analyze_nuscenes_qa.py            官方 QA 对照分析生成器
├── discussion_open_questions.md      待和老师讨论的问题清单
├── nuscenes_qa_vs_ours.md           官方 QA vs 我们题的对照分析
└── handover_notes.md                 本交接文档
```

### 数据路径

```text
E:\Project\ADVTEST\
├── 1号机代码/DATA_new/data/
│   ├── nuscenes/                     nuScenes v1.0 数据集(v1.0-trainval)
│   ├── NuScenes_val_questions.json   官方 NuScenes-QA val 题(24.3MB,8.3万题)
│   └── data_cache/                   sample_images mmap 缓存索引
├── 1号机代码/DATA_new/outputs/        scene graph 输出(scene-XXXX_frameYY/)
├── 1号机代码/DATA_new/analysis/
│   ├── fixed_budget_results/         四方法 suite JSONL(各 1000 题,11 帧)
│   └── suite_eval_results/           评测结果输出
│       ├── mplug_advtest_limit1/
│       ├── mplug_advtest_limit5/
│       └── mplug_all_methods_limit20/  ← 最新四方法真实 VLM 结果
└── E:\hf_cache/                      HuggingFace/ModelScope 模型缓存
    ├── modelscope/iic/mPLUG-Owl2/
    ├── modelscope/openbmb/MiniCPM-o-2_6/
    └── modules/transformers_modules/
```

### 环境

```text
.venv310/            Python 3.10.11 虚拟环境
  核心包:
    torch==2.3.1+cu121
    torchvision==0.18.1+cu121
    torchaudio==2.3.1
    transformers==4.45.2
    accelerate==0.34.2
    pillow
    soundfile
    librosa
```

启动方式:
```powershell
set PYTHONNOUSERSITE=1
set PYTHONDONTWRITEBYTECODE=1
.\.venv310\Scripts\python.exe <script>
```

---

## 三、已识别的问题和待办

### 问题 A:`--limit` 单帧问题(技术)

**现象**:suite 按帧分块存储(每帧连续 100 题),`--limit 20` 顺序截断导致只命中第一帧。

**根因**:
```python
for question in iter_jsonl(path):
    if limit and total >= limit:
        break  # 直接截断,不跨帧
```

**影响**:`Frames=1`,无法展示跨帧 failure detection 能力。

**修复方案**:加 `--per-frame-limit` 参数,每帧取前 N 题,或实现按帧分层采样。

**优先级**:中(不影响 pipeline 验证,但影响真实规模实验)

### 问题 B:对照组设计有方法论硬伤(最关键,需老师决策)

**现象**:当前四个方法(advtest/qatest/qaasker/random)都从**同一个候选池**选题。

**详细说明**:

`rq1_selectors.py` 的逻辑:
```python
def select_ours_complete(questions, B):
    return questions[:B]  # 取前 B 个(已按覆盖率贪心序排好)

def select_ours_random(questions, B):
    return rng.sample(questions, B)  # 候选池随机

def select_qatest(questions, B):
    select_and_mutate_qatest(questions, B)  # 按题型均匀采 + 文本变异

def select_recursive_asking(questions, B):
    # 随机起点 + 沿 footprint 链追加衍生问题
```

关键:`questions` 这个输入参数 = **我们 ADVTEST 已经生成好的全部候选问题**(从 scene graph 拓扑按我们的 L2 关系覆盖逻辑产出的实例级题库)。

**本质问题**:
- 出什么题(问哪些对象、什么关系、答案是什么)← 全部由我们 ADVTEST 决定
- QATest 做的 ← 在我们的题里挑 + 把措辞改乱(打错字、换同义词)
- Random 做的 ← 在我们的题里随机挑
- QAAskeR 做的 ← 在我们的题里按 footprint 链挑

**后果**:
1. baseline 天花板被我们锁死,永远问不出我们池子里没有的题
2. 这只能证明"我们的选题排序好",没法证明"我们的方法整体好"
3. 审稿人会质疑"在自己设计的赛道上自比"= 循环论证

**QATest 实际做了什么**(举例):
```text
原题(我们生成):"There is a car to the back left of car4; what is it?"
QATest 变异后:"There is a car to teh back left of car4; what is it??"
                ↑ 打错字             ↑ 多问号
```

它只改了措辞,没改内容、没改答案、没有生成新题——本质是"在我们的题上加噪声"。

**正确的做法应该是**:每个方法从原始数据(nuScenes 场景/官方 QA)出发,用各自逻辑独立产出 B 道题:
- ADVTEST:从 scene graph 按覆盖率主动构造实例级题(我们现在的逻辑)
- QATest:从官方 NuScenes-QA 出发,跑它原始变异生成,独立产出 B 道题
- Random:从场景独立随机构造,或归为消融组(证明我们的排序 > 随机)

这样共享的才是真正中立的东西:同一批帧、同一个被测 VLM、同一个 budget、同一套评测协议。

**待老师决策**:
1. 对照组要不要改成"各自独立生成"(工作量大,但方法论更站得住)
2. 还是承认"当前只比选题策略,不比生成能力",调整 claim 和论文叙事

### 问题 C:GT 标答粒度不统一(需老师决策)

**现象**:官方 NuScenes-QA 是类别级,我们是实例级,两者 fail rate 不可比。

**详细对比**(见 `nuscenes_qa_vs_ours.md`):

| 维度 | 官方 NuScenes-QA | 我们的题 |
|---|---|---|
| 答案粒度 | 类别级(car/yes/3) | 实例级(car5) |
| 答案空间 | 30 种 | 62~74 种 |
| 关系复杂度 | 0~1 hop | 多跳链 |
| 判定标准 | 类别匹配即对 | 必须命中实例 ID |

**示例对比**:
```text
官方题:前方那个东西是什么?
官方答案:car
判定:VLM 答"car"就算对

我们的题:car4 后左方是什么?
我们答案:car5
判定:VLM 必须答"car5",答"car"算错
```

**后果**:同一个 VLM 在官方题上 fail rate 天然低,在我们题上天然高。直接比 fail rate = 比题难度,不是比方法好坏。

**三条可选路线**(需老师拍板):

路线 A:**统一到类别级**。都用类别判定,放弃我们实例级的优势。安全但自废武功。

路线 B(推荐):**不比 fail rate,改比找 bug 的效率**。用跨方法可比的中立指标,比如:
- 相同 budget 下暴露多少独立可验证 failure
- 覆盖多少不同失败类型/场景区域
- 每消耗一次 VLM 调用平均发现多少 unique bug

这样比的是"测试方法找 bug 的能力",而不是"题难不难"。最符合 software testing 论文叙事。

路线 C:**双轨报告**。官方题集跑一遍(证明在标准 benchmark 有效)+ 我们题集跑一遍(展示独有能力),分开报告不混比。最稳但工作量翻倍。

**待老师决策**:选哪条路线,或提出第四条。

### 问题 D:QAAskeR 复杂度高,本轮可暂时排除(已商定)

**现状**:QAAskeR 需要多轮 VLM 调用(主问 + 衍生问 + 看两次答案是否矛盾),budget 口径复杂。

**决定**:本轮先把 QAAskeR 排除,budget 统一按"问题数"算,所有方法一题一调用。等主实验稳定后再考虑是否纳入。

---

## 四、运行手册(关键命令)

### 跑四方法 suite evaluation

```powershell
cd E:\Project\ADVTEST

# 激活环境变量
set PYTHONNOUSERSITE=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONHASHSEED=0

# 运行(mPLUG 模式)
.\.venv310\Scripts\python.exe 1号机代码/DATA_new/analysis/rq1_error_detection/run_suite_evaluation.py ^
  --mode MPLUG ^
  --limit 20 ^
  --methods advtest random qatest qaasker ^
  --suite-dir 1号机代码/DATA_new/analysis/fixed_budget_results ^
  --output-dir 1号机代码/DATA_new/analysis/suite_eval_results/mplug_limit20_run2
```

**参数说明**:
- `--mode`:MPLUG / MINICPM / API / MOCK
- `--limit`:每方法最多评测几题(0=不限)
- `--methods`:要评测的方法列表,空格分隔
- `--suite-dir`:suite JSONL 所在目录
- `--output-dir`:输出目录(自动创建)

**耗时参考**(mPLUG,单帧):
- limit=5:约 2 分钟
- limit=20:约 15 分钟(四方法)
- limit=100:预计 1.2 小时(四方法)

### 生成官方 QA 对照分析

```powershell
.\.venv310\Scripts\python.exe 1号机代码/DATA_new/analysis/rq1_error_detection/analyze_nuscenes_qa.py
```

输出:`1号机代码/DATA_new/analysis/rq1_error_detection/nuscenes_qa_vs_ours.md`

### MiniCPM smoke(独立最小脚本)

```powershell
.\.venv310\Scripts\python.exe 1号机代码/DATA_new/analysis/rq1_error_detection/run_minicpm_smoke.py
```

功能:预热 torch/transformers → 加载第一题 → 生成 mosaic → 构造 MiniCPMOEvaluator → 真实推理 → 输出 JSON。

**状态**:MiniCPM-o-2_6 权重未完整下载,当前会 fallback 到 MOCK。mPLUG 已验证可用,优先用 mPLUG。

---

## 五、已解决的坑(供参考)

### 坑 1:torch import 卡在 kernel32.LoadLibraryExW

**现象**:`.venv310` 里 `import torch` 偶发卡住或 KeyboardInterrupt。

**根因**:Windows DLL 加载 + user site 干扰 + 文件扫描。

**解法**:
```powershell
set PYTHONNOUSERSITE=1        # 禁用 user site
set PYTHONDONTWRITEBYTECODE=1 # 禁止 .pyc
set PYTHONHASHSEED=0
```

用 `cmd.exe /d /c` 或 `--isolated` pip 操作。偶发性仍存在,多试几次。

### 坑 2:中文路径 cv2.imread 失败

**现象**:路径带中文时 `cv2.imread` 返回 None。

**解法**:mosaic 渲染改用 PIL(Image.open 支持中文路径),不用 cv2。

**位置**:`evaluator.py` 的 `render_labeled_mosaic()`。

### 坑 3:nuScenes sample_data.json 1.35GB 加载慢

**现象**:每次查 camera 图像路径都要加载完整 metadata。

**解法**:改用 mmap 快速 seek 按 sample_token 查找。

**位置**:`evaluator.py` 的 `_get_camera_images()`。

**性能**:lookup 时间从 N/A 降至 0.03s。

### 坑 4:urllib3 import 偶发卡住

**现象**:urllib3 的 compression backend 导入在 Windows 上不稳定。

**解法**:改为 opt-in(环境变量 `ADVTEST_ENABLE_URLLIB3=1` 才导入),默认跳过。

**位置**:`evaluator.py` 头部。

### 坑 5:GitHub 拒绝 push(2.48GB outputs.tar)

**现象**:历史里有超大 tar,GitHub 单文件限 100MB。

**解法**:创建 orphan 分支 `github-main-clean`,不含大文件历史,force-with-lease 推送。完整历史保留在本地 `local-history-backup` 分支。

---

## 六、下一步建议 TODO

### 短期(不依赖决策,工程类)

1. **修 `--limit` 单帧问题**:实现按帧采样(`--per-frame-limit` 或 `--max-frames`)。
2. **补全 raw result 字段**:prompt、耗时、mode、原始输出、error message。
3. **清理根目录临时文件**:`progress_*.txt`、`log_tail.txt`、`suite_probe.txt` 等。
4. **提交当前进展**:
   ```bash
   git add 1号机代码/DATA_new/analysis/rq1_error_detection/
   git commit -m "feat(rq1): add handover notes and NuScenes-QA comparison analysis"
   git push
   ```
5. **建立 scene_frame ↔ sample_token 映射表**:方便后续把官方 QA 对齐到我们的 11 帧。

### 中期(待老师决策后)

**如果决定"各自独立生成"**:
1. 实现 QATest 独立生成 pipeline:从官方 NuScenes-QA 读 seed → 跑原始变异逻辑 → 产出 B 道题。
2. 实现 Random 独立生成:从 scene graph 随机构造实例级题,不经过我们的候选池。
3. 统一评测协议:同一批 frame、同一 VLM、同一 budget、同一 GT 口径(待定)。

**如果决定"路线 B(比找 bug 效率)"**:
1. 定义"独立可验证 failure"标准:什么算一个 unique bug、怎么去重。
2. 实现 failure 分类:按失败类型/对象类别/空间区域聚类。
3. 计算跨方法可比的效率指标:bugs_found / vlm_calls、coverage_of_failure_modes 等。
4. 改写实验结果表:不再主打 fail rate,改主打 bug detection efficiency。

**如果决定"路线 C(双轨)"**:
1. 在官方 NuScenes-QA 上跑 ADVTEST 的选择策略,产出"官方题 + 我们排序"的 suite。
2. 分别报告两套实验:
   - 官方题集(类别级):ADVTEST vs QATest vs Random
   - 我们题集(实例级):ADVTEST 独秀(或加消融组)
3. 论文里明确标注两套实验目的不同、不混比。

### 长期(主实验)

1. **扩大预算和帧覆盖**:从 limit=20(1 帧)扩到 limit=100~1000(11 帧)。
2. **跑完整四方法(或三方法)真实 VLM 评测**。
3. **分析 failure case**:
   - 哪些题 VLM 必错
   - 哪些错误类型是方法独有的
   - 哪些对象/关系特别容易触发 failure
4. **补充消融实验**:
   - Ours-Complete vs Ours-Random(证明排序有用)
   - 去掉约束、去掉 family 平衡等
5. **准备论文素材**:
   - failure case 可视化(mosaic + 错误答案)
   - 覆盖率曲线
   - 跨帧/跨方法对比表

---

## 七、联系方式和资源

### 文档

- 本交接文档:`1号机代码/DATA_new/analysis/rq1_error_detection/handover_notes.md`
- 待讨论问题清单:`discussion_open_questions.md`
- 官方 QA 对照分析:`nuscenes_qa_vs_ours.md`
- 真实 VLM 结果:`suite_eval_results/mplug_all_methods_limit20/suite_eval_report.md`

### 外部资源

- NuScenes 官方文档:`https://www.nuscenes.org/nuscenes`
- NuScenes-QA 论文/仓库:`https://github.com/qiantianwen/NuScenes-QA`
- mPLUG-Owl2:`https://github.com/X-PLUG/mPLUG-Owl`
- QATest 论文:`[待补充]`
- QAAskeR 论文:`imcsq-ASE21-QAAskeR-a71ef1f/` 本地有仓库

### 环境备份

如果 `.venv310` 损坏,重建命令:
```powershell
py -3.10 -m venv .venv_vlm_rebuild
.\.venv_vlm_rebuild\Scripts\python.exe -m pip install -U pip
.\.venv_vlm_rebuild\Scripts\python.exe -m pip install torch==2.3.1+cu121 torchvision==0.18.1+cu121 torchaudio==2.3.1 --index-url https://download.pytorch.org/whl/cu121
.\.venv_vlm_rebuild\Scripts\python.exe -m pip install transformers==4.45.2 accelerate==0.34.2 pillow soundfile librosa sentencepiece timm einops
```

---

## 八、关键决策历史记录

| 日期 | 决策 | 原因 | 影响 |
|---|---|---|---|
| 2026-06-11 | mosaic 改用 PIL 不用 cv2 | cv2 中文路径 bug | 支持中文路径 |
| 2026-06-11 | sample_data 改 mmap 查询 | 1.35GB 加载慢 | lookup 0.03s |
| 2026-06-12 | GitHub 用 orphan 分支 | 大文件历史超限 | 推送成功,旧历史本地保留 |
| 2026-06-12 | 本轮不纳入 QAAskeR | budget 口径复杂 | budget 按问题数,口径统一 |
| 待定 | GT 标答口径选择 | 粒度不统一 | 决定指标体系和论文叙事 |
| 待定 | 对照组是否独立生成 | 方法论硬伤 | 决定工作量和可信度 |

---

**交接完成。如有疑问,参考本文档和 `discussion_open_questions.md`,或直接查看代码注释。**

