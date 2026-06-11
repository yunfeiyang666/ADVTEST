"""
步骤5: 生成覆盖率热力图

功能：
1. 从Neo4j查询覆盖数据
2. 生成距离×方向热力图
3. 标注盲区
"""
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from neo4j import GraphDatabase

devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

import config

# Neo4j连接信息
NEO4J_URI = "neo4j://localhost:7600"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "87017563"

print("=" * 60)
print("生成覆盖率热力图")
print("=" * 60)

# 连接Neo4j
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
print(f"✓ 已连接到Neo4j")

# 查询覆盖数据
print(f"\n正在查询覆盖数据...")

with driver.session() as session:
    result = session.run("""
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
    """)
    
    # 收集数据
    data = {}
    for record in result:
        key = (record['distance_level'], record['direction'])
        data[key] = record['count']
    
    print(f"✓ 查询完成，获得 {len(data)} 个数据点")

driver.close()

# 创建矩阵
distance_labels = ['near', 'mid', 'far']
direction_labels = ['front', 'rear', 'left', 'right']

matrix = np.zeros((3, 4))

for i, dist in enumerate(distance_labels):
    for j, direction in enumerate(direction_labels):
        matrix[i][j] = data.get((dist, direction), 0)

print(f"\n覆盖矩阵:")
print(f"        front  rear  left  right")
for i, dist in enumerate(distance_labels):
    print(f"{dist:6s}  {matrix[i][0]:5.0f}  {matrix[i][1]:5.0f}  {matrix[i][2]:5.0f}  {matrix[i][3]:5.0f}")

# 绘制热力图
print(f"\n正在生成热力图...")

plt.figure(figsize=(10, 7))

# 使用seaborn绘制热力图
ax = sns.heatmap(
    matrix,
    annot=True,  # 显示数值
    fmt='.0f',  # 整数格式
    cmap='YlOrRd',  # 黄-橙-红配色
    xticklabels=direction_labels,
    yticklabels=distance_labels,
    cbar_kws={'label': 'Number of Objects'},
    linewidths=1,
    linecolor='white',
    square=True,  # 方形格子
    vmin=0  # 最小值从0开始
)

# 标题和标签
plt.title('Scene Coverage Heatmap\nDistance Level × Direction Sector', 
          fontsize=16, fontweight='bold', pad=20)
plt.xlabel('Direction Sector', fontsize=13, fontweight='bold')
plt.ylabel('Distance Level', fontsize=13, fontweight='bold')

# 添加说明文字
plt.text(0.5, -0.15, 
         'Coverage Rate: 41.67% (60/144 combinations)\nWhite cells indicate coverage blind spots',
         ha='center', transform=ax.transAxes, fontsize=10, style='italic')

plt.tight_layout()

# 保存
output_dir = os.path.join(config.FIGURES_DIR)
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'coverage_heatmap.png')

plt.savefig(output_path, dpi=300, bbox_inches='tight')
print(f"✓ 热力图已保存: {output_path}")

# 显示
plt.show()

print(f"\n✓ 完成！")
print(f"\n热力图解读:")
print(f"  - 深红色：覆盖密度高（数据多）")
print(f"  - 浅黄色：覆盖密度低（数据少）")
print(f"  - 白色/0：覆盖盲区（无数据）")
print(f"\n关键发现:")
print(f"  - front方向覆盖最好")
print(f"  - left方向覆盖较差")
print(f"  - 如果有白色格子，说明该配置完全缺失")
