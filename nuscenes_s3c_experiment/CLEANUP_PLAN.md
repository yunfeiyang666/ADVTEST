# 文件清理计划（谨慎版）

## ⚠️ 清理前必读
1. **不要一次性全删**，建议分批审查
2. 标记为 🟢 的最安全，🟡 的需要确认，🔴 的谨慎删除
3. 所有文件先移动到 `_archived/` 文件夹，而不是直接删除

---

## 🟢 第一批：临时测试文件（最安全）

### 临时脚本（以 tmp_ 开头）
```
tmp_check_direction.py                 # 临时方向检查
tmp_inspect_neo4j_0916.py              # 临时Neo4j检查
tmp_inspect_scene_0916.py              # 临时场景检查
tmp_ir_agg.py                          # 临时IR聚合
tmp_ir_stat.py                         # 临时IR统计
tmp_run_core_examples.py               # 临时核心示例
```

### 单次验证脚本（verify_）
```
verify_4vs8_direction.py               # 4方位vs8方位验证
verify_back_right.py                   # back-right方向验证
verify_original_data.py                # 原始数据验证
verify_q11_direction.py                # Q11方向验证
verify_q3q4.py                         # Q3Q4验证
verify_q8_direction.py                 # Q8方向验证
verify_qa_data.py                      # QA数据验证
verify_queries.py                      # 查询验证
verify_sample_token.py                 # 样本token验证
```

### 一次性调试脚本（debug_, inspect_, probe_）
```
debug_all_questions.py                 # 调试所有问题
debug_extraction.py                    # 调试提取
inspect_trailer_same_status_0553.py    # 检查trailer状态
inspect_trailer_same_status_detailed_0553.py
probe_same_status_rules_0553.py        # 探测状态规则
```

### 单次检查脚本（check_）
```
check_bicycle_heading.py               # 检查自行车朝向
check_data.py                          # 检查数据
check_empty_results.py                 # 检查空结果
check_format_issue.py                  # 检查格式问题
check_json_direction.py                # 检查JSON方向
check_official_qa_count.py             # 检查官方QA数量
```

---

## 🟡 第二批：旧版/重复测试文件（需确认）

### 旧版测试文件
```
test_coverage_vqa.py                   # 被 v2 替代？
test_coverage_vqa_v2.py                # 被 fixed 替代？
test_coverage_vqa_v2_fixed.py          # 最新版
run_official_qa_pretest.py             # 被 enhanced 替代？
test_official_qa_baseline.py           # 基线测试
test_official_qa_ir.py                 # IR测试
```

### 可能已完成的分析脚本（analyze_）
```
analyze_errors_detailed.py             # 详细错误分析
analyze_failures.py                    # 失败分析
analyze_fixed_results.py               # 修复结果分析
analyze_logic_errors.py                # 逻辑错误分析
analyze_remaining_errors.py            # 剩余错误分析
analyze_q5_q11.py                      # Q5/Q11分析
analyze_q6_q7_q11_q12_q13.py          # 多问题分析
analyze_qa_results.py                  # QA结果分析
analyze_scene0553_q8_relations.py      # Scene 0553 Q8关系分析
```

### 特定场景的一次性脚本
```
manual_check_q11_q13.py                # 手动检查Q11/Q13
analyze_scene_data.py                  # 分析场景数据
check_bicycle_heading.py               # 检查自行车朝向
```

---

## 🔴 第三批：可能还有用（谨慎）

### 目前在用或刚修改的（保留）
```
✅ run_official_qa_enhanced.py          # 当前正在测试！
✅ regen_103_38.py                      # 刚创建的
✅ generate_coverage_scenes_v2.py       # 刚修复的
✅ step2_full_relation_scene_graph.py   # 刚修复的核心文件
```

### 可能的核心分析工具（保留）
```
✅ analyze_direction_coordinate_system.py  # 方向坐标系统分析
✅ analyze_qa_coverage.py                   # QA覆盖率分析
✅ analyze_scene_coverage.py                # 场景覆盖率分析
✅ coverage_core.py                         # 覆盖率核心
✅ calculate_coverage.py                    # 计算覆盖率
```

### 其他测试工具（暂时保留）
```
✅ test_all_coverage.py                # 全覆盖测试
✅ test_scene_coverage.py              # 场景覆盖测试
✅ test_failed_cases_retest.py         # 失败案例重测
✅ run_full_coverage_test.py           # 全覆盖测试运行
✅ quick_vqa_smoke_test.py             # 快速冒烟测试
```

---

## 📋 建议清理步骤

### Step 1: 创建归档文件夹
```powershell
New-Item -ItemType Directory -Path "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived" -Force
New-Item -ItemType Directory -Path "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived\batch1_tmp_verify" -Force
```

### Step 2: 移动第一批文件（最安全）
```powershell
# 移动 tmp_* 文件
Move-Item "E:\Project\ADVTEST\nuscenes_s3c_experiment\tmp_*.py" "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived\batch1_tmp_verify\" -Force

# 移动 verify_* 文件
Move-Item "E:\Project\ADVTEST\nuscenes_s3c_experiment\verify_*.py" "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived\batch1_tmp_verify\" -Force

# 移动 debug_/inspect_/probe_* 文件
Move-Item "E:\Project\ADVTEST\nuscenes_s3c_experiment\debug_*.py" "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived\batch1_tmp_verify\" -Force
Move-Item "E:\Project\ADVTEST\nuscenes_s3c_experiment\inspect_*.py" "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived\batch1_tmp_verify\" -Force
Move-Item "E:\Project\ADVTEST\nuscenes_s3c_experiment\probe_*.py" "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived\batch1_tmp_verify\" -Force

# 移动 check_* 文件
Move-Item "E:\Project\ADVTEST\nuscenes_s3c_experiment\check_*.py" "E:\Project\ADVTEST\nuscenes_s3c_experiment\_archived\batch1_tmp_verify\" -Force
```

### Step 3: 测试是否影响核心功能
运行核心测试确保没问题：
```powershell
python run_official_qa_enhanced.py
```

### Step 4: 如果没问题，继续第二批
创建第二批归档文件夹并移动旧版测试文件

---

## ⚠️ 不要删除的文件
- config.py 系列
- step*.py 系列（核心流程）
- vqa_pipeline/ 文件夹下的所有文件
- requirements.txt
- README.md
- 任何 `generate_*.py` （生成脚本）
- 任何 `import_*.py` （导入脚本）

---

## 📊 统计
- 🟢 第一批（最安全）: ~30个文件
- 🟡 第二批（需确认）: ~15个文件
- 🔴 保留文件: ~40个核心文件

**建议**：先执行 Step 1 和 Step 2，移动第一批30个文件到归档，测试后再决定是否继续。
