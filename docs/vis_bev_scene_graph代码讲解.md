# vis_bev_scene_graph.py 代码详细讲解

## 📋 **脚本概览**

### 功能
从场景图JSONL文件生成鸟瞰图（BEV - Bird's Eye View）可视化图像

### 核心能力
```
输入: 场景图JSONL文件（每行一个帧）
处理: 解析节点、边、坐标、尺寸、速度
输出: BEV PNG图像（俯视图）

可视化元素:
├─ 对象框（带类别颜色）
├─ 自车（ego vehicle）
├─ 速度箭头（可选）
├─ 对象间关系边
└─ 图例和坐标轴
```

---

## 🎨 **一、配置与常量定义**

### 1.1 导入依赖
```python
import os
import json
import argparse
import math
from typing import Tuple, List

import numpy as np
import matplotlib
matplotlib.use('Agg')  # 非交互式后端，适合批量渲染
import matplotlib.pyplot as plt
```

**关键点**:
- `matplotlib.use('Agg')`: 使用非交互式后端
  - 不需要显示窗口
  - 适合服务器环境和批量处理
  - 避免内存泄漏

---

### 1.2 类别颜色映射
```python
CAT_COLORS = {
    'vehicle': '#e41a1c',        # 红色 - 车辆
    'human': '#377eb8',          # 蓝色 - 行人
    'animal': '#4daf4a',         # 绿色 - 动物
    'movable_object': '#984ea3', # 紫色 - 可移动物体
    'static_object': '#ff7f00',  # 橙色 - 静态物体
    'flat': '#a65628',           # 棕色 - 平面（路面）
    'vehicle.ego': '#1f78b4'     # 深蓝色 - 自车
}
```

**设计思路**:
- 使用ColorBrewer配色方案（专业、可区分）
- 每个大类有独特颜色
- ego车辆特殊标识（深蓝色）

---

### 1.3 颜色查找函数
```python
def _cat_color(category_name: str) -> str:
    """
    根据类别名称返回对应颜色
    
    参数:
        category_name: 例如 'vehicle.car', 'human.pedestrian'
    
    返回:
        十六进制颜色代码
    
    逻辑:
        1. 如果是ego → 返回专用颜色
        2. 否则提取前缀（.之前的部分）
        3. 在颜色表中查找，找不到返回灰色
    """
    if category_name == 'vehicle.ego':
        return CAT_COLORS['vehicle.ego']
    
    # 提取类别前缀: 'vehicle.car' → 'vehicle'
    prefix = category_name.split('.')[0] if '.' in category_name else category_name
    
    return CAT_COLORS.get(prefix, '#555555')  # 默认灰色
```

**示例**:
```python
_cat_color('vehicle.car')        # → '#e41a1c' (红色)
_cat_color('human.pedestrian')   # → '#377eb8' (蓝色)
_cat_color('vehicle.ego')        # → '#1f78b4' (深蓝色)
_cat_color('unknown.object')     # → '#555555' (灰色)
```

---

## 📐 **二、几何计算函数**

### 2.1 计算2D框的四个角点
```python
def box2d_corners(center: np.ndarray, yaw: float, w: float, l: float) -> np.ndarray:
    """
    计算2D矩形框的四个角点坐标（BEV视图）
    
    参数:
        center: (x, y) - 框中心在ego坐标系下的位置
        yaw:    弧度 - 车头朝向角度（相对于x轴）
        w:      宽度（沿y轴方向，NuScenes定义）
        l:      长度（沿x轴方向，NuScenes定义）
    
    返回:
        shape (4, 2) - 四个角点的(x, y)坐标
    
    NuScenes坐标系:
        x轴: 前方（forward）
        y轴: 左侧（left）
        z轴: 上方（up）
    """
    # 半长和半宽
    dx = l / 2.0  # x方向半长
    dy = w / 2.0  # y方向半宽
    
    # 在局部坐标系（车体坐标系）中的四个角点
    # 顺序: 右前、右后、左后、左前（逆时针）
    pts = np.array([
        [ dx,  dy],  # 右前角
        [ dx, -dy],  # 右后角
        [-dx, -dy],  # 左后角
        [-dx,  dy]   # 左前角
    ], dtype=float)
    
    # 构造旋转矩阵
    c, s = math.cos(yaw), math.sin(yaw)
    R = np.array([[c, -s], 
                  [s,  c]], dtype=float)
    
    # 旋转 + 平移
    # 1. pts @ R.T: 将局部坐标系的点旋转到全局坐标系
    # 2. + center: 平移到正确位置
    return (pts @ R.T) + center[None, :]
```

