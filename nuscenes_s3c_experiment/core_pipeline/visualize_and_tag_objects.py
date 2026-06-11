"""
对象可视化标注工具 - 为 Visual VQA 准备

功能：
1. 在 BEV（鸟瞰图）上绘制所有对象的边界框
2. 自动为每个对象分配唯一编号（如 car1, pedestrian2）
3. 在框内标注对象类型和编号
4. 生成带标注的图像，供 Vision LLM 使用
5. 同时生成对象编号映射表（用于答案验证）

使用场景：
- Vision-Language VQA: 让 LLM 看图回答问题
- 问题示例: "What's the status of car1?" (图中已标注 car1 的位置)
- 答案可以直接引用对象编号，避免歧义
"""
import json
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.patches import FancyBboxPatch, Rectangle
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


class ObjectVisualizer:
    """对象可视化标注器"""
    
    # 对象类型颜色调色板（每种类型提供多个变体，相邻同类对象使用不同变体）
    COLOR_PALETTES = {
        'ego':        ['#FF0000'],
        'car':        ['#1f77b4', '#3399ff', '#0044aa'],
        'truck':      ['#ff7f0e', '#ffaa33', '#cc5500'],
        'bus':        ['#2ca02c', '#44cc44', '#006600'],
        'pedestrian': ['#d62728', '#ff4444', '#991111'],
        'bicycle':    ['#9467bd', '#bb88dd', '#6633aa'],
        'motorcycle': ['#8c564b', '#aa7766', '#664433'],
        'trailer':    ['#e377c2', '#ff99dd', '#bb5599'],
        'barrier':    ['#7f7f7f', '#aaaaaa', '#555555'],
    }
    # 向后兼容：默认颜色映射（取每组的第一个）
    COLORS = {k: v[0] for k, v in COLOR_PALETTES.items()}
    
    def __init__(self, scene_graph: Dict):
        """
        初始化可视化器
        
        Args:
            scene_graph: 场景图 JSON 数据
        """
        self.scene_name = scene_graph.get('scene_name', 'unknown')
        self.frame_idx = scene_graph.get('frame_idx', 0)
        
        # 解析节点
        nodes_data = scene_graph.get('objects') or scene_graph.get('nodes', [])
        self.objects = []
        
        for node in nodes_data:
            obj = {
                'unique_id': node['unique_id'],
                'type': node['type'],
                'translation': node.get('translation', {}),
                'size': node.get('size'),
                'rotation': node.get('rotation', []),
                'status': node.get('status', 'unknown'),
            }
            
            # 处理 translation 格式
            if isinstance(obj['translation'], dict):
                obj['x'] = obj['translation'].get('x', 0)
                obj['y'] = obj['translation'].get('y', 0)
            elif isinstance(obj['translation'], (list, tuple)):
                obj['x'] = obj['translation'][0]
                obj['y'] = obj['translation'][1]
            else:
                obj['x'] = 0
                obj['y'] = 0
            
            # 处理 size 格式
            if obj['size']:
                if isinstance(obj['size'], dict):
                    obj['width'] = obj['size'].get('width', 1.0)
                    obj['length'] = obj['size'].get('length', 1.0)
                elif isinstance(obj['size'], (list, tuple)):
                    obj['width'] = obj['size'][0]
                    obj['length'] = obj['size'][1]
                else:
                    obj['width'] = 1.0
                    obj['length'] = 1.0
            else:
                obj['width'] = 1.0
                obj['length'] = 1.0
            
            self.objects.append(obj)
        
        logger.info(f"加载场景: {self.scene_name} 帧{self.frame_idx}")
        logger.info(f"对象数量: {len(self.objects)}")
    
    def create_bev_with_tags(self, output_path: str, figsize: Tuple[int, int] = (12, 12),
                             range_x: Optional[Tuple[float, float]] = None,
                             range_y: Optional[Tuple[float, float]] = None,
                             show_ego_heading: bool = True,
                             auto_range: bool = True,
                             margin: float = 10.0) -> Dict:
        """
        创建带标注的 BEV 图像
        
        Args:
            output_path: 输出图像路径
            figsize: 图像尺寸
            range_x: X 轴范围（米），None 则自动计算
            range_y: Y 轴范围（米），None 则自动计算
            show_ego_heading: 是否显示 ego 朝向箭头
            auto_range: 自动根据对象位置调整范围
            margin: 自动范围时的边距（米）
        
        Returns:
            对象编号映射表 {unique_id: display_info}
        """
        # 自动计算坐标范围
        if auto_range or range_x is None or range_y is None:
            all_x = [obj['x'] for obj in self.objects]
            all_y = [obj['y'] for obj in self.objects]
            
            if not all_x or not all_y:
                range_x = (-50, 50)
                range_y = (-50, 50)
            else:
                min_x, max_x = min(all_x), max(all_x)
                min_y, max_y = min(all_y), max(all_y)
                
                range_x = (min_x - margin, max_x + margin)
                range_y = (min_y - margin, max_y + margin)
                
                logger.info(f"自动范围: X=[{min_x:.1f}, {max_x:.1f}], Y=[{min_y:.1f}, {max_y:.1f}]")
        
        fig, ax = plt.subplots(figsize=figsize)
        
        # 设置坐标系
        ax.set_xlim(range_x)
        ax.set_ylim(range_y)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_xlabel('X (meters)', fontsize=12)
        ax.set_ylabel('Y (meters)', fontsize=12)
        ax.set_title(f'Scene: {self.scene_name} Frame {self.frame_idx} - Object Tagging',
                     fontsize=14, fontweight='bold')
        
        # 只在原点可见时绘制
        if range_x[0] <= 0 <= range_x[1] and range_y[0] <= 0 <= range_y[1]:
            ax.plot(0, 0, 'k+', markersize=15, markeredgewidth=2)
            ax.text(0, -2, 'Origin', ha='center', fontsize=10, 
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
        
        # 对象编号映射
        object_map = {}
        
        # 跟踪已绘制对象的位置和颜色，用于相邻同色检测
        drawn_objects = []  # [(type, x, y, color_idx), ...]
        
        # 绘制每个对象
        for obj in self.objects:
            unique_id = obj['unique_id']
            obj_type = obj['type']
            x, y = obj['x'], obj['y']
            width, length = obj['width'], obj['length']
            
            # 选择颜色：相邻同类对象使用不同颜色变体
            color, color_idx = self._pick_color_for_object(
                obj_type, x, y, drawn_objects
            )
            drawn_objects.append((obj_type, x, y, color_idx))
            
            # 绘制边界框（简化为矩形，不考虑旋转）
            rect = Rectangle(
                (x - width/2, y - length/2),
                width, length,
                linewidth=2,
                edgecolor=color,
                facecolor=color,
                alpha=0.3 if obj_type != 'ego' else 0.5
            )
            ax.add_patch(rect)
            
            # 标注对象 ID
            label = unique_id
            fontsize = 10 if obj_type == 'ego' else 8
            fontweight = 'bold' if obj_type == 'ego' else 'normal'
            
            ax.text(x, y, label,
                   ha='center', va='center',
                   fontsize=fontsize,
                   fontweight=fontweight,
                   color='white',
                   bbox=dict(boxstyle='round,pad=0.4', 
                            facecolor=color, 
                            edgecolor='white',
                            linewidth=1.5,
                            alpha=0.9))
            
            # 记录对象信息
            object_map[unique_id] = {
                'type': obj_type,
                'position': {'x': x, 'y': y},
                'size': {'width': width, 'length': length},
                'status': obj.get('status', 'unknown'),
                'display_label': label,
                'color': color
            }
        
        # 如果有 ego，绘制朝向箭头
        if show_ego_heading:
            ego_obj = next((o for o in self.objects if o['type'] == 'ego'), None)
            if ego_obj and ego_obj['rotation']:
                ego_x, ego_y = ego_obj['x'], ego_obj['y']
                
                # 从四元数计算 yaw 角（朝向）
                rot = ego_obj['rotation']
                if isinstance(rot, (list, tuple)) and len(rot) == 4:
                    w, x, y, z = rot[0], rot[1], rot[2], rot[3]
                    # 四元数转欧拉角 yaw = atan2(2(wz + xy), 1 - 2(y^2 + z^2))
                    yaw = np.arctan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
                else:
                    yaw = 0  # 默认朝向
                
                # 计算箭头方向
                arrow_length = 8
                dx = arrow_length * np.cos(yaw)
                dy = arrow_length * np.sin(yaw)
                
                ax.arrow(ego_x, ego_y, dx, dy,
                        head_width=2.0, head_length=1.5,
                        fc='red', ec='red', linewidth=2.5,
                        alpha=0.8, zorder=10)
                
                # 标注文字位置也根据朝向调整
                text_x = ego_x + dx * 1.3
                text_y = ego_y + dy * 1.3
                ax.text(text_x, text_y, 'Ego Forward',
                       ha='center', fontsize=9, color='red', fontweight='bold',
                       bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                                edgecolor='red', alpha=0.8))
        
        # 添加图例
        legend_elements = []
        unique_types = set(o['type'] for o in self.objects)
        for obj_type in sorted(unique_types):
            if obj_type in self.COLORS:
                legend_elements.append(
                    patches.Patch(facecolor=self.COLORS[obj_type], 
                                 edgecolor='black',
                                 label=obj_type.capitalize())
                )
        
        ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
        
        # 保存图像
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"✓ BEV 图像已保存: {output_path}")
        logger.info(f"  标注对象数: {len(object_map)}")
        
        return object_map
    
    def _pick_color_for_object(self, obj_type: str, x: float, y: float,
                               drawn_objects: List[Tuple],
                               proximity_thresh: float = 15.0
                               ) -> Tuple[str, int]:
        """为对象选择颜色变体，确保相邻同类对象颜色不同
        
        Args:
            obj_type: 对象类型
            x, y: 对象在BEV中的世界坐标
            drawn_objects: 已绘制对象列表 [(type, x, y, color_idx), ...]
            proximity_thresh: 邻近判定阈值（米），默认15米
            
        Returns:
            (color_hex, color_idx)
        """
        palette = self.COLOR_PALETTES.get(obj_type, ['#cccccc'])
        if len(palette) <= 1:
            return palette[0], 0
        
        # 收集邻近同类对象已使用的颜色变体索引
        used_indices = set()
        for d_type, d_x, d_y, d_idx in drawn_objects:
            if d_type != obj_type:
                continue
            dist = np.sqrt((x - d_x)**2 + (y - d_y)**2)
            if dist < proximity_thresh:
                used_indices.add(d_idx)
        
        # 选择第一个未使用的变体
        for idx in range(len(palette)):
            if idx not in used_indices:
                return palette[idx], idx
        
        # 所有变体都被邻近对象用了，循环选择
        return palette[len(used_indices) % len(palette)], len(used_indices) % len(palette)
    
    def create_object_reference_table(self, object_map: Dict, output_path: str):
        """
        创建对象编号参考表（Markdown 格式）
        
        Args:
            object_map: 对象映射表
            output_path: 输出文件路径
        """
        lines = [
            f"# Object Reference Table",
            f"",
            f"**Scene**: {self.scene_name} Frame {self.frame_idx}",
            f"",
            f"| Object ID | Type | Position (x, y) | Size (w×l) | Status |",
            f"|-----------|------|-----------------|------------|--------|"
        ]
        
        for obj_id, info in sorted(object_map.items()):
            pos = info['position']
            size = info['size']
            lines.append(
                f"| **{obj_id}** | {info['type']} | "
                f"({pos['x']:.1f}, {pos['y']:.1f}) | "
                f"{size['width']:.1f}×{size['length']:.1f} | "
                f"{info['status']} |"
            )
        
        content = "\n".join(lines)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        logger.info(f"✓ 对象参考表已保存: {output_path}")
    
    def generate_visual_qa_prompt(self, question: str, object_map: Dict, 
                                   image_path: str) -> str:
        """
        生成 Visual VQA 提示词
        
        Args:
            question: 原始问题
            object_map: 对象映射表
            image_path: 图像路径
        
        Returns:
            完整的提示词
        """
        prompt = f"""# Visual Question Answering Task

## Scene Information
- Scene: {self.scene_name} Frame {self.frame_idx}
- Image: {image_path}

## Objects in Scene
"""
        for obj_id, info in sorted(object_map.items()):
            prompt += f"- **{obj_id}**: {info['type']} (status: {info['status']})\n"
        
        prompt += f"""
## Question
{question}

## Instructions
1. Look at the image to identify object positions and relationships
2. Use the object IDs (e.g., car1, pedestrian2) shown in the image
3. Answer the question based on visual information and object attributes
4. Your answer should be concise and specific

## Answer
"""
        return prompt


