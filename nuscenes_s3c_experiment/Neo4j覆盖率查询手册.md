# Neo4j覆盖率查询手册 - 直接在浏览器中操作

## 🎯 **目标**

直接在Neo4j Browser中运行Cypher查询，计算覆盖率。

---

## 📋 **完整操作步骤**

### **步骤1：查询实际覆盖的组合数（分子）**

在Neo4j Browser中输入并运行：

```cypher
// 查询实际覆盖的组合
MATCH (ego:Ego)-[r:SPATIAL_RELATION]->(obj:Object)
WHERE r.distance IS NOT NULL
  AND r.direction_sector IS NOT NULL

// 映射距离到等级
WITH CASE 
        WHEN r.distance < 10 THEN 'near'
        WHEN r.distance < 30 THEN 'mid'
        ELSE 'far'
     END AS distance_level,
     r.direction_sector AS direction,
     CASE WHEN r.moving THEN 'moving' ELSE 'stopped' END AS motion,
     CASE 
        WHEN obj:Pedestrian THEN 'Pedestrian'
        WHEN obj:Car THEN 'Car'
        WHEN obj:Truck THEN 'Truck'
        WHEN obj:Bus THEN 'Bus'
        WHEN obj:Bicycle THEN 'Bicycle'
        WHEN obj:Motorcycle THEN 'Motorcycle'
     END AS object_type

WHERE distance_level IS NOT NULL
  AND direction IS NOT NULL
  AND object_type IS NOT NULL

// 去重并统计
RETURN DISTINCT distance_level, direction, motion, object_type
```

**看结果：**
- 切换到"Table"视图
- 数一下有多少行 = 实际覆盖数（分子）
- 例如：45行

---

### **步骤2：手动计算覆盖率**

```
理论总数（分母）= 3距离 × 4方向 × 2运动 × 6对象 = 144

实际覆盖（分子）= 45（从步骤1的结果数行数）

覆盖率 = 45 / 144 = 0.3125 = 31.25%

未覆盖 = 144 - 45 = 99种
未覆盖率 = 68.75%
```

---

### **步骤3：查询覆盖率统计（带计数）**

```cypher
// 统计每种组合的频率
MATCH (ego:Ego)-[r:SPATIAL_RELATION]->(obj:Object)
WHERE r.distance IS NOT NULL
  AND r.direction_sector IS NOT NULL

WITH CASE 
        WHEN r.distance < 10 THEN 'near'
        WHEN r.distance < 30 THEN 'mid'
        ELSE 'far'
     END AS distance_level,
     r.direction_sector AS direction,
     CASE WHEN r.moving THEN 'moving' ELSE 'stopped' END AS motion,
     CASE 
        WHEN obj:Pedestrian THEN 'Pedestrian'
        WHEN obj:Car THEN 'Car'
        WHEN obj:Truck THEN 'Truck'
        WHEN obj:Bus THEN 'Bus'
        WHEN obj:Bicycle THEN 'Bicycle'
        WHEN obj:Motorcycle THEN 'Motorcycle'
     END AS object_type

WHERE distance_level IS NOT NULL
  AND direction IS NOT NULL
  AND object_type IS NOT NULL

RETURN distance_level, direction, motion, object_type, COUNT(*) AS frequency
ORDER BY frequency DESC
```

**看结果：**
- 每一行 = 一种配置
- frequency = 该配置出现的次数
- 总行数 = 实际覆盖数

---

### **步骤4：按维度统计覆盖**

#### **4.1 距离维度覆盖：**

```cypher
// 统计每个距离等级的覆盖情况
MATCH (ego:Ego)-[r:SPATIAL_RELATION]->(obj:Object)
WHERE r.distance IS NOT NULL

WITH CASE 
        WHEN r.distance < 10 THEN 'near'
        WHEN r.distance < 30 THEN 'mid'
        ELSE 'far'
     END AS distance_level

RETURN distance_level, COUNT(DISTINCT [r.direction_sector, r.moving, labels(obj)[1]]) AS unique_configs
ORDER BY distance_level
```

**结果示例：**
```
distance_level  unique_configs
near            20
mid             18
far             7
```

**解读：**
- near距离：20种不同配置
- mid距离：18种不同配置
- far距离：7种不同配置