**数学原理**:
```
旋转矩阵（2D）:
R(θ) = [cos(θ)  -sin(θ)]
       [sin(θ)   cos(θ)]

点的变换:
P_global = R(yaw) * P_local + center

示例:
center = [10, 5], yaw = π/4 (45°), w = 2, l = 4

局部坐标（未旋转）:
[ 2,  1]  右前
[ 2, -1]  右后
[-2, -1]  左后
[-2,  1]  左前

旋转后 + 平移:
→ 四个全局坐标点
```

**可视化**:
```
    y (left)
    ↑
    │    ┌────┐
    │    │ →  │  (车头朝向)
    │    └────┘
    │
    └──────────→ x (forward)
```

---

### 2.2 绘制2D框
```python
def draw_box(ax, corners2d: np.ndarray, color: str, 
             lw: float = 1.0, fill: bool = False, alpha: float = 0.2):
    """
    在matplotlib轴上绘制2D矩形框
    
    参数:
        ax:        matplotlib轴对象
        corners2d: shape (4, 2) - 四个角点坐标
        color:     颜色代码
        lw:        线宽
        fill:      是否填充
        alpha:     填充透明度
    """
    # 将第一个点加到末尾，形成闭合多边形
    poly = np.vstack([corners2d, corners2d[0]])
    
    # 绘制边框
    ax.plot(poly[:, 0], poly[:, 1], color=color, linewidth=lw)
    
    # 可选：填充内部
    if fill:
        ax.fill(poly[:, 0], poly[:, 1], color=color, alpha=alpha)
```

**效果**:
```
不填充 (fill=False):
    ┌────┐
    │    │  只有边框
    └────┘

填充 (fill=True, alpha=0.2):
    ┌────┐
    │████│  半透明填充
    └────┘
```

---

### 2.3 绘制速度箭头
```python
def draw_arrow(ax, start: np.ndarray, vec: np.ndarray, 
               color: str, scale: float = 1.0, width: float = 0.003):
    """
    绘制速度矢量箭头
    
    参数:
        ax:    matplotlib轴对象
        start: 箭头起点 (x, y)
        vec:   速度矢量 (vx, vy) m/s
        color: 颜色
        scale: 缩放因子（调整箭头长度）
        width: 箭头宽度
    
    箭头方向 = 速度方向
    箭头长度 = 速度大小 × scale
    """
    ax.arrow(
        start[0], start[1],           # 起点
        vec[0] * scale, vec[1] * scale,  # 方向和长度
        head_width=0.8,               # 箭头宽度
        head_length=1.2,              # 箭头长度
        fc=color, ec=color,           # 填充和边框颜色
        length_includes_head=True,    # 长度包含箭头
        lw=0.5                        # 线宽
    )
```

**可视化**:
```
速度 = (3, 2) m/s

        ↗  箭头指向速度方向
       /
      /
     •  对象中心
```

---

## 🖼️ **三、核心绘图函数**

### 3.1 绘制单帧场景
```python
def plot_frame(frame: dict, out_path: str, 
               xlim: Tuple[float, float], 
               ylim: Tuple[float, float],
               show_edges_from_ego: bool, 
               k_nearest: int, 
               draw_vel: bool):
    """
    渲染单个场景帧的BEV图像
    
    参数:
        frame:              场景图JSON对象（一帧）
        out_path:           输出图像路径
        xlim:               X轴范围 (xmin, xmax) 米
        ylim:               Y轴范围 (ymin, ymax) 米
        show_edges_from_ego: 是否只显示与ego连接的边
        k_nearest:          显示最近k个对象的边
        draw_vel:           是否绘制速度箭头
    
    场景图结构:
    {
        'sample_token': 'xxx',
        'timestamp': 1234567890,
        'nodes': [
            {
                'id': 'ego' or 'obj_xxx',
                'category_name': 'vehicle.car',
                'pose': {
                    'ego': {
                        'center': [x, y, z],
                        'yaw': angle_rad
                    }
                },
                'size': {'wlh': [w, l, h]},
                'velocity': {'ego': [vx, vy, vz]}
            },
            ...
        ],
        'edges': [
            {'from': 'ego', 'to': 'obj_1', 'relation': 'lateral'},
            ...
        ]
    }
    """
```

