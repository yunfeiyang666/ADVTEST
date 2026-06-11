#!/usr/bin/env python
"""检查实际数据并生成正确的ground truth"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'core_pipeline'))
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig


def main():
    config = Neo4jConfig.from_env()
    
    with Neo4jImporter(config) as importer:
        with importer._session() as session:
            print("="*60)
            print("检查scene-0103实际数据")
            print("="*60)
            
            # Q1: 自车前方有多少行人？
            print("\nQ1: 自车前方有多少行人？")
            result = session.run("""
                MATCH (ego:Object {unique_id: 'scene-0103_ego'})-[r:RELATES_TO]->(p:Object)
                WHERE p.type = 'pedestrian' AND 'front' IN r.angle_matches_ego
                RETURN count(p) as count
            """)
            count = result.single()['count']
            print(f"  Ego Frame (angle_matches_ego): {count}")
            
            result = session.run("""
                MATCH (ego:Object {unique_id: 'scene-0103_ego'})-[r:RELATES_TO]->(p:Object)
                WHERE p.type = 'pedestrian' AND 'front' IN r.angle_matches_source
                RETURN count(p) as count
            """)
            count = result.single()['count']
            print(f"  Source Frame (angle_matches_source): {count}")
            
            # Q2: 自车左侧有车辆吗？
            print("\nQ2: 自车左侧有车辆吗？")
            result = session.run("""
                MATCH (ego:Object {unique_id: 'scene-0103_ego'})-[r:RELATES_TO]->(c:Object)
                WHERE c.type = 'car' AND 'left' IN r.angle_matches_ego
                RETURN count(c) as count
            """)
            count = result.single()['count']
            print(f"  Ego Frame: {count} (Yes/No: {'Yes' if count > 0 else 'No'})")
            
            # Q3: car1后方有行人吗？
            print("\nQ3: car1后方有行人吗？")
            result = session.run("""
                MATCH (car1:Object {unique_id: 'scene-0103_car1'})-[r:RELATES_TO]->(p:Object)
                WHERE p.type = 'pedestrian' AND 'back' IN r.angle_matches_source
                RETURN count(p) as count, collect(p.unique_id)[0..3] as samples
            """)
            record = result.single()
            print(f"  Source Frame: {record['count']} (Yes/No: {'Yes' if record['count'] > 0 else 'No'})")
            print(f"  Samples: {record['samples']}")
            
            # Q4: 自车右前方10米内有多少对象？
            print("\nQ4: 自车右前方10米内有多少对象？")
            result = session.run("""
                MATCH (ego:Object {unique_id: 'scene-0103_ego'})-[r:RELATES_TO]->(obj:Object)
                WHERE 'front-right' IN r.angle_matches_ego AND r.distance <= 10
                RETURN count(obj) as count
            """)
            count = result.single()['count']
            print(f"  Ego Frame: {count}")
            
            # Q5: 场景中总共有多少辆车？
            print("\nQ5: 场景中总共有多少辆车？")
            result = session.run("""
                MATCH (c:Object)
                WHERE c.unique_id STARTS WITH 'scene-0103_' AND c.type = 'car'
                RETURN count(c) as count
            """)
            count = result.single()['count']
            print(f"  Total cars: {count}")
            
            # 额外检查：显示所有方向分布
            print("\n" + "="*60)
            print("scene-0103 ego周围对象方向分布 (Ego Frame)")
            print("="*60)
            result = session.run("""
                MATCH (ego:Object {unique_id: 'scene-0103_ego'})-[r:RELATES_TO]->(obj:Object)
                RETURN r.direction_8_ego as direction, obj.type as type, count(*) as cnt
                ORDER BY direction, type
            """)
            for record in result:
                print(f"  {record['direction']:15} | {record['type']:12} | {record['cnt']}")


if __name__ == "__main__":
    main()
