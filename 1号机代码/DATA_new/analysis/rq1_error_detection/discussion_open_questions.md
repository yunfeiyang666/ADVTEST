# RQ1 实验设计 — 待和老师讨论的问题清单

> 背景:真实 VLM 评测链路(mPLUG-Owl2)已跑通,四方法 limit=20 smoke 已出表。
> 现在要定的是实验组设计,核心矛盾是"对照组不该完全继承我们的生成流程"。

---

## 一、已确认的事实(用数据说话)

### 1. 官方 NuScenes-QA(val)的规模和答案空间

- 文件:`1号机代码/DATA_new/data/NuScenes_val_questions.json`(24.3 MB)
- 总题数:**83,337**,覆盖 **6,011** 个 key-frame(sample_token)
- 平均每帧 13.9 题,最多 32 题
- 答案空间只有 **30 种**:yes/no 占 ~45%,类别词(car/pedestrian/truck...)、
  数字 0-10、状态(moving/parked/stopped)
- 题型:exist 30% / object 21% / count 20% / comparison 15% / status 14%
- 全是 0-hop 或 1-hop(简单空间关系)

### 2. 我们的题(object-instance 级)

- 每方法 1000 题,覆盖 11 帧
- 答案空间 **62~74 种**,且是 **实例级**:car5、bicycle2、car4、ego...
- 题型:converge / viewpoint_transfer / distance_chain / direction_chain 等
  多跳关系链

### 3. 核心结论:两套题"标答粒度"差一个量级

| 维度 | 官方 NuScenes-QA | 我们的题 |
|---|---|---|
| 答案粒度 | 类别级(car/yes/3) | 实例级(car5) |
| 答案空间 | 30 | 62~74 |
| 关系复杂度 | 0~1 hop | 多跳链 |
| 判定 | 类别匹配即对 | 必须命中实例 ID |

→ **同一个 VLM,在官方题上 fail rate 天然低、在我们题上天然高。直接比 fail
rate 不公平**,审稿人必然质疑。

---

## 二、当前实验组的方法论硬伤

`rq1_selectors.py` 里四个方法**共享同一个候选池**,只在"怎么选/改"上不同:

- advtest:按我们的贪心覆盖序取
- random:候选池内随机
- qatest:候选池内按 family 均匀采 + 文本变异
- qaasker:候选池内随机起点 + footprint 链

问题:baseline 寄生在我们的产物上,天花板被我们锁死 → 等于"在我们设计的
赛道上比我们排序最优",循环论证。

---

## 三、需要老师拍板的决策点

### 决策 1:GT 标答口径怎么统一(最关键)

两套题 GT 粒度不同,直接比 fail rate 不行。三条路线:

- **路线 A**:都降到类别级判定。安全,但放弃我们 instance 级的优势(自废武功)。
- **路线 B**:不比 fail rate,改比"找 bug 的效率"——相同 budget 下暴露多少
  独立可验证 failure / 覆盖多少失败类型。最符合 software testing 论文叙事。**(我倾向这条)**
- **路线 C**:双轨报告——官方题集跑一遍(证明在标准 benchmark 有效)+ 我们的
  题集跑一遍(展示独有能力),分开报告不混比。最稳但工作量翻倍。

### 决策 2:baseline 用各自原始 pipeline 还是继续当 selector

- QATest 原本是"变异测试输入生成",QAAskeR 是"基于 QA 对的递归追问检错"。
- 建议:用官方 NuScenes-QA 当**中立 seed**,让两者跑各自原始逻辑独立产题,
  而不是从我们的候选池里挑。
- 待确认:这样改动量多大?是否需要跑通 QATest-main / QAAskeR 原始仓库?

### 决策 3:Random 归类

- 我们的判断:"从 gap 完全随机生成"在小预算下显示不出优势 →
  **Random 应归到"消融组"(证明我们的排序 > 随机),不当外部 baseline**。
- 待确认:老师是否认可把 Random 从 baseline 移到 ablation。

### 决策 4:budget 口径 = 问题数 还是 VLM 调用次数

- QAAskeR 的检错靠"主问 + 衍生问 + 看两次答案是否矛盾",天然吃 2 次 VLM 调用。
- 按问题数算对 QAAskeR 有利/不利需厘清;按调用次数算更公平。
- 待确认:先读 QAAskeR 论文确认 follow-up 机制,再定口径。

### 决策 5:难度可比性(受控变量)

- 若各方法完全独立生成,问的对象/难度不可比,fail rate 差异可能只是
  "题难度不同"而非"方法好坏"。
- 可能需要受控:固定"同一批 frame、同类对象关系",但生成策略各自独立。

---

## 四、建议的两层实验结构(讨论用草案)

- **第一层 内部消融**:Ours-Complete vs Ours-Random vs 去组件变体。
  可共享候选池,诚实标注 ablation。回答"我们的选择策略有用"。
- **第二层 跨方法对比**:ADVTEST / QATest / QAAskeR(/官方题)各自独立生成,
  共享 = 同一批 frame + 同一 VLM + 同一 budget + 同一评测协议。
  回答"ADVTEST 作为 testing 方法更能暴露 VLM 失败"。

---

## 五、待解决的工程对齐问题(不依赖上面决策)

1. `scene_frame ↔ sample_token` 映射:官方 QA 按 sample 组织,我们按 frame
   组织,要跑同一批帧需建映射(evaluator 已有 `get_sample_token()`,不难)。
2. `--limit` 单帧问题:suite 按帧分块存储,小 limit 只命中第一帧,需改成
   按帧采样(per-frame-limit),让跨帧 smoke 能跑。
3. raw result 字段补全:prompt / 耗时 / mode / 原始输出,便于 failure 分析。
4. 根目录临时文件清理 + 提交当前真实 VLM 进展。