---

#### 3.1.1 初始化画布
```python
    # 创建8x8英寸的方形画布
    fig, ax = plt.subplots(figsize=(8, 8))
    
    # 设置等比例坐标轴（避免变形）
    ax.set_aspect('equal', adjustable='box')
    
    # 设置坐标轴范围
    ax.set_xlim(*xlim)  # 例如 (-20, 80) → 车前80m，车后20m
    ax.set_ylim(*ylim)  # 例如 (-40, 40) → 左右各40m
    
    # 网格线
    ax.grid(True, linestyle='--', alpha=0.3)
    
    # 坐标轴标签
    ax.set_xlabel('x (forward, m)')
    ax.set_ylabel('y (left, m)')
    
    # 标题：显示场景token和时间戳
    ax.set_title(f"sample: {frame.get('sample_token','')}  "
                 f"t: {frame.get('timestamp','')}")
```

**坐标系说明**:
```
BEV视图（俯视图）:

    y (left, 左侧)
    ↑
 40 │
    │
  0 ├─────────•──────── (ego车，原点)
    │         |
-40 │         |
    │         ↓ x (forward, 前方)
    └──────────────────→
   -20       0        80
   
可视范围:
- 车前: 0 → 80m
- 车后: 0 → -20m
- 左侧: 0 → 40m
- 右侧: 0 → -40m
```

---

#### 3.1.2 提取节点信息
```python
    nodes = frame['nodes']
    
    # 构建ID到节点的映射（快速查找）
    node_by_id = {n['id']: n for n in nodes}
    
    # 提取所有节点的中心坐标（用于绘制边）
    centers = {}
    for n in nodes:
        if n['pose']['ego']['center'] is not None:
            # 只取x, y坐标（忽略z高度）
            centers[n['id']] = np.array(
                n['pose']['ego']['center'][:2], 
                dtype=float
            )
        else:
            centers[n['id']] = np.zeros(2)  # 缺失数据用原点
```

**数据结构**:
```python
nodes = [
    {
        'id': 'ego',
        'category_name': 'vehicle.ego',
        'pose': {'ego': {'center': [0, 0, 0], 'yaw': 0}}
    },
    {
        'id': 'obj_1',
        'category_name': 'vehicle.car',
        'pose': {'ego': {'center': [10, 5, 0], 'yaw': 0.5}}
    },
    ...
]

centers = {
    'ego': array([0, 0]),
    'obj_1': array([10, 5]),
    ...
}
```

---

#### 3.1.3 绘制节点（对象）
```python
    # 遍历所有节点
    for n in nodes:
        nid = n['id']
        cat = n['category_name']
        color = _cat_color(cat)  # 获取类别颜色
        
        # 提取中心坐标
        center = np.array(
            n['pose']['ego']['center'][:2], dtype=float
        ) if n['pose']['ego']['center'] is not None else np.zeros(2)
        
        # === 特殊处理：自车（ego vehicle）===
        if cat == 'vehicle.ego':
            # 绘制固定大小的框（4m长 × 2m宽）
            c2d = box2d_corners(center, 0.0, w=2.0, l=4.0)
            draw_box(ax, c2d, color=color, lw=2.0, fill=True, alpha=0.15)
            
            # 绘制朝向箭头（指向前方）
            draw_arrow(ax, center, np.array([3.0, 0.0]), color)
        
        # === 其他对象 ===
        else:
            # 提取尺寸信息
            size = n.get('size') or {}
            wlh = size.get('wlh') if size else None  # [width, length, height]
            yaw = float(n['pose']['ego'].get('yaw', 0.0))
            
            if wlh is not None:
                # 有尺寸信息 → 绘制矩形框
                w, l = float(wlh[0]), float(wlh[1])
                box = box2d_corners(center, yaw, w=w, l=l)
                draw_box(ax, box, color=color, lw=1.2, fill=False)
            else:
                # 无尺寸信息 → 绘制圆点
                ax.plot(center[0], center[1], marker='o', 
                       color=color, markersize=3)
            
            # === 可选：绘制速度箭头 ===
            if draw_vel:
                v = np.array(n['velocity']['ego'][:2], dtype=float)
                # 只绘制有显著速度的对象（>0.05 m/s）
                if np.linalg.norm(v) > 0.05:
                    draw_arrow(ax, center, v, color=color, scale=1.0)
```

