# S3C官方代码索引 - 已添加的实际代码示例

## 📚 总览

已为汇报文档添加S3C官方仓库的实际代码示例，增强学术严谨性和可信度。

---

## 🔍 已添加的代码示例清单

### **1. 图同构检测核心代码**

**文件：** `utils/asg_compare.py` (第1-46行)

**功能：** S3C聚类的核心 - 判断两个场景图是否同构

**代码：**
```python
import rustworkx as rx

def remove_ids(label):
    """移除标签中的ID号，保留类型（实现抽象化）"""
    if label is None:
        return None
    if hasattr(label, 'name'):
        under_index = label.name.rfind('_')
        if under_index == -1:
            return label.name
        else:
            return label.name[:under_index]
    return label

def compare_asgs(asg1, asg2):
    """比较两个抽象场景图是否同构"""
    return rx.digraph_is_isomorphic(
        asg1, asg2, 
        id_order=False,
        node_matcher=get_hierarchy_check(),
        edge_matcher=get_hierarchy_check()
    )
```

**关键技术：**
- `rustworkx.digraph_is_isomorphic()` - Rust实现的高性能图同构检测
- `node_matcher` - 节点语义匹配函数
- `edge_matcher` - 边语义匹配函数
- `remove_ids()` - 实现论文Section 3.2.2的抽象化操作

**对应论文：** Section 3.2.3 (Abstraction Clustering)

**使用位置：**
- ✅ S3C理论标准答案 - 问题1（描述语言）
- ✅ S3C理论标准答案 - 问题3（查询能力）

---

### **2. 聚类算法实现代码**

**文件：** `utils/dataset.py` (第426-449行)

**功能：** 高效聚类算法 - 两阶段优化

**代码：**
```python
def _gen_clusters(self, threads=1, max_per_thread=512):
    """生成场景图聚类"""
    logging.info('Generating clusters for dataset using %d threads' % threads)
    self._has_clusters = True
    
    # 阶段1：按图元数据（节点数+边数）进行粗粒度分组
    # 这一步避免了所有图两两比较的O(n²)复杂度
    logging.info('Performing initial size indexing to speed up clustering')
    for image_file in tqdm(self._image_files):
        metadata = get_sg_metadata(self._sg_files[image_file])
        self._index_sg_metadata(metadata, image_file)
    
    # 阶段2：在每个粗粒度组内进行精确的图同构检测
    logging.info('Performing clustering')
    sorted_sizes = sorted(self._graph_metadata_groups.keys())
    for size in tqdm(sorted_sizes):
        group = self._graph_metadata_groups[size]
        if len(group) == 1:
            # 单个图直接作为独立聚类
            self._clusters[group[0]] = group
        else:
            # 使用图同构检测进行精确聚类
            refined_clusters = naive_clustering(group)
            for cluster in refined_clusters:
                self._clusters[cluster[0]] = cluster
```

**算法优化：**
1. **粗粒度过滤**：先按(节点数, 边数)分组
2. **精确检测**：组内再用图同构检测
3. **并行化**：支持多线程处理

**复杂度分析：**
```
朴素算法：O(n²) × 图同构复杂度
优化算法：O(m × k²) × 图同构复杂度
其中 m = 元数据组数，k = 每组平均大小，通常 k << n
```

**对应论文：** approach/README.md - `efficient_clustering()`

**使用位置：**
- ✅ S3C理论标准答案 - 问题3（查询能力）

---

### **3. 可视化生成代码**

**文件：** `carla/cluster_figure_generator.py` (第34-82行)

**功能：** 生成论文Figure 3的聚类分布图

