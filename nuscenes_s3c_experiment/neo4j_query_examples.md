# Neo4j查询操作示例

## 6-7. 查询操作（文字描述 + Cypher函数 + 查询结果）

---

## 查询1：查看所有对象及其类型

### 文字描述
查询数据库中所有的对象节点，显示它们的唯一ID和类型，用于了解场景中有哪些参与者。

### Cypher查询
```cypher
MATCH (obj:Object)
RETURN obj.unique_id AS 对象ID, obj.type AS 类型
LIMIT 20
```

### 预期结果
```
对象ID        类型
ego          ego
car1         car
car2         car
pedestrian1  pedestrian
truck1       truck
...
```

### 使用场景
- 场景概览
- 统计对象数量
- 了解场景复杂度

---

## 查询2：查看Ego车周围的所有对象

### 文字描述
以Ego车为中心，查询所有与Ego车有关系的对象，包括它们的位置和距离信息。

### Cypher查询
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
RETURN 
    obj.unique_id AS 对象ID,
    obj.type AS 类型,
    r.predicates AS 空间关系,
    r.distance AS 距离,
    obj.translation AS 位置
ORDER BY r.distance ASC
```

### 预期结果
```
对象ID    类型         空间关系          距离    位置
car1     car         [front, near]    8.5    {x: 8.2, y: 1.3, z: 0.5}
car2     car         [left, mid]      15.2   {x: 5.1, y: -14.3, z: 0.4}
ped1     pedestrian  [front, near]    6.8    {x: 6.5, y: 0.8, z: 0.0}
...
```

### 使用场景
- 碰撞预警
- 路径规划
- 安全距离判断

---

## 查询3：查找前方近距离的危险对象

### 文字描述
查询Ego车前方10米以内的所有对象，这些是需要重点关注的潜在危险对象。

### Cypher查询
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
WHERE 'front' IN r.predicates 
  AND r.distance < 10
RETURN 
    obj.unique_id AS 对象ID,
    obj.type AS 类型,
    r.distance AS 距离,
    obj.velocity AS 速度
ORDER BY r.distance ASC
```

### 预期结果
```
对象ID    类型         距离    速度
car1     car         8.5    {vx: 2.3, vy: 0.1, vz: 0.0}
ped1     pedestrian  6.8    {vx: 0.5, vy: -0.2, vz: 0.0}
bicycle1 bicycle     9.2    {vx: 3.1, vy: 0.5, vz: 0.0}
```

### 使用场景
- 自动紧急制动(AEB)
- 前向碰撞预警(FCW)
- 自适应巡航控制(ACC)

---

## 查询4：查找所有移动的车辆

### 文字描述
识别场景中所有正在移动的车辆（速度大于阈值），用于动态风险评估。

### Cypher查询
```cypher
MATCH (obj:Object)
WHERE obj.type = 'car' 
  AND obj.speed > 1.0
RETURN 
    obj.unique_id AS 车辆ID,
    obj.speed AS 速度,
    obj.velocity AS 速度矢量,
    obj.translation AS 位置
ORDER BY obj.speed DESC
```

### 预期结果
```
车辆ID    速度     速度矢量                      位置
car3     5.8     {vx: 5.2, vy: 2.1, vz: 0.0}  {x: 12.3, y: -8.5, z: 0.5}
car1     2.3     {vx: 2.3, vy: 0.1, vz: 0.0}  {x: 8.2, y: 1.3, z: 0.5}
car5     1.5     {vx: 1.2, vy: 0.9, vz: 0.0}  {x: -5.6, y: 10.2, z: 0.4}
```

### 使用场景
- 动态障碍物追踪
- 轨迹预测
- 交通流分析

---

## 查询5：对象之间的关系（全关系图查询）

### 文字描述
查询任意两个对象之间的空间关系，展示场景中的完整关系网络。

### Cypher查询
```cypher
MATCH (obj1:Object)-[r:RELATES_TO]->(obj2:Object)
WHERE obj1.unique_id <> 'ego' 
  AND obj2.unique_id <> 'ego'
RETURN 
    obj1.unique_id AS 源对象,
    obj2.unique_id AS 目标对象,
    r.predicates AS 关系,
    r.distance AS 距离
LIMIT 10
```