**绘制效果**:
```
Ego车（深蓝色，半透明填充）:
    ┌────┐
    │ ████│ →  (朝向箭头)
    └────┘

其他车辆（红色框，带速度箭头）:
    ┌────┐
    │    │ ↗  (速度方向)
    └────┘

行人（蓝色点或小框）:
    •  或  ┌┐
           └┘
```

---

#### 3.1.4 绘制关系边
```python
    edges = frame['edges']
    
    # === 策略1: 只显示与ego连接的边 ===
    if show_edges_from_ego:
        for e in edges:
            a, b = e['from'], e['to']
            if a == 'ego' or b == 'ego':
                p = centers[a]
                q = centers[b]
                ax.plot([p[0], q[0]], [p[1], q[1]], 
                       color='#999999', alpha=0.6, linewidth=0.8)
    
    # === 策略2: 显示最近k个对象的边 ===
    else:
        # 计算所有对象到ego的距离
        ego_c = centers.get('ego', np.zeros(2))
        others = [(nid, np.linalg.norm(c - ego_c)) 
                  for nid, c in centers.items() 
                  if nid != 'ego']
        
        # 按距离排序
        others.sort(key=lambda x: x[1])
        
        # 只保留最近k个对象
        keep = set([nid for nid, _ in others[:max(1, k_nearest)]])
        
        # 绘制与这k个对象相关的边
        for e in edges:
            a, b = e['from'], e['to']
            if a in keep or b in keep:
                p = centers[a]
                q = centers[b]
                ax.plot([p[0], q[0]], [p[1], q[1]], 
                       color='#bbbbbb', alpha=0.5, linewidth=0.6)
```

**策略对比**:
```
策略1 (only_ego_edges):
    显示所有与ego直接连接的边
    适合: 关注自车周围环境
    
    • ───── •
     ╲     ╱
      ╲   ╱
       ego
      ╱   ╲
     ╱     ╲
    • ───── •

策略2 (k_nearest=5):
    显示距离ego最近的5个对象及其所有边
    适合: 减少视觉混乱
    
    •       •  (远处，不显示)
    
    • ─── •    (近处，显示)
     ╲   ╱
      ego
```

---

#### 3.1.5 添加图例并保存
```python
    # 创建图例（显示各类别颜色）
    for k, v in CAT_COLORS.items():
        # 绘制空线条作为图例代理
        ax.plot([], [], color=v, label=k)
    
    # 显示图例（右上角，8号字体，两列）
    ax.legend(loc='upper right', fontsize=8, ncol=2)
    
    # 自动调整布局（避免标签被裁剪）
    fig.tight_layout()
    
    # 确保输出目录存在
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    
    # 保存图像（120 DPI，适合屏幕查看）
    fig.savefig(out_path, dpi=120)
    
    # 关闭图形对象（释放内存）
    plt.close(fig)
```

**图例效果**:
```
┌─────────────────┐
│ ■ vehicle       │
│ ■ human         │
│ ■ movable_object│
│ ■ static_object │
│ ■ vehicle.ego   │
└─────────────────┘
```

---

## 🚀 **四、主函数（命令行接口）**

### 4.1 参数解析
```python
def main():
    ap = argparse.ArgumentParser()
    
    # === 必需参数 ===
    ap.add_argument('--jsonl', type=str, required=True, 
                   help='Path to scene graph jsonl')
    ap.add_argument('--out_dir', type=str, required=True, 
                   help='Where to save BEV images')
    
    # === 可选参数 ===
    ap.add_argument('--max_frames', type=int, default=10, 
                   help='Render at most N frames')
    
    # X轴范围：需要2个浮点数 [xmin, xmax]
    ap.add_argument('--xlim', type=float, nargs=2, 
                   default=[-20, 80], 
                   help='x axis range (m)')
    
    # Y轴范围：需要2个浮点数 [ymin, ymax]
    ap.add_argument('--ylim', type=float, nargs=2, 
                   default=[-40, 40], 
                   help='y axis range (m)')
    
    # 布尔标志：是否只显示ego边
    ap.add_argument('--only_ego_edges', action='store_true', 
                   help='Draw only edges connected to ego')
    
    # 最近邻数量
    ap.add_argument('--k_nearest', type=int, default=30, 
                   help='When not only_ego_edges, draw edges for k nearest nodes to ego')
    
    # 布尔标志：是否绘制速度
    ap.add_argument('--draw_vel', action='store_true', 
                   help='Draw velocity arrows')
    
    args = ap.parse_args()
```

