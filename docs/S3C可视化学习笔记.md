# S3C可视化学习笔记

## 📚 一、S3C核心配置

### 1.1 距离分档（5档）
```python
# 来自S3C官方README
距离档位         范围                物理意义
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
near_coll       ≤ 4m               Near Collision (接近碰撞)
super_near      4m < d ≤ 7m        Super Near (超近)
very_near       7m < d ≤ 10m       Very Near (很近)
near            10m < d ≤ 16m      Near (近)
visible         16m < d ≤ 25m      Visible (可见)
(无关系)        25m < d ≤ 50m      No Distance Relation
(不包含)        d > 50m            Entity not included
```

### 1.2 角度分档（4象限 + 左右）
```python
# 角度关系1：左右（不可参数化）
- Left: 相对于车辆左侧
- Right: 相对于车辆右侧
- 特点：双向性（两车可能互为对方的左/右）

# 角度关系2：前后+直接/侧面（4象限）
Direct Front (DF)   : 正前方  (315° - 45°)    90度范围
Side Front (SF)     : 前侧方  (45° - 135°)    90度范围
Direct Rear (DR)    : 正后方  (135° - 225°)   90度范围
Side Rear (SR)      : 后侧方  (225° - 315°)   90度范围
```

---

## 🎯 二、S3C的三种可视化

### 2.1 聚类分布可视化（Cluster Distribution）

**目的：** 展示场景图如何被聚类成等价类

**文件：** `carla/cluster_figure_generator.py`

**输出：** `study_data/figures/cluster_viz_carla_rsv.png`

**关键代码逻辑：**
```python
# 1. 加载聚类数据
datasets = {}
for dataset_file in glob.glob('*.json'):
    datasets[graph_type] = Dataset.load_from_file(dataset_file)

# 2. 统计每个聚类的大小
box_vals = []
for cluster in datasets._clusters:
    box_vals.append(len(cluster))  # 每个聚类包含多少图像

# 3. 双Y轴可视化
ax1.scatter(cluster_ids, box_vals)     # 左轴：每个聚类的大小
ax2.plot(cluster_ids, cumulative)      # 右轴：累积覆盖的图像数

# 4. 标注关键点
- 最大聚类覆盖多少图像
- 前10个聚类覆盖多少图像
- 单例聚类（singleton）的分界线
```

**可视化效果：**
```
Images in Class (left)
    ↑
10k │ •                              ← 最大聚类
    │  •
 5k │   ••
    │    •••
    │       •••••••••••••••••
  0 └────────────────────────────→ Equivalence Class ID
                                     Cumulative Images (right)
```

---

### 2.2 覆盖率对比可视化（Coverage Comparison）

**目的：** 对比不同抽象方法的覆盖率性能

**文件：** `carla/meta_figure_generator.py`

**输出：** `study_data/figures/new_num_clusters_80_20_trivial_legend_within.png`

**关键代码逻辑：**
```python
# 计算PNFNC (Percentage of Novel Failures Not Covered)
def compute_pnfnc(train_clusters, test_failures):
    novel_failures = 0
    for failure in test_failures:
        if failure not in train_clusters:
            novel_failures += 1
    return novel_failures / len(test_failures) * 100

# 对比5种抽象方法
abstractions = ['E', 'EL', 'ER', 'ELR', 'ERS']
for abstraction in abstractions:
    pnfnc_scores.append(compute_pnfnc(...))
    
# 绘制对比图
plt.plot(num_clusters, pnfnc_scores, label=abstraction)
```

**可视化效果：**
```
PNFNC (%)
    ↑
100 │ ╲
    │  ╲  Random Baseline
 50 │   ╲──────────────────
    │    ╲    ELR (最好)
    │     ╲╲╲
  0 └────────────────→ Number of Clusters
    0  5k  10k  15k  20k
```

---

### 2.3 决策树可视化（Decision Tree）

**目的：** 展示测试失败的分类规则

**文件：** `rq2/a/rq2a.py`

**输出：** 
- `study_data/figures/tree.png` (30,000 x 30,000像素)
- `study_data/figures/tree_small.png` (1,500 x 1,500像素)