**代码：**
```python
import matplotlib.pyplot as plt
from utils.dataset import Dataset

def cluster_figure_generator(arg_string):
    """生成S3C论文Figure 3 - 聚类分布图"""
    args = custom_argparse(arg_string)
    output_path = args.output_path/''
    os.makedirs(output_path, exist_ok=True)
    
    datasets = {}
    x_vals = {}      # 累积覆盖
    box_vals = {}    # 每个聚类的大小
    
    # 加载聚类数据
    for dataset_file in glob.glob(str(args.input_path/'*.json')):
        graph_type = extract_graph_type(dataset_file)
        datasets[graph_type] = Dataset.load_from_file(dataset_file, '', '')
        
        cumulative = []
        count = 0
        box_vals[graph_type] = []
        
        # 统计每个聚类的大小和累积覆盖
        for cluster_key in datasets[graph_type]._sorted_cluster_keys:
            cluster = datasets[graph_type]._clusters[cluster_key]
            count += len(cluster)
            cumulative.append(count)
            box_vals[graph_type].append(len(cluster))
        
        x_vals[graph_type] = cumulative
    
    # 生成双Y轴图
    for graph_type in graphs_to_show:
        fig = plt.figure()
        ax1 = fig.gca()
        ax2 = ax1.twinx()
        
        # 左轴：聚类大小（蓝色散点）
        vals = box_vals[graph_type]
        ax1.scatter(range(len(vals)), vals, 
                   color='tab:blue', 
                   label='Images in Class (left)')
        ax1.set_ylabel('Number of Images in Class', color='tab:blue')
        
        # 右轴：累积覆盖（红色曲线）
        vals = x_vals[graph_type]
        ax2.plot(range(len(vals)), vals, 
                color='tab:red',
                label='Cumulative Images Covered (right)')
        ax2.set_ylabel('Cumulative Images Covered', color='tab:red')
        
        # 标注单例聚类分界线
        singleton_index = find_singleton_boundary(box_vals[graph_type])
        ax2.hlines(vals[singleton_index], singleton_index, len(vals), 
                  color='k', linestyles='--')
        ax2.text(singleton_index, vals[singleton_index],
                f'Remaining {len(vals)-singleton_index} Images in Singleton Classes')
        
        fig.suptitle(f'{label_map[graph_type]} Equivalence Class Partitions')
        fig.savefig(f'{output_path}/cluster_viz_{graph_type}.png')
```

**可视化特点：**
- **双Y轴设计**：同时显示聚类大小和累积覆盖
- **自动标注**：识别并标注单例聚类分界线
- **颜色编码**：蓝色=聚类大小，红色=累积覆盖

**输出对应：** 论文Figure 3

**使用位置：**
- ✅ S3C理论标准答案 - 问题4（可视化工具）
- ✅ PPT Slide 5（可视化重点）

---

## 📊 代码与论文的对应关系

| 代码文件 | 论文章节 | 关键函数 | 功能 |
|---------|---------|---------|------|
| `utils/asg_compare.py` | Section 3.2.3 | `compare_asgs()` | 图同构检测 |
| `utils/dataset.py` | Section 3.2.3 | `_gen_clusters()` | 聚类算法 |
| `carla/cluster_figure_generator.py` | Figure 3 | `cluster_figure_generator()` | 可视化生成 |
| `approach/README.md` | Section 3.2 | `get_scene_graph()` | 伪代码定义 |

---

## 🔑 关键技术点总结

### **1. 抽象化实现**
```python
# 论文：Section 3.2.2 - Abstraction
# 代码：utils/asg_compare.py - remove_ids()

原理：移除ID，保留类型
例子：car_2 → car
目的：使得相似场景被识别为同构
```

### **2. 图同构检测**
```python
# 论文：Section 3.2.3 - Abstraction Clustering
# 代码：utils/asg_compare.py - compare_asgs()

库：rustworkx (Rust实现，高性能)
算法：VF2算法（图同构经典算法）
复杂度：指数级（但实际场景图较小）
```

### **3. 高效聚类**
```python
# 论文：approach/README.md - efficient_clustering()
# 代码：utils/dataset.py - _gen_clusters()

优化策略：
1. 粗粒度预过滤（按节点数+边数）
2. 精确聚类（图同构检测）
3. 并行化处理（多线程）
```

### **4. 双Y轴可视化**
```python
# 论文：Figure 3
# 代码：carla/cluster_figure_generator.py

设计理念：
- 左Y轴（蓝色）：聚类大小 → 展示分布
- 右Y轴（红色）：累积覆盖 → 展示覆盖率
- 虚线标注：单例分界 → 识别长尾
```