**命令行示例**:
```bash
# 基础用法
python vis_bev_scene_graph.py \
    --jsonl data/scene_graphs.jsonl \
    --out_dir output/bev

# 自定义范围和参数
python vis_bev_scene_graph.py \
    --jsonl data/scene_graphs.jsonl \
    --out_dir output/bev \
    --max_frames 20 \
    --xlim -30 100 \
    --ylim -50 50 \
    --only_ego_edges \
    --draw_vel

# 参数说明
--jsonl:          场景图文件路径
--out_dir:        输出目录
--max_frames:     最多渲染多少帧（默认10）
--xlim:           X轴范围，米（默认 -20 80）
--ylim:           Y轴范围，米（默认 -40 40）
--only_ego_edges: 只显示与ego连接的边
--k_nearest:      显示最近k个对象（默认30）
--draw_vel:       绘制速度箭头
```

---

### 4.2 批量渲染
```python
    # 创建输出目录
    os.makedirs(args.out_dir, exist_ok=True)
    
    # 打开JSONL文件（每行一个JSON对象）
    with open(args.jsonl, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            # 检查是否达到最大帧数
            if idx >= args.max_frames:
                break
            
            # 解析JSON行
            frame = json.loads(line)
            
            # 获取场景token（用于文件名）
            sample_token = frame.get('sample_token', f'{idx:06d}')
            
            # 构造输出路径
            # 格式: 000000_xxx.png, 000001_yyy.png, ...
            out_path = os.path.join(
                args.out_dir, 
                f"{idx:06d}_{sample_token}.png"
            )
            
            # 渲染并保存
            plot_frame(
                frame, 
                out_path, 
                tuple(args.xlim), 
                tuple(args.ylim), 
                args.only_ego_edges, 
                args.k_nearest, 
                args.draw_vel
            )
    
    print(f"Saved BEV images to {args.out_dir}")
```

**文件输出**:
```
output/bev/
├── 000000_ca9a282c9e77460f8360f564131a8af5.png
├── 000001_36f66b618afb41029d8e6f3c0bca5e3f.png
├── 000002_7e7e1b0e30944bd88a5d5f2c45b08f16.png
...
└── 000009_abc123def456.png
```

---

## 📊 **五、数据流程图**

### 完整处理流程
```
输入: scene_graphs.jsonl
├─ 第1行: {"sample_token": "xxx", "nodes": [...], "edges": [...]}
├─ 第2行: {"sample_token": "yyy", "nodes": [...], "edges": [...]}
└─ ...

处理:
1. 解析JSON → frame对象
2. 提取nodes和edges
3. 为每个node:
   ├─ 计算颜色
   ├─ 计算框角点
   ├─ 绘制框/点
   └─ 绘制速度箭头（可选）
4. 为每条edge:
   ├─ 检查是否应显示
   └─ 绘制连线
5. 添加图例
6. 保存PNG

输出:
output/bev/
├── 000000_xxx.png  ← BEV图像
├── 000001_yyy.png
└── ...
```

---

## 🎯 **六、关键技术点**

### 6.1 坐标系转换
```
NuScenes坐标系（右手系）:
    Z (up)
    ↑
    │    Y (left)
    │   ↗
    │  ╱
    │ ╱
    └────────→ X (forward)

BEV视图（俯视图，投影到XY平面）:
    Y
    ↑
    │
    │
    └────────→ X

转换: 直接忽略Z坐标
```

---

### 6.2 旋转变换
```python
# 2D旋转矩阵
R(θ) = [cos(θ)  -sin(θ)]
       [sin(θ)   cos(θ)]

# 应用到4个角点
corners_rotated = corners_local @ R.T

# 例子（旋转45°）:
θ = π/4
R = [0.707  -0.707]
    [0.707   0.707]

点 [1, 0] 旋转后 → [0.707, 0.707]（45°方向）
```