def visualize_scene(scene_graph_path: str, output_dir: Optional[str] = None):
    """
    可视化场景并生成标注图像
    
    Args:
        scene_graph_path: 场景图 JSON 路径
        output_dir: 输出目录（默认与场景图同目录）
    """
    # 加载场景图
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    # 确定输出目录
    if output_dir is None:
        output_dir = Path(scene_graph_path).parent / "visualizations"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建可视化器
    visualizer = ObjectVisualizer(scene_graph)
    
    # 生成文件名前缀
    scene_name = scene_graph.get('scene_name', 'unknown')
    frame_idx = scene_graph.get('frame_idx', 0)
    prefix = f"{scene_name}_frame{frame_idx}"
    
    # 生成 BEV 图像
    image_path = output_dir / f"{prefix}_tagged.png"
    object_map = visualizer.create_bev_with_tags(str(image_path))
    
    # 生成对象参考表
    table_path = output_dir / f"{prefix}_objects.md"
    visualizer.create_object_reference_table(object_map, str(table_path))
    
    # 保存对象映射 JSON
    json_path = output_dir / f"{prefix}_object_map.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(object_map, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ 可视化完成！")
    logger.info(f"  图像: {image_path}")
    logger.info(f"  参考表: {table_path}")
    logger.info(f"  映射JSON: {json_path}")
    
    return {
        'image_path': str(image_path),
        'table_path': str(table_path),
        'json_path': str(json_path),
        'object_map': object_map
    }


