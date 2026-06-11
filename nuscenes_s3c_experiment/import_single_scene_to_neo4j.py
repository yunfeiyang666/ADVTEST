"""
单场景Neo4j导入脚本

将生成的场景图导入Neo4j图数据库
"""
import json
from pathlib import Path
from neo4j import GraphDatabase


class Neo4jImporter:
    def __init__(self, uri, user, password):
        """初始化Neo4j连接"""
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        
    def close(self):
        """关闭连接"""
        self.driver.close()
    
    def clear_database(self):
        """清空数据库"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("✓ 数据库已清空")
    
    def create_constraints(self):
        """创建约束（确保unique_id唯一）"""
        with self.driver.session() as session:
            try:
                session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (obj:Object) REQUIRE obj.unique_id IS UNIQUE")
                print("✓ 约束已创建")
            except Exception as e:
                print(f"  约束创建跳过（可能已存在）: {e}")
    
    def import_scene(self, scene_graph):
        """导入场景图数据"""
        print(f"\n导入场景: {scene_graph['scene_name']}")
        
        # 兼容不同的字段名
        objects = scene_graph.get('objects') or scene_graph.get('nodes', [])
        relationships = scene_graph.get('relationships') or scene_graph.get('edges', [])
        
        with self.driver.session() as session:
            # 1. 创建对象节点
            print("  创建对象节点...")
            for obj in objects:
                # 准备属性
                props = {
                    'unique_id': obj['unique_id'],
                    'type': obj['type'],
                }
                
                # 添加位置信息
                if 'translation' in obj:
                    trans = obj['translation']
                    if isinstance(trans, dict):
                        props['translation_x'] = trans['x']
                        props['translation_y'] = trans['y']
                        props['translation_z'] = trans['z']
                    else:
                        props['translation_x'] = trans[0]
                        props['translation_y'] = trans[1]
                        props['translation_z'] = trans[2]
                
                # 添加尺寸信息
                if 'size' in obj and obj['size'] is not None:
                    size = obj['size']
                    if isinstance(size, dict):
                        props['size_width'] = size['width']
                        props['size_length'] = size['length']
                        props['size_height'] = size['height']
                    else:
                        props['size_width'] = size[0]
                        props['size_length'] = size[1]
                        props['size_height'] = size[2]
                
                # 添加速度信息
                if 'velocity' in obj and obj['velocity'] is not None:
                    vel = obj['velocity']
                    if isinstance(vel, dict):
                        props['velocity_vx'] = vel['vx']
                        props['velocity_vy'] = vel['vy']
                        props['velocity_vz'] = vel['vz']
                    else:
                        props['velocity_vx'] = vel[0]
                        props['velocity_vy'] = vel[1]
                        props['velocity_vz'] = vel[2]
                
                # 添加其他属性
                if 'category' in obj:
                    props['category'] = obj['category']
                if 'num_lidar_pts' in obj:
                    props['num_lidar_pts'] = obj['num_lidar_pts']
                if 'is_ego' in obj:
                    props['is_ego'] = obj['is_ego']
                
                # 🆕 新增：添加状态属性
                if 'status' in obj:
                    props['status'] = obj['status']
                
                # 🆕 新增：添加attributes属性（转换为字符串）
                if 'attributes' in obj and obj['attributes']:
                    props['attributes'] = ','.join(obj['attributes'])
                
                # 创建节点
                session.run(
                    "CREATE (obj:Object $props)",
                    props=props
                )
            
            print(f"  ✓ 已创建 {len(objects)} 个对象节点")
            
            # 2. 创建关系
            print("  创建关系...")
            relationship_count = 0
            
            for rel in relationships:
                # 准备关系属性
                rel_props = {
                    'predicates': rel['predicates'],  # [方位, 距离级别]
                    'distance': rel['metrics']['distance'],
                    'angle': rel['metrics']['angle']
                }
                
                # 🆕 新增：添加4方位和8方位字段
                if 'direction_4' in rel and rel['direction_4']:
                    rel_props['direction_4'] = rel['direction_4']
                if 'direction_8' in rel and rel['direction_8']:
                    rel_props['direction_8'] = rel['direction_8']
                
                # 添加相对位置
                if 'relative_position' in rel['metrics']:
                    rel_pos = rel['metrics']['relative_position']
                    rel_props['relative_x'] = rel_pos['x']
                    rel_props['relative_y'] = rel_pos['y']
                    rel_props['relative_z'] = rel_pos['z']
                
                # 创建关系
                session.run(
                    """
                    MATCH (a:Object {unique_id: $source})
                    MATCH (b:Object {unique_id: $target})
                    CREATE (a)-[r:RELATES_TO $props]->(b)
                    """,
                    source=rel['source'],
                    target=rel['target'],
                    props=rel_props
                )
                relationship_count += 1
                
                # 每100条打印一次进度
                if relationship_count % 100 == 0:
                    print(f"    已创建 {relationship_count} 条关系...")
            
            print(f"  ✓ 已创建 {relationship_count} 条关系")
    
    def verify_import(self):
        """验证导入结果"""
        print("\n验证导入结果...")
        
        with self.driver.session() as session:
            # 统计节点数
            result = session.run("MATCH (n:Object) RETURN count(n) as count")
            node_count = result.single()['count']
            print(f"  对象节点数: {node_count}")
            
            # 统计关系数
            result = session.run("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
            rel_count = result.single()['count']
            print(f"  关系数: {rel_count}")
            
            # 显示对象类型分布
            result = session.run("""
                MATCH (n:Object) 
                RETURN n.type as type, count(*) as count 
                ORDER BY count DESC
            """)
            print("\n  对象类型分布:")
            for record in result:
                print(f"    {record['type']}: {record['count']}")
            
            # 显示ego周围最近的5个对象
            result = session.run("""
                MATCH (ego:Object {unique_id: 'ego'})-[r:RELATES_TO]->(obj:Object)
                RETURN obj.unique_id as id, obj.type as type, r.distance as distance
                ORDER BY r.distance ASC
                LIMIT 5
            """)
            print("\n  Ego车周围最近的5个对象:")
            for record in result:
                print(f"    {record['id']} ({record['type']}): {record['distance']:.2f}m")


def main():
    """主函数"""
    print("=" * 70)
    print("  单场景Neo4j导入")
    print("=" * 70)
    
    # 加载场景图数据
    data_path = Path('output/single_scene_demo/single_scene_full_graph.json')
    if not data_path.exists():
        print(f"\n✗ 错误：找不到场景图数据文件: {data_path}")
        print("  请先运行 single_scene_demo.py 生成数据")
        return
    
    print(f"\n加载场景图数据: {data_path}")
    with open(data_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    print(f"✓ 已加载场景: {scene_graph['scene_name']}")
    print(f"  对象数: {len(scene_graph['objects'])}")
    print(f"  关系数: {len(scene_graph['relationships'])}")
    
    # Neo4j连接配置
    NEO4J_URI = "bolt://localhost:7600"  # 使用bolt协议（适用于Neo4j Desktop）
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "87017563"
    
    print(f"\n连接Neo4j数据库...")
    print(f"  URI: {NEO4J_URI}")
    
    try:
        importer = Neo4jImporter(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        print("✓ 连接成功")
        
        # 清空数据库
        print("\n清空现有数据...")
        importer.clear_database()
        
        # 创建约束
        print("\n创建约束...")
        importer.create_constraints()
        
        # 导入场景
        importer.import_scene(scene_graph)
        
        # 验证导入
        importer.verify_import()
        
        # 关闭连接
        importer.close()
        
        print("\n" + "=" * 70)
        print("✓ 导入完成！")
        print("\n下一步：")
        print("  1. 打开Neo4j Browser: http://localhost:7474")
        print("  2. 执行查询示例（见下方）")
        print("\n查询示例：")
        print("  # 查看所有对象")
        print("  MATCH (n:Object) RETURN n LIMIT 25")
        print()
        print("  # 查看ego周围的对象")
        print("  MATCH (ego:Object {unique_id: 'ego'})-[r]->(obj)")
        print("  RETURN ego, r, obj")
        print()
        print("  # 查看完整关系网络")
        print("  MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n✗ 错误: {e}")
        print("\n请确保：")
        print("  1. Neo4j服务正在运行")
        print("  2. 连接信息正确（URI, 用户名, 密码）")
        print("  3. 已安装neo4j Python驱动: pip install neo4j")


if __name__ == "__main__":
    main()
