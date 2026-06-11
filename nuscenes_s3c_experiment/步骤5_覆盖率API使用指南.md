# 步骤5：覆盖率API使用指南

## 🎯 **目标**

实现真正的覆盖率计算（带分母），提供API接口。

---

## 📋 **快速开始**

### **运行覆盖率计算：**

```powershell
cd E:\Project\ADVTEST\nuscenes_s3c_experiment
& e:/Project/ADVTEST/.venv310/Scripts/Activate.ps1
python step5_run_coverage_api.py
```

### **预期输出：**

```
============================================================
快速覆盖率计算
============================================================

理论总组合数（分母）: 144

实际覆盖组合数（分子）: 45

覆盖率: 31.25%
未覆盖: 99种组合 (68.75%)

✓ 结果已保存
```

---

## 📊 **覆盖率API的5个核心功能**

### **API 1: calculate_coverage()**
```python
# 计算总体覆盖率
coverage_report = api.calculate_coverage()

# 返回：
{
    'total_combinations': 144,      # 分母
    'actual_combinations': 45,      # 分子
    'coverage_percentage': 31.25,   # 覆盖率
    'uncovered_count': 99           # 未覆盖数
}
```

---

### **API 2: identify_blind_spots()**
```python
# 识别覆盖盲区
uncovered = api.identify_blind_spots()

# 返回：
[
    ('Motorcycle', 'near', 'rear', 'moving'),  # 未覆盖组合1
    ('Bus', 'far', 'left', 'stopped'),         # 未覆盖组合2
    ...
]
```

---

### **API 3: get_coverage_by_dimension()**
```python
# 按维度统计覆盖率
dimension_stats = api.get_coverage_by_dimension()

# 返回：
{
    'distance': {
        'near': {'count': 20, 'rate': 41.67%},
        'mid': {'count': 18, 'rate': 37.50%},
        'far': {'count': 7, 'rate': 14.58%}
    },
    'direction': {...},
    'object_type': {...}
}
```

---

### **API 4: generate_coverage_heatmap()**
```python
# 生成覆盖率热力图
api.generate_heatmap('output/figures/coverage_heatmap.png')

# 生成：
# 距离×方向的热力图
# 颜色表示覆盖密度
# 白色表示盲区
```

---

### **API 5: generate_coverage_report()**
```python
# 生成完整报告
report = api.generate_coverage_report('output/coverage_report.json')

# 包含：
# - 覆盖率统计
# - 实际覆盖列表
# - 未覆盖列表
# - 维度统计
```

---

## 🎯 **覆盖率计算原理**

### **第1步：定义覆盖空间（分母）**

```
场景特征空间 = 距离 × 方向 × 运动 × 对象

距离等级（3种）:
- near: 0-10m
- mid: 10-30m
- far: >30m

方向扇区（4种）:
- front, rear, left, right

运动状态（2种）:
- moving, stopped

对象类型（6种）:
- Pedestrian, Car, Truck, Bus, Bicycle, Motorcycle

理论总数 = 3 × 4 × 2 × 6 = 144种
```

---

### **第2步：查询实际覆盖（分子）**

```cypher
MATCH (ego)-[r]->(obj)
WHERE r.distance IS NOT NULL
RETURN DISTINCT 
    CASE 
        WHEN r.distance < 10 THEN 'near'
        WHEN r.distance < 30 THEN 'mid'
        ELSE 'far'
    END AS distance_level,
    r.direction_sector AS direction,
    CASE WHEN r.moving THEN 'moving' ELSE 'stopped' END AS motion,
    obj.type AS object_type
```

**结果示例：**
```
实际覆盖：45种组合
```

---

### **第3步：计算覆盖率**

```
覆盖率 = 实际覆盖 / 理论总数
      = 45 / 144
      = 0.3125
      = 31.25%

未覆盖 = 144 - 45 = 99种
未覆盖率 = 68.75%
```

---

## 📊 **覆盖率热力图示例**

```
距离×方向覆盖矩阵：

        front  rear  left  right
near     15     8     5     12
mid      20     6     3     10
far      8      2     0     1

解读：
- front + near: 15种配置 ← 覆盖最好
- left + far: 0种配置 ← 盲区！
- right + far: 1种配置 ← 覆盖很差
```

---

## 🎯 **与step4的区别**

| 功能 | step4 | step5 |
|------|-------|-------|
| **查询配置** | ✅ 55种 | ✅ 45种 |
| **定义分母** | ❌ 无 | ✅ 144种 |
| **计算覆盖率** | ❌ 无 | ✅ 31.25% |
| **识别盲区** | ❌ 无 | ✅ 99种 |
| **热力图** | ❌ 无 | ✅ 有 |
| **API封装** | ❌ 无 | ✅ 5个API |

---

## 🚀 **现在运行**

```powershell
python step5_run_coverage_api.py
```

**预计运行时间：10秒**

**输出文件：**
- `output/statistics/step5_coverage_result.json`
- 控制台显示覆盖率统计

---

## 📝 **给PPT用的内容**

### **覆盖率定义页：**
```
场景特征空间定义：
- 距离等级：3种（near <10m, mid 10-30m, far >30m）
- 方向扇区：4种（front, rear, left, right）
- 运动状态：2种（moving, stopped）
- 对象类型：6种（Pedestrian, Car, Truck, Bus, Bicycle, Motorcycle）

理论总组合数：3 × 4 × 2 × 6 = 144种场景原子
```

### **覆盖率计算页：**
```
覆盖率公式：
覆盖率 = 实际覆盖的组合数 / 理论总组合数

计算结果：
- 理论总数（分母）：144种
- 实际覆盖（分子）：45种
- 覆盖率：31.25%
- 未覆盖（盲区）：99种（68.75%）

结论：存在大量覆盖盲区，需要针对性测试
```

---

**运行吧！看看真正的覆盖率是多少！** 🚀
