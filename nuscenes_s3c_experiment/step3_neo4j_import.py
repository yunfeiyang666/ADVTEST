"""
步骤3: 导入场景图到Neo4j

功能：
1. 连接Neo4j数据库
2. 创建约束和索引
3. 导入场景图数据
4. 验证导入结果
"""
import os
import sys
import json
from neo4j import GraphDatabase
from tqdm import tqdm

# 添加本地nuscenes-devkit路径
devkit_path = r"E:\Project\ADVTEST\nuscenes-devkit\nuscenes-devkit-master\python-sdk"
if devkit_path not in sys.path:
    sys.path.insert(0, devkit_path)

import config


class Neo4jImporter:
    def __init__(self, uri, user, password):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        print(f"✓ 已连接到Neo4j: {uri}")
    
    def close(self):
        """关闭连接"""
        self.driver.close()
    
    def clear_database(self):
        """清空数据库"""
        print("\n正在清空数据库...")
        with self.driver.session() as session:
            # 先删除所有索引和约束
            try:
                session.run("DROP CONSTRAINT scene_token IF EXISTS")
                session.run("DROP INDEX ego_id IF EXISTS")
                session.run("DROP INDEX object_id IF EXISTS")
            except:
                pass
            
            # 删除所有节点和关系
            session.run("MATCH (n) DETACH DELETE n")
            
            # 验证清空
            result = session.run("MATCH (n) RETURN COUNT(n) AS count")
            count = result.single()['count']
            print(f"✓ 数据库已清空（剩余节点: {count}）")
    
    def create_constraints(self):
        """创建约束和索引"""
        print("\n正在创建约束和索引...")
        with self.driver.session() as session:
            # 场景唯一性约束
            try:
                session.run("""
                    CREATE CONSTRAINT scene_token IF NOT EXISTS
                    FOR (s:Scene) REQUIRE s.token IS UNIQUE
                """)
                print("  ✓ 场景token唯一性约束")
            except:
                print("  - 场景约束已存在")
            
            # Ego ID索引
            try:
                session.run("""
                    CREATE INDEX ego_id IF NOT EXISTS
                    FOR (e:Ego) ON (e.id)
                """)
                print("  ✓ Ego ID索引")
            except:
                print("  - Ego索引已存在")
            
            # 对象ID索引
            try:
                session.run("""
                    CREATE INDEX object_id IF NOT EXISTS
                    FOR (o:Object) ON (o.id)
                """)
                print("  ✓ 对象ID索引")
            except:
                print("  - 对象索引已存在")
        
        print("✓ 约束和索引创建完成")
    
    def import_scene(self, scene_data):
        """导入单个场景"""
        with self.driver.session() as session:
            # 1. 创建场景节点
            session.run("""
                CREATE (scene:Scene {
                    token: $token,
                    name: $name,
                    description: $description,
                    timestamp: $timestamp,
                    total_objects: $total_objects,
                    min_distance: $min_distance,
                    max_distance: $max_distance,
                    avg_distance: $avg_distance,
                    max_speed: $max_speed,
                    moving_objects: $moving_objects,
                    stopped_objects: $stopped_objects
                })
            """,
                token=scene_data['scene_token'],
                name=scene_data['scene_name'],
                description=scene_data.get('scene_description', ''),
                timestamp=scene_data['timestamp'],
                total_objects=scene_data['scene_statistics']['total_objects'],
                min_distance=scene_data['scene_statistics']['min_distance'],
                max_distance=scene_data['scene_statistics']['max_distance'],
                avg_distance=scene_data['scene_statistics']['avg_distance'],
                max_speed=scene_data['scene_statistics']['max_speed'],
                moving_objects=scene_data['scene_statistics']['moving_objects'],
                stopped_objects=scene_data['scene_statistics']['stopped_objects']
            )
            
            # 2. 创建Ego节点（每个场景独立的ego）
            ego_id = f"ego_{scene_data['scene_token'][:8]}"
            session.run("""
                MATCH (scene:Scene {token: $scene_token})
                CREATE (ego:Ego {
                    id: $ego_id,
                    scene_token: $scene_token,
                    position_x: $pos_x,
                    position_y: $pos_y,
                    position_z: $pos_z
                })
                CREATE (scene)-[:CONTAINS]->(ego)
            """,
                scene_token=scene_data['scene_token'],
                ego_id=ego_id,
                pos_x=scene_data['ego_pose']['translation']['x'],
                pos_y=scene_data['ego_pose']['translation']['y'],
                pos_z=scene_data['ego_pose']['translation']['z']
            )
            
            # 3. 导入对象
            for obj in scene_data['objects_detailed']:
                self.import_object(session, scene_data['scene_token'], obj)
    
    def import_object(self, session, scene_token, obj_data):
        """导入单个对象"""
        obj_type = obj_data['type'].capitalize()
        
        # 提取谓词中的距离和方向等级
        predicates = obj_data['predicates']
        distance_level = None
        direction_sector = None
        moving = False
        
        for pred in predicates:
            if pred in ['near_coll', 'super_near', 'very_near', 'near', 'visible']:
                distance_level = pred
            elif pred in ['front', 'rear', 'left', 'right']:
                direction_sector = pred
            elif pred == 'moving':
                moving = True
        
        # 创建对象节点和关系
        ego_id = f"ego_{scene_token[:8]}"
        session.run(f"""
            MATCH (scene:Scene {{token: $scene_token}})
            MATCH (ego:Ego {{scene_token: $scene_token}})
            CREATE (obj:Object:{obj_type} {{
                id: $id,
                category: $category,
                size_width: $size_width,
                size_length: $size_length,
                size_height: $size_height,
                num_lidar_pts: $num_lidar_pts,
                num_radar_pts: $num_radar_pts
            }})
            CREATE (scene)-[:CONTAINS]->(obj)
            CREATE (ego)-[:SPATIAL_RELATION {{
                predicates: $predicates,
                distance: $distance,
                angle: $angle,
                speed: $speed,
                relative_x: $relative_x,
                relative_y: $relative_y,
                relative_z: $relative_z,
                velocity_x: $velocity_x,
                velocity_y: $velocity_y,
                velocity_z: $velocity_z,
                distance_level: $distance_level,
                direction_sector: $direction_sector,
                moving: $moving
            }}]->(obj)
        """,
            scene_token=scene_token,
            id=f"{obj_data['type']}_{obj_data['token'][:8]}",
            category=obj_data['category'],
            size_width=obj_data['size']['width'],
            size_length=obj_data['size']['length'],
            size_height=obj_data['size']['height'],
            num_lidar_pts=obj_data['quality']['num_lidar_pts'],
            num_radar_pts=obj_data['quality']['num_radar_pts'],
            predicates=predicates,
            distance=obj_data['distance'],
            angle=obj_data['angle'],
            speed=obj_data['speed'],
            relative_x=obj_data['relative_position']['x'],
            relative_y=obj_data['relative_position']['y'],
            relative_z=obj_data['relative_position']['z'],
            velocity_x=obj_data['velocity_vector']['vx'],
            velocity_y=obj_data['velocity_vector']['vy'],
            velocity_z=obj_data['velocity_vector']['vz'],
            distance_level=distance_level,
            direction_sector=direction_sector,
            moving=moving
        )
    
    def verify_import(self):
        """验证导入结果"""
        print("\n正在验证导入结果...")
        with self.driver.session() as session:
            # 统计节点
            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] AS label, COUNT(n) AS count
                ORDER BY count DESC
            """)
            
            print("\n节点统计:")
            total_nodes = 0
            for record in result:
                print(f"  - {record['label']}: {record['count']}")
                total_nodes += record['count']
            print(f"  总计: {total_nodes} 个节点")
            
            # 统计关系
            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) AS type, COUNT(r) AS count
                ORDER BY count DESC
            """)
            
            print("\n关系统计:")
            total_rels = 0
            for record in result:
                print(f"  - {record['type']}: {record['count']}")
                total_rels += record['count']
            print(f"  总计: {total_rels} 条关系")