---

#### **4.2 方向维度覆盖：**

```cypher
// 统计每个方向的覆盖情况
MATCH (ego:Ego)-[r:SPATIAL_RELATION]->(obj:Object)
WHERE r.direction_sector IS NOT NULL

RETURN r.direction_sector AS direction, 
       COUNT(*) AS total_objects
ORDER BY total_objects DESC
```

**结果示例：**
```
direction  total_objects
front      136
right      72
rear       50
left       25
```

---

### **步骤5：生成覆盖率矩阵**

```cypher
// 距离×方向的覆盖矩阵
MATCH (ego:Ego)-[r:SPATIAL_RELATION]->(obj:Object)
WHERE r.distance IS NOT NULL
  AND r.direction_sector IS NOT NULL

WITH CASE 
        WHEN r.distance < 10 THEN 'near'
        WHEN r.distance < 30 THEN 'mid'
        ELSE 'far'
     END AS distance_level,
     r.direction_sector AS direction

RETURN distance_level, direction, COUNT(*) AS count
ORDER BY distance_level, direction
```

**结果示例：**
```
distance  direction  count
near      front      45
near      left       12
near      rear       20
near      right      28
mid       front      60
mid       left       8
mid       rear       15
mid       right      30
far       front      31
far       left       5
far       rear       15
far       right      14
```

**手动整理成矩阵：**
```
        front  rear  left  right
near     45     20    12    28
mid      60     15    8     30
far      31     15    5     14
```

---

## 🎯 **覆盖率计算总结查询**

### **一次性显示所有关键指标：**

```cypher
// 覆盖率总结查询
MATCH (ego:Ego)-[r:SPATIAL_RELATION]->(obj:Object)
WHERE r.distance IS NOT NULL
  AND r.direction_sector IS NOT NULL

WITH CASE 
        WHEN r.distance < 10 THEN 'near'
        WHEN r.distance < 30 THEN 'mid'
        ELSE 'far'
     END AS distance_level,
     r.direction_sector AS direction,
     CASE WHEN r.moving THEN 'moving' ELSE 'stopped' END AS motion,
     CASE 
        WHEN obj:Pedestrian THEN 'Pedestrian'
        WHEN obj:Car THEN 'Car'
        WHEN obj:Truck THEN 'Truck'
        WHEN obj:Bus THEN 'Bus'
        WHEN obj:Bicycle THEN 'Bicycle'
        WHEN obj:Motorcycle THEN 'Motorcycle'
     END AS object_type

WHERE distance_level IS NOT NULL
  AND object_type IS NOT NULL

WITH DISTINCT distance_level, direction, motion, object_type

RETURN 
    COUNT(*) AS actual_combinations,
    144 AS total_combinations,
    toFloat(COUNT(*)) / 144 * 100 AS coverage_percentage,
    144 - COUNT(*) AS uncovered_combinations
```

**结果示例：**
```
actual_combinations: 45
total_combinations: 144
coverage_percentage: 31.25
uncovered_combinations: 99
```

**这就是完整的覆盖率！** 🎯

---

## 📸 **操作指南**

### **1. 打开Neo4j Browser**
- 访问：http://localhost:7474

### **2. 复制查询**
- 复制上面的"覆盖率总结查询"

### **3. 粘贴并运行**
- 粘贴到命令框
- 点击运行（或Ctrl+Enter）

### **4. 查看结果**
- 切换到"Table"视图
- 看到4个数字：
  - actual_combinations（分子）
  - total_combinations（分母）
  - coverage_percentage（覆盖率）
  - uncovered_combinations（盲区数）

### **5. 截图保存**
- 截图这个结果
- 放到PPT里

---

## ✅ **总结**

### **在Neo4j Browser中可以：**
- ✅ 查询实际覆盖（分子）
- ✅ 定义理论总数（分母）
- ✅ 计算覆盖率（百分比）
- ✅ 一次性显示所有指标

### **不需要Python脚本！**
- 直接用Cypher查询
- 立即看到结果
- 方便演示给老师

---

**现在试试"覆盖率总结查询"吧！** 🚀

**应该能看到：覆盖率31.25%，未覆盖99种！** 🎯