**关键代码逻辑：**
```python
from sklearn.tree import DecisionTreeClassifier
from sklearn import tree

# 1. 准备数据：场景图特征 + 标签（失败/成功）
data, labels = get_data_for_training(test_fail, train)

# 2. 训练决策树
clf = DecisionTreeClassifier(max_depth=27)
clf.fit(data, labels)

# 3. 生成可视化
plt.figure(figsize=(15, 15))
tree.plot_tree(clf)
plt.savefig('tree_small.png')

plt.figure(figsize=(300, 300))  # 超大图！
tree.plot_tree(clf)
plt.savefig('tree.png')
```

**决策树的特征：**
```
每个节点表示一个谓词（predicate）：
- "car - lane_0 - near"
- "pedestrian - lane_1 - visible"
- "traffic_light - intersection - near_coll"

叶节点：
- Class 0: 测试失败
- Class 1: 训练通过
```

---

## 🔧 三、如何运行S3C的可视化

### 3.1 环境准备
```bash
cd e:/Project/ADVTEST/文献/s3c-main

# 安装环境
source env.sh  # 创建conda环境 'sg'
```

### 3.2 生成所有图表
```bash
# 运行主脚本（10-15分钟）
source study_data/generate_figures.sh

# 查看生成的图表
ls study_data/figures/
```

### 3.3 单独运行可视化

#### A. 聚类分布图
```bash
python3 carla/cluster_figure_generator.py \
    -i study_data/carla_clusters/ \
    -o study_data/figures/
```

#### B. 覆盖率对比图
```bash
python3 carla/meta_figure_generator.py \
    -i study_data/results/ \
    -o study_data/figures/
```

#### C. 决策树
```bash
python3 rq2/a/rq2a.py
```

---

## 📊 四、S3C vs 我们的实现对比

| 维度 | S3C官方 | 我们的实现 | 建议 |
|------|---------|-----------|------|
| **距离分档** | 5档 (≤4m, 4-7m, 7-10m, 10-16m, 16-25m) | 7档 | 可选择简化为5档 |
| **角度分档** | 4象限 (DF/SF/DR/SR) | 4象限 | ✅ 匹配 |
| **最大距离** | 50m | 50m | ✅ 匹配 |
| **可视化1** | 聚类分布图 | 无 | ⚠️ 需要添加 |
| **可视化2** | 覆盖率对比图 | 无 | ⚠️ 需要添加 |
| **可视化3** | 决策树 | 无 | ⚠️ 需要添加 |

---

## 🎨 五、为我们的场景图添加S3C风格可视化

### 5.1 聚类分布可视化（改编）

创建文件：`e:/Project/ADVTEST/scripts/vis_s3c_cluster_distribution.py`

```python
import json
import matplotlib.pyplot as plt
from collections import Counter

def visualize_cluster_distribution(scene_graph_jsonl):
    """
    可视化场景图的S3C聚类分布
    """
    # 1. 加载场景图
    clusters = Counter()
    
    with open(scene_graph_jsonl, 'r') as f:
        for line in f:
            scene = json.loads(line)
            
            # 2. 生成S3C签名（简化版）
            signature = []
            for node in scene['nodes']:
                if node['id'] == 'ego':
                    continue
                bins = node.get('bins', {})
                s3c_ang = bins.get('s3c_angular', 'unknown')
                s3c_dist = bins.get('s3c_distance', 'unknown')
                cat = node['category_name'].split('.')[0]
                
                signature.append(f"{cat}-{s3c_ang}-{s3c_dist}")
            
            # 3. 聚类键：排序后的签名
            cluster_key = tuple(sorted(signature))
            clusters[cluster_key] += 1
    
    # 4. 排序并可视化
    sorted_clusters = sorted(clusters.items(), key=lambda x: x[1], reverse=True)
    sizes = [size for _, size in sorted_clusters]
    cumulative = []
    total = 0
    for size in sizes:
        total += size
        cumulative.append(total)
    
    # 5. 双Y轴图
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax2 = ax1.twinx()
    
    color = 'tab:blue'
    ax1.scatter(range(len(sizes)), sizes, color=color, alpha=0.6)
    ax1.set_xlabel('Equivalence Class ID')
    ax1.set_ylabel('Images in Class', color=color)
    ax1.tick_params(axis='y', labelcolor=color)
    
    color = 'tab:red'
    ax2.plot(range(len(cumulative)), cumulative, color=color)
    ax2.set_ylabel('Cumulative Images', color=color)
    ax2.tick_params(axis='y', labelcolor=color)
    
    plt.title('S3C Cluster Distribution')
    plt.tight_layout()
    plt.savefig('s3c_cluster_distribution.png', dpi=150)
    print(f"Saved to s3c_cluster_distribution.png")
    print(f"Total clusters: {len(clusters)}")
    print(f"Largest cluster: {sizes[0]} images ({100*sizes[0]/sum(sizes):.1f}%)")
    print(f"Top 10 clusters: {sum(sizes[:10])} images ({100*sum(sizes[:10])/sum(sizes):.1f}%)")

# 使用示例
if __name__ == '__main__':
    visualize_cluster_distribution(
        'e:/Project/ADVTEST/data/nuscenes_scene_graph_mini_v2_s3c_enhanced.jsonl'
    )
```