def generate_visual_qa_dataset(scene_graph_path: str, qa_data_path: str, 
                                output_dir: Optional[str] = None):
    """
    生成 Visual VQA 数据集
    
    Args:
        scene_graph_path: 场景图 JSON
        qa_data_path: QA 数据 JSON
        output_dir: 输出目录
    """
    # 可视化场景
    viz_result = visualize_scene(scene_graph_path, output_dir)
    
    # 加载 QA 数据
    with open(qa_data_path, 'r', encoding='utf-8') as f:
        qa_data = json.load(f)
    
    questions = qa_data.get('questions', [])
    if not questions:
        questions = [{'question': r['question'], 'answer': r.get('expected_answer', '')}
                    for r in qa_data.get('results', [])]
    
    # 加载场景图
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    visualizer = ObjectVisualizer(scene_graph)
    
    # 为每道题生成提示词
    visual_qa_dataset = []
    for i, q in enumerate(questions, 1):
        question = q['question']
        answer = q.get('answer', '')
        
        prompt = visualizer.generate_visual_qa_prompt(
            question, 
            viz_result['object_map'],
            viz_result['image_path']
        )
        
        visual_qa_dataset.append({
            'id': i,
            'question': question,
            'answer': answer,
            'prompt': prompt,
            'image': viz_result['image_path']
        })
    
    # 保存数据集
    output_dir = Path(viz_result['image_path']).parent
    dataset_path = output_dir / f"{Path(scene_graph_path).stem}_visual_qa.json"
    
    with open(dataset_path, 'w', encoding='utf-8') as f:
        json.dump(visual_qa_dataset, f, indent=2, ensure_ascii=False)
    
    logger.info(f"\n✓ Visual VQA 数据集已生成: {dataset_path}")
    logger.info(f"  问题数量: {len(visual_qa_dataset)}")
    
    return dataset_path


def main():
    """主函数"""
    import sys
    
    print("="*70)
    print("  对象可视化标注工具")
    print("="*70)
    
    # 默认路径
    default_sg = "output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json"
    
    if len(sys.argv) < 2:
        scene_graph_path = default_sg
    else:
        scene_graph_path = sys.argv[1]
    
    # 检查文件
    if not Path(scene_graph_path).exists():
        logger.error(f"找不到场景图文件: {scene_graph_path}")
        logger.info("\n用法: python visualize_and_tag_objects.py <scene_graph.json> [qa_data.json]")
        return
    
    # 可视化场景
    result = visualize_scene(scene_graph_path)
    
    # 如果提供了 QA 数据，生成 Visual VQA 数据集
    if len(sys.argv) >= 3:
        qa_data_path = sys.argv[2]
        if Path(qa_data_path).exists():
            generate_visual_qa_dataset(scene_graph_path, qa_data_path)
        else:
            logger.warning(f"找不到 QA 数据文件: {qa_data_path}")
    
    print("\n" + "="*70)
    print("提示：可以用这个图像给 Vision LLM (如 GPT-4V) 做 Visual VQA")
    print("="*70)


if __name__ == "__main__":
    main()
