# NuScenes 场景图（Scene Graph）v2 生成与应用指南

本指南说明从原始 nuScenes 标注与自车姿态出发，如何严格几何计算并构建“标准答案”场景图，以及如何用于 VLM 问答（SpatialQA / MetaVQA 风格）、可视化与覆盖率分析。

- 数据根：`data/nuscenes/`
- 主要脚本（scripts/）：
  - `build_nuscenes_scene_graph.py`（核心：生成 SG v2）
  - `add_visibility_to_sg.py`（相机可见性 + 2D 投影框）
  - `vis_bev_scene_graph.py`（BEV 俯视图渲染）
  - `render_mosaic_from_sg.py`（六相机马赛克渲染）
  - `gen_qa_from_sg.py`（从 SG 生成 QA）
  - `coverage_from_sg.py`（覆盖率统计）

---

## 1. 关键概念

- 坐标系
  - 自车（ego）坐标系：x 前、y 左、z 上。全部“前/后/左/右、方位角、扇区、距离”都在此系计算。
  - 全球→自车：`p_e = R_ge^T (p_w - t_ge)`，来自当帧 `ego_pose` 的旋转/平移。
- 节点（SceneParticipant）
  - ego 与所有已标注对象。包含位姿、速度、尺寸、地图挂接、属性（moving/standing/...）、扇区/距离分档。
- 边（agent-agent）
  - 几何：距离、方位、前后/左右、相对速度、TTC。
  - 语义：`relation_type ∈ {longitudinal, lateral, intersecting}`；`same_lane`、`adjacent_lane`。
- 时间链
  - 每帧（Scene）在根级记录 `prev_sample_token/next_sample_token`。

---

## 2. 生成流程

1) 选参考帧与姿态
- 以 `LIDAR_TOP` 的时间/姿态作为该帧参考；从 `ego_pose` 取 `(R_ge, t_ge)`。

2) 生成节点
- 取每个 `sample_annotation` 的 `translation/rotation/size`（全局），变换到自车系，计算 8 角点与相对速度。
- 地图挂接（NuScenesMap）：`on_lane_id / on_layer(lane|lane_connector)`，`in_intersection=True` 表示连接段（路口）。
- 属性解析：`moving/standing/stopped/parked/with_rider/without_rider`。
- 扇区/距离分档：`sector8`（front 等 8 区）与 `distance ∈ {0-2,2-10,10-30,30+}`。

3) 生成边
- 半径 60m 内两两建边（含 ego）。
- 计算距离/方位/前后/左右与 TTC（沿 LOS；闭合速>0.5m/s 且距离>0.5m）。
- 语义关系：若任一端在 `lane_connector` → `intersecting`；否则按与 x 轴夹角判 `longitudinal/lateral`。
- 车道关系：`same_lane`（同 token）；`adjacent_lane` 近似（|y|<5m 且 |x|<20m）。

4) 时间链与序列化
- 根级加入 `prev_sample_token/next_sample_token`；每帧一行 JSON（JSONL）。

5) 可选：相机可见性
- 对六相机，把 3D 角点从自车系投到传感器，再用内参投影到 2D，统计落在图内的角点数（≥2 视为可见），并给出 `bbox2d/center_uv/depth`。

---

## 3. 输出字段（精简）

- 根：`sample_token, timestamp, prev_sample_token, next_sample_token, nodes[], edges[]`
- Node：
  - `id, instance_token, category_name`
  - `pose.ego.center/yaw`，`pose.global.center`
  - `velocity.ego/global`，`size.wlh`，`corners_ego(8x3)`
  - `map.on_layer/on_lane_id/in_intersection`
  - `attributes.moving/standing/stopped/parked/with_rider/without_rider`
  - `bins.sector8`（8 扇区），`bins.distance`（very_close/close/medium/far）
  - 可选 `visibility[CAM_*].visible/bbox2d/center_uv/depth`
- Edge：
  - `from, to, distance, bearing_ego, front_of, left_of, ttc`
  - `relation_type`（longitudinal/lateral/intersecting）
  - `same_lane, adjacent_lane`