---

## 💡 如何在汇报中使用这些代码

### **场景1：老师问"你怎么实现的聚类？"**

**回答：**
> "我们参考了S3C官方仓库的实现。核心是utils/asg_compare.py中的compare_asgs函数，
> 它使用rustworkx库的digraph_is_isomorphic进行图同构检测。为了提高效率，
> 我们采用了两阶段聚类：先按图的元数据粗过滤，再用图同构精确聚类。
> 这个优化策略在approach/README.md的efficient_clustering伪代码中有详细说明。"

**展示代码片段：**
```python
# 来自S3C官方代码
def compare_asgs(asg1, asg2):
    return rx.digraph_is_isomorphic(
        asg1, asg2, 
        node_matcher=get_hierarchy_check()
    )
```

---

### **场景2：老师问"你的可视化是怎么生成的？"**

**回答：**
> "我们的聚类分布图对应S3C论文的Figure 3。参考了官方的cluster_figure_generator.py，
> 采用双Y轴设计：左轴显示每个聚类的大小，右轴显示累积覆盖的场景数。
> 关键是自动标注单例聚类的分界线，这样能直观看出长尾分布。"

**展示代码片段：**
```python
# 双Y轴设计（来自S3C官方代码）
ax1.scatter(range(len(vals)), vals, color='blue')  # 聚类大小
ax2.plot(range(len(cumulative)), cumulative, color='red')  # 累积覆盖
```

---

### **场景3：老师问"抽象化是什么意思？"**

**回答：**
> "抽象化是S3C论文Section 3.2.2的核心概念。官方代码在utils/asg_compare.py的remove_ids
> 函数中实现了这个功能：移除对象的具体ID，只保留类型。比如把car_2和car_3都抽象成car。
> 这样做的目的是让相似的场景能够被识别为同构，从而正确聚类。"

**展示代码片段：**
```python
# 抽象化实现（来自S3C官方代码）
def remove_ids(label):
    # car_2 → car
    under_index = label.name.rfind('_')
    return label.name[:under_index] if under_index > 0 else label.name
```

---

## ✅ 代码引用的学术价值

### **增强可信度**
```
✓ 不是自己胡乱实现，而是遵循论文方法
✓ 有官方代码作为参考和对比
✓ 技术细节可追溯、可验证
```

### **展示理解深度**
```
✓ 不仅看懂了论文，还看懂了代码
✓ 能够解释实现细节（如两阶段聚类）
✓ 理解了优化策略（如元数据预过滤）
```

### **便于回答问题**
```
✓ 老师问"怎么做的"→ 指向官方代码
✓ 老师问"为什么这样"→ 引用论文章节
✓ 老师问"有什么优化"→ 解释两阶段策略
```

---

## 📋 汇报前检查清单

代码相关：
- [ ] 能解释图同构检测的作用
- [ ] 能说出使用的库（rustworkx）
- [ ] 能解释两阶段聚类的优化思路
- [ ] 能说出代码文件的具体位置
- [ ] 准备好了关键代码片段（截图或打印）

论文对应：
- [ ] 知道每段代码对应论文哪个章节
- [ ] 能引用approach/README.md的伪代码
- [ ] 理解抽象化（Section 3.2.2）
- [ ] 理解聚类（Section 3.2.3）

---

## 🎯 总结

### **已添加的代码**
1. ✅ 图同构检测（43行核心代码）
2. ✅ 聚类算法实现（24行关键逻辑）
3. ✅ 可视化生成（60行完整实现）

### **覆盖的论文章节**
1. ✅ Section 3.2.2 - Abstraction
2. ✅ Section 3.2.3 - Clustering
3. ✅ Figure 3 - Cluster Distribution

### **代码的价值**
1. ✅ 证明我们遵循了论文方法
2. ✅ 展示了对实现细节的理解
3. ✅ 便于回答老师的技术问题

---

**总结：所有关键代码已添加完毕，可作为汇报的技术支撑！** 🚀
