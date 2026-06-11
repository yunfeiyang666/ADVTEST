# S3C可视化脚本使用指南

## 📁 已创建的脚本

### 1. 聚类分布可视化
**文件：** `vis_s3c_cluster_distribution.py`  
**功能：** 展示场景图如何被S3C聚类成等价类

### 2. 空间分档概念图
**文件：** `vis_s3c_spatial_bins.py`  
**功能：** 展示S3C的空间分档定义（4象限×5距离档）

---

## 🚀 快速运行

### 方法1：生成聚类分布图
```bash
# 切换到项目目录
cd e:/Project/ADVTEST

# 激活虚拟环境
.venv310\Scripts\activate

# 运行脚本
python scripts/vis_s3c_cluster_distribution.py \
    --jsonl data/nuscenes_scene_graph_mini_v2_s3c_enhanced.jsonl \
    --out_dir output/s3c_visualization
```

**输出：**
- `output/s3c_visualization/s3c_cluster_distribution.png`
- 控制台统计信息

---

### 方法2：生成空间分档概念图
```bash
# 生成两种风格（极坐标 + 笛卡尔坐标）
python scripts/vis_s3c_spatial_bins.py \
    --out_dir output/s3c_visualization \
    --style both
```

**输出：**
- `output/s3c_visualization/s3c_spatial_bins_polar.png` (极坐标)
- `output/s3c_visualization/s3c_spatial_bins_cartesian.png` (BEV风格)

---

### 方法3：一键生成所有图表
```bash
# 创建输出目录
mkdir output\s3c_visualization

# 生成聚类分布图
python scripts/vis_s3c_cluster_distribution.py ^
    --jsonl data/nuscenes_scene_graph_mini_v2_s3c_enhanced.jsonl ^
    --out_dir output/s3c_visualization

# 生成空间分档图
python scripts/vis_s3c_spatial_bins.py ^
    --out_dir output/s3c_visualization ^
    --style both

echo "All S3C visualizations generated!"
```

---

## 📊 生成的图表说明

### 1. 聚类分布图 (Cluster Distribution)
```
用途：展示S3C如何将场景聚类
内容：
- 蓝色散点：每个聚类包含多少图像
- 红色曲线：累积覆盖的图像数量
- 标注：最大聚类、前10聚类、单例聚类

适用场景：
✅ 论文图表
✅ PPT讲解
✅ 覆盖率分析
```

### 2. 空间分档概念图 - 极坐标 (Polar)
```
用途：展示S3C的空间划分方式
内容：
- 4个扇区：Direct Front/Side Front/Direct Rear/Side Rear
- 5个距离环：near_coll/super_near/very_near/near/visible
- 颜色编码：从红色（危险）到蓝色（安全）

适用场景：
✅ 概念讲解
✅ PPT首页
✅ 空间分档定义
```

### 3. 空间分档概念图 - 笛卡尔坐标 (Cartesian)
```
用途：BEV风格展示S3C分档
内容：
- 同心圆表示距离档
- 十字线表示4象限
- Ego车在中心

适用场景：
✅ 与BEV场景图对比
✅ 更直观的空间理解
```

---

## 🎯 预期输出示例

### 聚类分布图统计
```
Total scenes: 404
Total clusters: 187

Cluster Statistics:
  Largest cluster: 45 images (11.1%)
  Top 10 clusters: 156 images (38.6%)
  Non-singleton clusters: 89 (47.6%)
  Singleton clusters: 98 (52.4%)
```

### 空间分档定义
```
Distance Bins:
  near_coll:   0-4m   (接近碰撞)
  super_near:  4-7m   (超近)
  very_near:   7-10m  (很近)
  near:        10-16m (近)
  visible:     16-25m (可见)

Angular Bins:
  Direct Front: 315°-45°  (90度范围)
  Side Front:   45°-135°  (90度范围)
  Direct Rear:  135°-225° (90度范围)
  Side Rear:    225°-315° (90度范围)
```

---

## 🔧 参数说明

### vis_s3c_cluster_distribution.py
```
--jsonl      场景图JSONL文件路径 (必需)
--out_dir    输出目录 (默认: ./output)
```

### vis_s3c_spatial_bins.py
```
--out_dir    输出目录 (默认: ./output)
--style      可视化风格 (polar/cartesian/both)
             - polar: 极坐标图
             - cartesian: 笛卡尔坐标图
             - both: 两种都生成 (默认)
```

---

## 📖 用于PPT的建议

### 第1页：S3C空间分档概念
```
标题：S3C空间语义覆盖率
图片：s3c_spatial_bins_polar.png

要点：
- 4个角度象限
- 5个距离档位
- 离散化策略
```

### 第2页：聚类效果展示
```
标题：场景图聚类分布
图片：s3c_cluster_distribution.png

要点：
- 总聚类数：187
- 最大聚类占比：11.1%
- 长尾分布特征
```

### 第3页：空间分档细节
```
标题：BEV视角的S3C分档
图片：s3c_spatial_bins_cartesian.png

要点：
- 与BEV场景图的关系
- 如何从坐标映射到bins
- 实际应用场景
```

---

## ❓ 常见问题

### Q1: 为什么我的聚类数量很少？
A: 可能是场景图文件中的`s3c_angular`和`s3c_distance`字段缺失。
   检查场景图是否使用了`build_nuscenes_scene_graph.py`生成。

### Q2: 图片分辨率不够清晰？
A: 修改代码中的`dpi`参数：
   ```python
   plt.savefig(output_path, dpi=300, bbox_inches='tight')  # 原本150
   ```

### Q3: 如何修改距离分档？
A: 修改`vis_s3c_spatial_bins.py`中的`distances`字典：
   ```python
   distances = {
       'near_coll': (0, 4, '#d62728'),
       # 添加或修改距离档位
   }
   ```

---

## 🎓 学习路径

1. **理解S3C理论** (已完成 ✓)
   - 阅读：`docs/S3C可视化学习笔记.md`
   - 理解：4象限×5距离档

2. **运行可视化脚本** (当前步骤)
   - 生成空间分档概念图
   - 生成聚类分布图

3. **分析结果**
   - 统计聚类数量
   - 识别长尾分布
   - 对比覆盖率

4. **准备PPT**
   - 使用生成的图表
   - 结合统计数据
   - 讲解S3C优势

---

**准备完成！可以开始生成可视化了！** 🚀