---

## 4. 一键复现（mini）

在项目根 `e:\Project\ADVTEST`：

- 生成 v2（mini 全量）
```powershell
python .\scripts\build_nuscenes_scene_graph.py --dataroot .\data\nuscenes --version v1.0-mini --out_path .\data\nuscenes_scene_graph_mini_v2_all.jsonl
```

- 叠加相机可见性（可选）
```powershell
python .\scripts\add_visibility_to_sg.py --dataroot .\data\nuscenes --version v1.0-mini \
  --jsonl_in .\data\nuscenes_scene_graph_mini_v2_all.jsonl \
  --jsonl_out .\data\nuscenes_scene_graph_mini_v2_vis.jsonl --max_frames 404
```

- 俯视图渲染（24 帧示例）
```powershell
python .\scripts\vis_bev_scene_graph.py --jsonl .\data\nuscenes_scene_graph_mini_v2_all.jsonl \
  --out_dir .\data\sg_bev_mini_v2_all --max_frames 24 --only_ego_edges --draw_vel
```

- 六相机马赛克渲染（24 帧示例）
```powershell
python .\scripts\render_mosaic_from_sg.py --dataroot .\data\nuscenes --version v1.0-mini \
  --jsonl .\data\nuscenes_scene_graph_mini_v2_vis.jsonl --out_dir .\data\sg_mosaic_mini_v2 --max_frames 24
```

- 从 SG 生成 QA（全部404帧）
```powershell
python .\scripts\gen_qa_from_sg.py --jsonl .\data\nuscenes_scene_graph_mini_v2_all.jsonl \
  --out_path .\data\qa_mini_v2.jsonl --max_frames 404 --ttc_threshold 2.0
```

- 覆盖率统计
```powershell
python .\scripts\coverage_from_sg.py --jsonl .\data\nuscenes_scene_graph_mini_v2_vis.jsonl \
  --out_dir .\data\coverage_mini_v2
```

---

## 5. 结果文件（本仓库已生成）
- `data/nuscenes_scene_graph_mini_v2_all.jsonl`（mini 全量 SG v2）
- `data/nuscenes_scene_graph_mini_v2_vis.jsonl`（叠加相机可见性）
- `data/qa_mini_v2.jsonl`（21829 条 QA）
- `data/sg_bev_mini_v2_all/`（BEV PNG，24 帧）
- `data/sg_mosaic_mini_v2/`（六相机马赛克 JPG，24 帧）
- `data/coverage_mini_v2/*.csv, overview.json`（覆盖率报表）

---

## 6. 与论文/基准的对齐
- SpatialQA/NuScenes-QA：扇区/距离分档/前后左右/最近对象/碰撞（TTC）→ 已覆盖。
- Traffic Scene Graphs：`longitudinal/lateral/intersecting` 关系 → 已输出。
- nuScenes Knowledge Graph：代理-地图关系与时间链 → 已输出 `on_lane_id/in_intersection/prev/next`。

---

## 7. 已知限制与改进路线
- `adjacent_lane` 目前为几何近似；可根据 `NuScenesMap.connectivity` 做严格邻接判定与优先权（路口）。
- TTC 为 LOS 近似，适合短时 Embodied 判断；如需控制输入预测，可引入形体/制动模型。
- 可见性未做 Z-buffer 遮挡，现阶段以角点入画统计近似，可进一步精化。
- 支持导出三元组（RDF/Neo4j）或 Parquet 以便大规模检索与计算。

---

## 8. 训练集（trainval）扩展
将 `--version v1.0-trainval` 并更换输出文件名即可，文件会明显更大，建议先 mini 验证后再全量。

---

## 9. 小词典
- bearing（方位角）：自车系内，从 x 轴（前）逆时针到目标向量的角度（rad）。
- sector8：按方位角分的8个扇区（front 等）。
- same_lane/adjacent_lane：是否同车道/邻接车道（近似判定）。
- TTC：Time-To-Collision，沿两点连线方向的距离/闭合速度。
