#!/usr/bin/env python
"""验证Neo4j中的双坐标系数据"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig

def main():
    config = Neo4jConfig.from_env()
    
    with Neo4jImporter(config) as importer:
        with importer._session() as session:
            # 1. 检查双坐标系属性是否存在
            print("=" * 60)
            print("检查双坐标系数据")
            print("=" * 60)
            
            result = session.run("""
                MATCH ()-[r:RELATES_TO]->()
                WHERE r.angle_source IS NOT NULL AND r.angle_ego IS NOT NULL
                RETURN count(r) as count
            """)
            count = result.single()['count']
            print(f"\n✓ 包含双坐标系角度的关系数: {count}")
            
            # 2. 检查angle_matches属性
            result = session.run("""
                MATCH ()-[r:RELATES_TO]->()
                WHERE r.angle_matches_source IS NOT NULL
                RETURN count(r) as count
            """)
            count = result.single()['count']
            print(f"✓ 包含angle_matches_source的关系数: {count}")
            
            # 3. 示例数据展示
            print("\n" + "-" * 60)
            print("示例: scene-0103中car到pedestrian的关系")
            print("-" * 60)
            
            result = session.run("""
                MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
                WHERE src.unique_id CONTAINS 'scene-0103' 
                  AND src.unique_id CONTAINS 'car'
                  AND tgt.type = 'pedestrian'
                RETURN src.unique_id as source, 
                       tgt.unique_id as target,
                       r.distance as distance,
                       r.angle_source as angle_source,
                       r.direction_8_source as dir8_source,
                       r.angle_matches_source as matches_source,
                       r.angle_ego as angle_ego,
                       r.direction_8_ego as dir8_ego,
                       r.angle_matches_ego as matches_ego
                LIMIT 5
            """)
            
            for record in result:
                print(f"\n{record['source']} -> {record['target']}")
                print(f"  Distance: {record['distance']}")
                print(f"  Source Frame: angle={record['angle_source']}, dir8={record['dir8_source']}")
                print(f"    matches: {record['matches_source']}")
                print(f"  Ego Frame: angle={record['angle_ego']}, dir8={record['dir8_ego']}")
                print(f"    matches: {record['matches_ego']}")
            
            # 4. 测试方向查询
            print("\n" + "-" * 60)
            print("测试: 查找所有 'back-right' 方向的关系（使用angle_matches）")
            print("-" * 60)
            
            result = session.run("""
                MATCH (src:Object)-[r:RELATES_TO]->(tgt:Object)
                WHERE 'back-right' IN r.angle_matches_ego
                RETURN src.unique_id as source, 
                       tgt.unique_id as target,
                       r.angle_ego as angle,
                       r.direction_8_ego as direction
                LIMIT 5
            """)
            
            for record in result:
                print(f"  {record['source']} -> {record['target']}: angle={record['angle']}, dir={record['direction']}")
            
            print("\n✓ 验证完成")

if __name__ == "__main__":
    main()