### 预期结果
```
源对象    目标对象     关系              距离
car1     car2        [left, mid]      18.5
car1     ped1        [rear, near]     5.2
car2     truck1      [front, far]     28.3
ped1     bicycle1    [right, near]    4.8
...
```

### 使用场景
- 场景理解
- 多对象交互分析
- 复杂场景推理

---

## 查询6：按方位统计对象分布

### 文字描述
统计Ego车四个方向（前后左右）分别有多少对象，了解周围环境的分布情况。

### Cypher查询
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
WITH 
    CASE 
        WHEN 'front' IN r.predicates THEN '前方'
        WHEN 'rear' IN r.predicates THEN '后方'
        WHEN 'left' IN r.predicates THEN '左侧'
        WHEN 'right' IN r.predicates THEN '右侧'
    END AS 方位,
    obj.type AS 类型
RETURN 方位, 类型, COUNT(*) AS 数量
ORDER BY 方位, 数量 DESC
```

### 预期结果
```
方位    类型         数量
前方    car         5
前方    pedestrian  3
前方    bicycle     1
左侧    car         4
左侧    truck       2
右侧    car         3
后方    car         2
```

### 使用场景
- 环境感知
- 态势评估
- 决策规划

---

## 查询7：按距离级别统计对象

### 文字描述
统计近、中、远三个距离级别分别有多少对象，评估不同风险等级的对象分布。

### Cypher查询
```cypher
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
WITH 
    CASE 
        WHEN 'near' IN r.predicates THEN '近距离(<10m)'
        WHEN 'mid' IN r.predicates THEN '中距离(10-25m)'
        WHEN 'far' IN r.predicates THEN '远距离(>25m)'
    END AS 距离级别,
    obj.type AS 类型
RETURN 距离级别, 类型, COUNT(*) AS 数量
ORDER BY 距离级别, 数量 DESC
```

### 预期结果
```
距离级别          类型         数量
近距离(<10m)     car         3
近距离(<10m)     pedestrian  4
中距离(10-25m)   car         6
中距离(10-25m)   truck       2
远距离(>25m)     car         2
```

### 使用场景
- 风险等级评估
- 注意力分配
- 传感器资源调度

---

## 查询8：场景统计信息

### 文字描述
获取场景的整体统计信息，包括对象总数、关系总数、平均距离等。

### Cypher查询
```cypher
MATCH (obj:Object)
WITH COUNT(obj) AS 对象总数
MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->()
WITH 对象总数, COUNT(r) AS 关系总数, AVG(r.distance) AS 平均距离
MATCH (obj:Object)
RETURN 
    对象总数,
    关系总数,
    ROUND(平均距离, 2) AS 平均距离,
    COUNT(DISTINCT obj.type) AS 对象类型数
```

### 预期结果
```
对象总数  关系总数  平均距离  对象类型数
25       24       16.5     6
```

### 使用场景
- 场景复杂度评估
- 数据质量检查
- 系统性能监控

---

## 如何在Neo4j Browser中执行

### 步骤：

1. **打开Neo4j Browser**
   ```
   http://localhost:7474
   ```

2. **连接数据库**
   - URI: `neo4j://localhost:7687`
   - 用户名: `neo4j`
   - 密码: `87017563`

3. **复制查询语句**
   - 从上面选择一个查询
   - 复制Cypher代码

4. **执行查询**
   - 粘贴到查询框
   - 点击运行按钮（或按Ctrl+Enter）

5. **查看结果**
   - 表格视图：查看数据
   - 图形视图：查看关系
   - 导出结果：用于PPT

---

## PPT演示建议

### 演示流程：
1. 先展示简单查询（查询1-2）
2. 展示实用查询（查询3-4）
3. 展示复杂查询（查询5）
4. 展示统计查询（查询6-8）

### 截图要点：
- 查询语句要清晰可见
- 结果表格要完整
- 图形视图要美观
- 添加必要的注释

### 演讲要点：
- 强调查询的实际意义
- 解释结果的含义
- 说明应用场景
- 展示系统优势