def load_scene_graphs():
    """加载场景图数据"""
    sg_path = os.path.join(config.SCENE_GRAPHS_DIR, 'all_scene_graphs_enhanced.json')
    
    if not os.path.exists(sg_path):
        raise FileNotFoundError(f"找不到场景图文件: {sg_path}\n请先运行步骤2")
    
    with open(sg_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    return data


def main():
    """主函数"""
    print("=" * 60)
    print("步骤3: 导入场景图到Neo4j")
    print("=" * 60)
    
    # Neo4j连接信息
    NEO4J_URI = "neo4j://localhost:7600"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "87017563"  # 修改为你的密码
    
    print(f"\nNeo4j连接信息:")
    print(f"  - URI: {NEO4J_URI}")
    print(f"  - User: {NEO4J_USER}")
    
    # 连接Neo4j
    try:
        importer = Neo4jImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
    except Exception as e:
        print(f"\n❌ 连接失败: {e}")
        print("\n请检查:")
        print("  1. Neo4j数据库是否在运行")
        print("  2. 密码是否正确")
        print("  3. 端口7687是否可用")
        return
    
    # 清空数据库
    importer.clear_database()
    
    # 创建约束和索引
    importer.create_constraints()
    
    # 加载场景图数据
    print("\n正在加载场景图数据...")
    all_scene_graphs = load_scene_graphs()
    print(f"✓ 加载了 {len(all_scene_graphs)} 个场景图")
    
    # 导入数据
    print("\n正在导入场景图到Neo4j...")
    for scene_data in tqdm(all_scene_graphs, desc="导入场景"):
        try:
            importer.import_scene(scene_data)
        except Exception as e:
            print(f"\n警告: 场景 {scene_data['scene_name']} 导入失败: {e}")
            continue
    
    print(f"\n✓ 场景图导入完成")
    
    # 验证导入
    importer.verify_import()
    
    # 关闭连接
    importer.close()
    
    print(f"\n✓ 步骤3完成！")
    print(f"\n下一步:")
    print(f"  1. 在Neo4j Browser中查看数据")
    print(f"  2. 运行Cypher查询")
    print(f"  3. 进行覆盖率分析")


if __name__ == "__main__":
    main()