---

### 6.3 颜色映射策略
```
分层颜色体系:
├─ 大类（vehicle, human, etc.）→ 主颜色
└─ 子类（vehicle.car, vehicle.truck）→ 继承主颜色

优势:
├─ 一致性：同类对象颜色相同
├─ 可扩展：新子类自动继承
└─ 可区分：不同大类颜色不同
```

---

### 6.4 边过滤策略
```
问题: 
完整场景图可能有数百条边 → 视觉混乱

解决方案:
1. only_ego_edges: 只显示与ego连接的边
   └─ 适合: 关注自车周围环境
   
2. k_nearest: 只显示距离ego最近的k个对象的边
   └─ 适合: 平衡信息量和清晰度
   
3. 可扩展: 可添加其他过滤策略
   └─ 例: 只显示危险距离(<10m)的边
```

---

## 💡 **七、使用技巧**

### 7.1 调整可视范围
```bash
# 城市道路（近距离）
--xlim -10 30 --ylim -20 20

# 高速公路（远距离）
--xlim -20 100 --ylim -30 30

# 路口场景（宽视野）
--xlim -40 40 --ylim -40 40
```

---

### 7.2 优化性能
```python
# 1. 使用Agg后端（不显示窗口）
matplotlib.use('Agg')

# 2. 批量处理后关闭图形
plt.close(fig)

# 3. 限制帧数
--max_frames 100

# 4. 降低DPI（如果只用于快速预览）
fig.savefig(out_path, dpi=80)  # 默认120
```

---

### 7.3 自定义扩展
```python
# 添加新的可视化元素

# 1. 显示对象ID
ax.text(center[0], center[1], nid, fontsize=6)

# 2. 显示距离标注
dist = np.linalg.norm(center - ego_center)
ax.text(center[0], center[1]+2, f"{dist:.1f}m", fontsize=5)

# 3. 高亮危险对象
if dist < 10:  # 距离<10m
    draw_box(ax, box, color='red', lw=3.0)

# 4. 显示S3C分档
sector, distance_bin = get_s3c_bin(center)
ax.text(center[0], center[1], f"{sector}/{distance_bin}", fontsize=5)
```

---

## 📋 **八、常见问题**

### Q1: 为什么ego车总是在原点？
```
A: 场景图使用ego车坐标系
   - ego车固定在(0,0,0)
   - 所有其他对象位置相对于ego
   - 这样便于理解"车前多远"、"车左多远"
```

### Q2: 速度箭头为什么有时很短？
```
A: 箭头长度 = 速度大小 × scale
   - 低速（<1m/s）→ 短箭头
   - 静止对象（<0.05m/s）→ 不显示箭头
   - 可调整scale参数放大显示
```

### Q3: 为什么有些对象是点而不是框？
```
A: 缺少尺寸信息
   - 场景图中size.wlh字段为None
   - 降级为点标记（保证可视）
   - 通常是远处或小对象
```

### Q4: 如何只显示特定类别？
```python
# 修改代码，在绘制节点时添加过滤
for n in nodes:
    cat = n['category_name']
    # 只显示车辆和行人
    if not (cat.startswith('vehicle') or cat.startswith('human')):
        continue
    # ... 绘制代码 ...
```

---

## 🎯 **九、总结**

### 核心功能
```
✅ 从场景图生成BEV可视化
✅ 支持多种对象类别和颜色
✅ 可选速度箭头显示
✅ 灵活的边过滤策略
✅ 批量渲染支持
✅ 高度可配置
```

### 技术亮点
```
1. 几何变换
   └─ 2D旋转矩阵 + 平移

2. 颜色管理
   └─ 分层映射 + 自动回退

3. 性能优化
   └─ 非交互式后端 + 资源释放

4. 可扩展性
   └─ 易于添加新的可视化元素
```

### 应用场景
```
✅ 数据质量检查
✅ 算法调试可视化
✅ 论文/报告配图
✅ 演示和展示
✅ VQA任务的输入图像生成
```

---

**这个脚本是场景图到BEV图像转换的核心工具，为后续VLM评估提供视觉输入！** 🎨