### 5.2 S3C空间分档可视化

创建文件：`e:/Project/ADVTEST/scripts/vis_s3c_spatial_bins.py`

```python
import matplotlib.pyplot as plt
import numpy as np

def visualize_s3c_spatial_bins():
    """
    可视化S3C的空间分档定义
    """
    fig = plt.figure(figsize=(12, 12))
    ax = fig.add_subplot(111, projection='polar')
    
    # S3C的4象限（每个90度）
    sectors = ['Direct\nFront', 'Side\nFront', 'Direct\nRear', 'Side\nRear']
    angles = [0, np.pi/2, np.pi, 3*np.pi/2, 2*np.pi]
    
    # 绘制扇区分界线
    for angle in angles:
        ax.plot([angle, angle], [0, 50], 'k-', alpha=0.3, linewidth=1)
    
    # S3C的5档距离
    distances = {
        'near_coll': (0, 4, '#ff0000'),       # 红色：危险
        'super_near': (4, 7, '#ff6600'),      # 橙色
        'very_near': (7, 10, '#ffcc00'),      # 黄色
        'near': (10, 16, '#99cc00'),          # 黄绿色
        'visible': (16, 25, '#00cc00'),       # 绿色
    }
    
    # 绘制距离环
    for label, (r_min, r_max, color) in distances.items():
        theta = np.linspace(0, 2*np.pi, 100)
        r = np.full_like(theta, r_max)
        ax.fill_between(theta, r_min, r_max, alpha=0.2, color=color, label=f'{label} ({r_min}-{r_max}m)')
        ax.plot(theta, r, color=color, linewidth=2)
    
    # 标注扇区
    for i, label in enumerate(sectors):
        angle = (angles[i] + angles[i+1]) / 2
        ax.text(angle, 55, label, ha='center', va='center', fontsize=12, fontweight='bold')
    
    # 设置
    ax.set_theta_zero_location('N')  # 0度在上方（前方）
    ax.set_theta_direction(-1)       # 顺时针
    ax.set_ylim(0, 60)
    ax.set_title('S3C Spatial Binning (4 Angular Sectors × 5 Distance Bins)', 
                 fontsize=14, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1))
    
    plt.tight_layout()
    plt.savefig('s3c_spatial_bins.png', dpi=150, bbox_inches='tight')
    print("Saved to s3c_spatial_bins.png")

if __name__ == '__main__':
    visualize_s3c_spatial_bins()
```

---

## 📖 六、学习路径总结

### 阶段1：理解S3C理论（已完成 ✓）
- S3C的距离分档：5档
- S3C的角度分档：4象限
- S3C的可视化方法：3种

### 阶段2：运行S3C官方代码
```bash
cd e:/Project/ADVTEST/文献/s3c-main
source env.sh
source study_data/generate_figures.sh
```

### 阶段3：适配到我们的项目
1. 统一距离分档（选择5档或保持7档）
2. 实现聚类分布可视化
3. 实现覆盖率统计和对比
4. （可选）实现决策树分析

### 阶段4：PPT准备
- 展示S3C空间分档概念图
- 展示我们的聚类分布图
- 展示覆盖率统计结果
- 对比传统方法 vs S3C方法

---

## 🎯 七、关键要点

### S3C的核心创新
1. **空间离散化**：连续空间 → 离散bins
2. **覆盖率量化**：可以统计"哪些空间配置被测试了"
3. **引导式生成**：优先为低覆盖区域生成测试

### 我们的实现优势
- 基于NuScenes真实数据
- 更细粒度的距离分档（7档 vs 5档）
- 集成了地图信息（车道、路口）
- 支持多种可视化方式（BEV + 马赛克）

---

**学习完成！现在可以为老师准备PPT了！** 🎉
