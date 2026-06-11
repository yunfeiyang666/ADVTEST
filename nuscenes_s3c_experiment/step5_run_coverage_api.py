"""
步骤5: 运行覆盖率API

整合Part 1-3，提供完整的覆盖率计算功能
"""
import os
import sys

# 由于代码分成了3个部分，这里手动整合
# 实际使用时，将Part 1-3的代码合并到一个文件中

# 这里提供简化的运行脚本
print("请将Part 1-3的代码合并后运行")
print("或者直接在Neo4j Browser中使用Cypher查询")

# ========== 快速覆盖率计算（不需要完整API）==========

from neo4j import GraphDatabase
import json

NEO4J_URI = "neo4j://localhost:7600"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "87017563"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

print("\n" + "=" * 60)
print("快速覆盖率计算")
print("=" * 60)

# 定义覆盖空间
distance_levels = ['near', 'mid', 'far']
directions = ['front', 'rear', 'left', 'right']
motions = ['moving', 'stopped']
types = ['Pedestrian', 'Car', 'Truck', 'Bus', 'Bicycle', 'Motorcycle']

total = len(distance_levels) * len(directions) * len(motions) * len(types)
print(f"\n理论总组合数（分母）: {total}")

# 查询实际覆盖
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
        RETURN DISTINCT distance_level, direction, motion, object_type
    """)
    
    actual_combinations = set()
    for record in result:
        combo = (
            record['distance_level'],
            record['direction'],
            record['motion'],
            record['object_type']
        )
        actual_combinations.add(combo)

actual = len(actual_combinations)
print(f"实际覆盖组合数（分子）: {actual}")

# 计算覆盖率
coverage = actual / total * 100
print(f"\n覆盖率: {coverage:.2f}%")
print(f"未覆盖: {total - actual}种组合 ({(total-actual)/total*100:.2f}%)")

# 保存结果
result_data = {
    'total_combinations': total,
    'actual_combinations': actual,
    'coverage_percentage': coverage,
    'uncovered_count': total - actual
}

output_dir = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\statistics"
os.makedirs(output_dir, exist_ok=True)

with open(os.path.join(output_dir, 'step5_coverage_result.json'), 'w') as f:
    json.dump(result_data, f, indent=2)

print(f"\n✓ 结果已保存")

driver.close()
```

**完成！现在创建使用说明...** 📝
