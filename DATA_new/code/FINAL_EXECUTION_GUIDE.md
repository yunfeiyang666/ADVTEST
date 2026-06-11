# 两帧完整测试 - 最终执行指南

## 执行步骤

### 步骤1: 生成场景图
```bash
cd E:\Project\ADVTEST\DATA_new\code
python generate_two_frames_scene_graphs.py
```

### 步骤2: 运行完整流程
```bash
python run_from_plan.py two_frames_plan.json
```

## 已创建的文件
- two_frames_plan.json - Plan文件（包含两帧配置）
- generate_two_frames_scene_graphs.py - 场景图生成脚本
- run_from_plan.py - 从plan文件运行的脚本

## 输出
- RQ.xlsx (filter_record, raw_coverage, question-answer-our)
- generated_qa/ 目录

## 验证点
1. Mid节点具体化：问题使用car1而不是car
2. is_unique比例：60-80%
3. 覆盖完成：所有gap标记为covered
