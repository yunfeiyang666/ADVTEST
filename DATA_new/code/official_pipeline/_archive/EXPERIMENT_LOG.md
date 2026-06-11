# ADVTEST VQA Pipeline — 实验操作日志

---

## 2026-05-10（Day 1）

### 上午：部署 & 首次批量跑
- 部署 pipeline 到 Server A，配置 Neo4j、环境变量
- 启动 `run_batch_fast.py plans/plan_B_remote1.json` 批量跑 2292 帧
- Phase 1 (OFFLINE) 完成 2272/2292 帧
- Phase 2 (GENERATE) 跑了 ~5h，仅完成 19 帧（0.8%）
- 瓶颈：大帧 (45 nodes) 耗时 66 min/帧，ETA ~20 天，不可接受

### 下午：性能优化（5 项）
1. `plan_to_qa_record` 增加 `skip_cypher` 参数 — 跳过 Cypher 字符串构建
2. `_pick_plan` 改为 first-feasible — 消除 O(n²) coverage_gain
3. 移除 per-QA 文件 I/O — 改为批量写入
4. 新增 `_memory_verify` — 内存验证替代 Neo4j（已验证 100% 等价）
5. plan_cache 完整预过滤 — 构建阶段 `_memory_verify + verify_valid` 一次过滤

### 性能测试结果（frame14, 45 nodes）
| 版本 | 耗时 | 说明 |
|------|------|------|
| 原始 | 66 min | Neo4j verify，per-QA I/O |
| skip_verify | 6 min | 跳过所有 verify |
| memory_verify + 预过滤 | 31.9 min | 完整验证，质量等价 |

### 当前状态
- L2 覆盖率 100%（42570/42570）
- 批量跑未启���，等待进一步优化
- selection+gen 阶段仍占 30.8 min（瓶颈）

---

## 2026-05-11（Day 2）

### 10:25 性能分析
- 用 profiler 对 frame14(45 nodes) 做了详细拆解
- 发现 plan_to_qa_record 本身只需 0.004ms/QA
- 真正的 31.9 分钟全部花在 selection loop 的 fallback 全量扫描上

### 10:30 根因定位
- 根因: selection loop 有个配额限制(family_cap_blocked), converge 类题目超配额后被跳过
- 快速线性扫描只能覆盖 20% 就跳完了
- 剩余 80% 走慢速全量扫描 _cursor_select, O(n^2) 复杂度, 花了 30 分钟
- 验证: 去掉配额限制后, 线性扫描 0.4 秒跑完 100% 覆盖

### 10:33 修改1: 移除选题阶段的配额限制
- _pick_plan 不再调用 family_cap_blocked
- 配额信息改为在 emit_qa_records 中标记 selection_phase (primary vs coverage_backfill)
- 删除 _cursor_select 全量扫描 fallback (不再需要)
- 效果: selection+gen 从 1846s 降为 1.9s

### 10:38 修改2: 直接验证函数 _direct_plan_verify
- 原方案: plan_to_qa_record + _memory_verify + verify_valid (3步串联)
- 新方案: _direct_plan_verify 直接从 DryRunInput/DryRunPlan 验证
- 等价性测试: 686440 道题全部匹配, 0 个不一致
- ���果: plan_cache 从 59s 降为 48s

### 性能对比 (frame14, 45 nodes)
| 版本 | 耗时 | plan_cache | selection+gen | 覆盖率 |
|------|------|-----------|---------------|--------|
| 原始 | 66 min | 52s | 3840s | 100% |
| v3 昨天最优 | 31.9 min | 58s | 1846s | 100% |
| v5 今天优化 | 1.0 min | 48s | 1.9s | 100% |

### 质量验证 (v5)
- L2 覆盖率 100% (42570/42570)
- L0=45/45, L1=990/990
- 验证等价性 686440/686440 = 100%
- 题目数量从 40447 变为 40256 (选题顺序变化导致, 覆盖率相同)

### 10:49 修改3: 两轮生成策略
- 思路: 把"覆盖"和"题型丰富"解耦
- Round 1: 只用 converge + diverge 跑完覆盖 (需要约束规划, 重量级)
- Round 2: 对每个 gap 直接生成一道 direction_chain / distance_chain / viewpoint_transfer
  - 不需要约束规划、不需要 verify, 每道题 O(1) 生成
  - 用 round-robin 轮换题型保证多样性
- build_gap_plans 只保留 converge + diverge 的 plan (跳过 chain/viewpoint)

### V6 两轮策略测试结果 (frame14, 45 nodes)
| 阶段 | 生成数 | 耗时 | 说明 |
|------|--------|------|------|
| plan_cache | - | 45s | 少了 3s(不再生成chain/viewpoint plan) |
| Round 1 (converge+diverge) | 24,737 | 1.6s | 覆盖 27173/42570 (63.8%) |
| Round 2 (chain+viewpoint) | 42,570 | 1.5s | 每个gap一道轻量题 |
| **总计** | **67,307** | **1.0 min** | L2 覆盖率 100% |

### 性能汇总 (frame14, 45 nodes, 所有版本)
| 版本 | 耗时 | 生成数 | 覆盖率 | 题型 |
|------|------|--------|--------|------|
| 原始 | 66 min | ~40K | 100% | 混合 |
| v3 昨天最优 | 31.9 min | ~40K | 100% | 混合 |
| v5 今天优化 | 1.0 min | ~40K | 100% | 混合(converge为主) |
| **v6 两轮策略** | **1.0 min** | **67K** | **100%** | **converge+diverge+chain+viewpoint** |

### 10:55 启动批量跑
- 命令: `nohup python run_batch_fast.py plans/plan_B_remote1.json --phase 2 > outputs/batch_v6_$(date +%Y%m%d_%H%M%S).log 2>&1 &`
- 预估: 大帧 ~1min, 小帧更快, 2292帧预估 3-8 小时
- 日志: outputs/batch_v6_*.log
- 进度查看: `grep "RESULT\|DONE\|ERROR" outputs/batch_v6_*.log | tail -20`
