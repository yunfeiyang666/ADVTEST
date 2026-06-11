"""
步骤4: 基于Neo4j的覆盖率分析

功能：
1. 计算空间配置覆盖率（C1）
2. 计算场景结构覆盖率（C2）
3. 识别长尾场景
4. 识别危险场景
5. 生成分析报告
"""
import os
import sys
import json
from neo4j import GraphDatabase

devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

import config


class CoverageAnalyzer:
    def __init__(self, uri, user, password):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print(f"✓ 已连接到Neo4j: {uri}")
    
    def close(self):
        """关闭连接"""
        self.driver.close()
    
    def calculate_c1_coverage(self):
        """
        计算C1覆盖率：空间配置多样性
        统计独特的(距离等级, 方向扇区, 对象类型)组合
        """
        print("\n=== C1覆盖率：空间配置多样性 ===")
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (ego:Ego)-[r:SPATIAL_RELATION]->(obj:Object)
                RETURN DISTINCT 
                    r.distance_level AS distance,
                    r.direction_sector AS direction,
                    labels(obj)[1] AS object_type,
                    COUNT(*) AS frequency
                ORDER BY frequency DESC
            """)
            
            configs = []
            for record in result:
                configs.append({
                    'distance': record['distance'],
                    'direction': record['direction'],
                    'object_type': record['object_type'],
                    'frequency': record['frequency']
                })
            
            print(f"  - 独特配置数: {len(configs)}")
            print(f"  - 前5个最常见配置:")
            for i, config in enumerate(configs[:5], 1):
                print(f"    {i}. {config['object_type']} + {config['distance']} + {config['direction']}: {config['frequency']}次")
            
            return {
                'total_configs': len(configs),
                'configs': configs
            }
    
    def calculate_c2_coverage(self):
        """
        计算C2覆盖率：场景结构多样性
        统计独特的场景拓扑结构
        """
        print("\n=== C2覆盖率：场景结构多样性 ===")
        
        with self.driver.session() as session:
            result = session.run("""
                MATCH (scene:Scene)-[:CONTAINS]->(ego:Ego)
                MATCH (ego)-[r:SPATIAL_RELATION]->(obj:Object)
                WITH scene,
                     collect({
                         type: labels(obj)[1],
                         distance: r.distance_level,
                         direction: r.direction_sector
                     }) AS structure
                RETURN scene.name AS scene_name,
                       structure,
                       size(structure) AS num_objects
                ORDER BY num_objects DESC
            """)
            
            structures = []
            for record in result:
                structures.append({
                    'scene_name': record['scene_name'],
                    'structure': record['structure'],
                    'num_objects': record['num_objects']
                })
            
            print(f"  - 总场景数: {len(structures)}")
            print(f"  - 场景复杂度:")
            for struct in structures:
                print(f"    * {struct['scene_name']}: {struct['num_objects']}个对象")
            
            return {
                'total_structures': len(structures),
                'structures': structures
            }
    
    def identify_longtail_scenes(self):
        """
        识别长尾场景
        找出独特的场景配置
        """
        print("\n=== 长尾场景识别 ===")
        
        with self.driver.session() as session:
            # 统计每种配置的出现次数
            result = session.run("""
                MATCH (scene:Scene)-[:CONTAINS]->(ego:Ego)
                MATCH (ego)-[r:SPATIAL_RELATION]->(obj:Object)
                WITH scene,
                     collect({
                         type: labels(obj)[1],
                         distance: r.distance_level,
                         direction: r.direction_sector
                     }) AS structure
                WITH structure, collect(scene.name) AS scenes
                RETURN structure, scenes, size(scenes) AS frequency
                ORDER BY frequency
            """)
            
            longtail = []
            common = []
            
            for record in result:
                if record['frequency'] == 1:
                    longtail.append({
                        'structure': record['structure'],
                        'scenes': record['scenes']
                    })
                else:
                    common.append({
                        'structure': record['structure'],
                        'scenes': record['scenes'],
                        'frequency': record['frequency']
                    })
            
            print(f"  - 长尾场景数: {len(longtail)}")
            print(f"  - 常见配置数: {len(common)}")
            
            if longtail:
                print(f"  - 长尾场景列表:")
                for lt in longtail[:5]:
                    print(f"    * {lt['scenes'][0]}")
                if len(longtail) > 5:
                    print(f"    ... 还有 {len(longtail)-5} 个长尾场景")
            
            if common:
                print(f"  - 常见配置:")
                for cm in common:
                    print(f"    * {cm['frequency']}个场景共享相同配置")
            
            return {
                'longtail_count': len(longtail),
                'common_count': len(common),
                'longtail_scenes': longtail,
                'common_configs': common
            }
    
    def identify_dangerous_scenes(self):
        """
        识别危险场景
        """
        print("\n=== 危险场景识别 ===")
        
        with self.driver.session() as session:
            # 极近距离场景
            result = session.run("""
                MATCH (scene:Scene)
                WHERE scene.min_distance < 5
                RETURN scene.name AS scene_name,
                       scene.min_distance AS min_distance,
                       scene.max_speed AS max_speed,
                       scene.total_objects AS total_objects
                ORDER BY scene.min_distance
            """)
            
            near_coll_scenes = []
            for record in result:
                near_coll_scenes.append({
                    'scene_name': record['scene_name'],
                    'min_distance': record['min_distance'],
                    'max_speed': record['max_speed'],
                    'total_objects': record['total_objects']
                })
            
            print(f"  - 极近碰撞风险场景: {len(near_coll_scenes)}")
            for scene in near_coll_scenes:
                print(f"    * {scene['scene_name']}: 最小距离{scene['min_distance']:.2f}m, "
                      f"最大速度{scene['max_speed']:.2f}m/s")
            
            # 高速场景
            result = session.run("""
                MATCH (scene:Scene)
                WHERE scene.max_speed > 15
                RETURN scene.name AS scene_name,
                       scene.max_speed AS max_speed,
                       scene.min_distance AS min_distance
                ORDER BY scene.max_speed DESC
            """)
            
            high_speed_scenes = []
            for record in result:
                high_speed_scenes.append({
                    'scene_name': record['scene_name'],
                    'max_speed': record['max_speed'],
                    'min_distance': record['min_distance']
                })
            
            print(f"  - 高速场景: {len(high_speed_scenes)}")
            for scene in high_speed_scenes:
                print(f"    * {scene['scene_name']}: 最大速度{scene['max_speed']:.2f}m/s")
            
            return {
                'near_coll_scenes': near_coll_scenes,
                'high_speed_scenes': high_speed_scenes
            }
    
    def generate_statistics(self):
        """
        生成综合统计
        """
        print("\n=== 综合统计 ===")
        
        with self.driver.session() as session:
            # 对象类型统计
            result = session.run("""
                MATCH (obj:Object)
                RETURN labels(obj)[1] AS type, COUNT(obj) AS count
                ORDER BY count DESC
            """)
            
            type_stats = {}
            for record in result:
                type_stats[record['type']] = record['count']
            
            print(f"  - 对象类型分布:")
            for obj_type, count in type_stats.items():
                print(f"    * {obj_type}: {count}")
            
            # 空间关系统计
            result = session.run("""
                MATCH ()-[r:SPATIAL_RELATION]->()
                UNWIND r.predicates AS predicate
                RETURN predicate, COUNT(*) AS frequency
                ORDER BY frequency DESC
            """)
            
            predicate_stats = {}
            for record in result:
                predicate_stats[record['predicate']] = record['frequency']
            
            print(f"  - 空间谓词分布:")
            for pred, freq in list(predicate_stats.items())[:5]:
                print(f"    * {pred}: {freq}")
            
            return {
                'type_stats': type_stats,
                'predicate_stats': predicate_stats
            }


def main():
    """主函数"""
    print("=" * 60)
    print("步骤4: 覆盖率分析和高级查询")
    print("=" * 60)
    
    # Neo4j连接信息
    NEO4J_URI = "neo4j://localhost:7600"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "87017563"
    
    # 连接Neo4j
    analyzer = CoverageAnalyzer(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    
    # 1. C1覆盖率
    c1_result = analyzer.calculate_c1_coverage()
    
    # 2. C2覆盖率
    c2_result = analyzer.calculate_c2_coverage()
    
    # 3. 长尾场景
    longtail_result = analyzer.identify_longtail_scenes()
    
    # 4. 危险场景
    dangerous_result = analyzer.identify_dangerous_scenes()
    
    # 5. 综合统计
    stats_result = analyzer.generate_statistics()
    
    # 保存分析结果
    analysis_report = {
        'c1_coverage': c1_result,
        'c2_coverage': c2_result,
        'longtail_analysis': longtail_result,
        'dangerous_scenes': dangerous_result,
        'statistics': stats_result
    }
    
    output_path = os.path.join(config.STATISTICS_DIR, 'step4_coverage_analysis.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(analysis_report, f, indent=2, ensure_ascii=False)
    
    print(f"\n✓ 分析报告已保存: {output_path}")
    
    # 关闭连接
    analyzer.close()
    
    print(f"\n✓ 步骤4完成！")
    print(f"\n关键发现:")
    print(f"  - C1覆盖率: {c1_result['total_configs']}种独特配置")
    print(f"  - C2覆盖率: {c2_result['total_structures']}个场景")
    print(f"  - 长尾场景: {longtail_result['longtail_count']}个")
    print(f"  - 危险场景: {len(dangerous_result['near_coll_scenes'])}个")
    
    print(f"\n下一步:")
    print(f"  1. 查看分析报告: {output_path}")
    print(f"  2. 生成可视化图表")
    print(f"  3. 更新PPT")


if __name__ == "__main__":
    main()
