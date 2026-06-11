"""快速导入scene-0553到Neo4j"""
import json
from neo4j import GraphDatabase

# Neo4j配置
NEO4J_URI = "bolt://localhost:7600"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "87017563"

def main():
    print("=" * 70)
    print("  导入 scene-0553 frame 8 到 Neo4j")
    print("=" * 70)
    
    # 加载场景图
    scene_graph_path = "E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/scene-0553_frame8_scene_graph.json"
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    print(f"\n加载场景图: {scene_graph['scene_name']} frame {scene_graph['frame_idx']}")
    print(f"  对象数: {len(scene_graph['nodes'])}")
    print(f"  关系数: {len(scene_graph['edges'])}")
    
    # 连接Neo4j
    print("\n连接Neo4j...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        # 清空数据库
        print("清空数据库...")
        session.run("MATCH (n) DETACH DELETE n")
        
        # 创建约束
        try:
            session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (obj:Object) REQUIRE obj.unique_id IS UNIQUE")
        except:
            pass
        
        # 创建对象节点
        print("创建对象节点...")
        for obj in scene_graph['nodes']:
            props = {
                'unique_id': obj['unique_id'],
                'type': obj['type'],
                'category': obj.get('category', obj['type']),
                'status': obj.get('status', 'unknown'),
            }
            
            if 'translation' in obj and obj['translation']:
                props['translation_x'] = obj['translation']['x']
                props['translation_y'] = obj['translation']['y']
                props['translation_z'] = obj['translation']['z']
            
            if 'velocity' in obj and obj['velocity']:
                props['velocity_vx'] = obj['velocity']['vx']
                props['velocity_vy'] = obj['velocity']['vy']
                props['velocity_vz'] = obj['velocity']['vz']
            
            if 'attributes' in obj and obj['attributes']:
                props['attributes'] = ','.join(obj['attributes'])
            
            session.run("CREATE (obj:Object $props)", props=props)
        
        print(f"  ✓ 已创建 {len(scene_graph['nodes'])} 个对象节点")
        
        # 创建关系
        print("创建关系...")
        count = 0
        for rel in scene_graph['edges']:
            rel_props = {
                'predicates': rel['predicates'],
                'distance': rel['metrics']['distance'],
                'angle': rel['metrics']['angle'],
                # 新增: 4方位和8方位方向
                'direction_4': rel.get('direction_4', rel['predicates'][0]),
                'direction_8': rel.get('direction_8', rel['predicates'][0])
            }
            
            if 'relative_position' in rel['metrics']:
                rel_pos = rel['metrics']['relative_position']
                rel_props['relative_x'] = rel_pos['x']
                rel_props['relative_y'] = rel_pos['y']
                rel_props['relative_z'] = rel_pos['z']
            
            session.run("""
                MATCH (a:Object {unique_id: $source})
                MATCH (b:Object {unique_id: $target})
                CREATE (a)-[r:RELATES_TO $props]->(b)
            """, source=rel['source'], target=rel['target'], props=rel_props)
            
            count += 1
            if count % 500 == 0:
                print(f"    已创建 {count} 条关系...")
        
        print(f"  ✓ 已创建 {count} 条关系")
        
        # 验证
        print("\n验证导入结果...")
        
        # 验证bicycle与truck的关系
        result = session.run("""
            MATCH (b:Object {type:'bicycle'})-[r:RELATES_TO]->(t:Object)
            WHERE t.type='truck' OR t.category CONTAINS 'trailer'
            RETURN b.unique_id as bicycle, r.predicates as direction, t.unique_id as truck, t.status as status, t.category as category
        """)
        
        print("\n=== Bicycle与Truck/Trailer的关系 ===")
        for record in result:
            print(f"  {record['bicycle']} -[{record['direction']}]-> {record['truck']} (status={record['status']}, category={record['category']})")
        
        # 测试查询: back-right方向的truck
        print("\n=== 测试查询: bicycle back-right方向的truck (排除trailer) ===")
        result = session.run("""
            MATCH (b:Object {type:'bicycle'})-[r:RELATES_TO]->(t:Object)
            WHERE r.predicates[0] = 'back-right' 
            AND t.type = 'truck' 
            AND NOT t.category CONTAINS 'trailer'
            RETURN t.unique_id as truck, t.status as status
        """)
        
        for record in result:
            print(f"  {record['truck']}: status = {record['status']}")
        
        # 新增: 验证4方位方向
        print("\n=== 验证4方位: ego back方向的truck ===")
        result = session.run("""
            MATCH (e:Object {unique_id:'ego'})-[r:RELATES_TO]->(t:Object {type:'truck'})
            WHERE r.direction_4 = 'back'
            RETURN t.unique_id as truck, t.status as status, t.category as cat, r.direction_8 as dir8
        """)
        for record in result:
            is_trailer = 'trailer' in record['cat']
            print(f"  {record['truck']}: status={record['status']}, 8方位={record['dir8']}, trailer={is_trailer}")
        
        print("\n=== 验证4方位: trailer front方向的bus ===")
        result = session.run("""
            MATCH (t:Object)-[r:RELATES_TO]->(b:Object {type:'bus'})
            WHERE t.category CONTAINS 'trailer' AND r.direction_4 = 'front'
            RETURN t.unique_id as trailer, b.unique_id as bus, b.status as status, r.direction_8 as dir8
        """)
        for record in result:
            print(f"  {record['trailer']} --4方位:front, 8方位:{record['dir8']}--> {record['bus']}: status={record['status']}")
    
    driver.close()
    print("\n✓ 导入完成!")
    print("\n下一步: 运行VQA测试")


if __name__ == "__main__":
    main()
