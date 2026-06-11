"""验证跳过的错题"""
from neo4j import GraphDatabase
import json
from pathlib import Path
import sys

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
from import_single_scene_to_neo4j import Neo4jImporter, Neo4jConfig

SCENE_GRAPH_DIR = Path(__file__).parent / "output" / "coverage_analysis" / "scene_graphs"

def verify_scene_0916():
    """验证 scene-0916 的错题"""
    driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))
    
    print("="*60)
    print("验证 scene-0916 frame 8")
    print("="*60)
    
    with driver.session() as s:
        # Q4: truck to front-left of bus, expected: parked
        print("\n[Q4] 'What status is the truck to front-left of bus?'")
        print("     Expected: parked")
        
        r = s.run('''
            MATCH (bus:Object {type:'bus'})-[r]->(truck:Object {type:'truck'})
            WHERE 'front-left' IN r.angle_matches_source
            RETURN truck.unique_id, truck.status
        ''').data()
        print(f"     front-left trucks: {r}")
        
        # 检查所有方向
        r2 = s.run('''
            MATCH (bus:Object {type:'bus'})-[r]->(truck:Object {type:'truck'})
            RETURN truck.unique_id, truck.status, r.angle_matches_source
        ''').data()
        print(f"     All bus->truck relations: {r2}")
        
        # 检查所有truck
        r3 = s.run("MATCH (t:Object {type:'truck'}) RETURN t.unique_id, t.status").data()
        print(f"     All trucks in scene: {r3}")
        
        if not r:
            print("     ❌ 确认错题: bus的front-left没有truck")
        else:
            actual_status = r[0].get('truck.status')
            if actual_status == 'parked' or actual_status == 'stopped':
                print(f"     ✓ 题目正确: truck status = {actual_status}")
            else:
                print(f"     ❌ 确认错题: truck status = {actual_status}, expected parked")
    
    driver.close()


def verify_scene_0553():
    """验证 scene-0553 的错题"""
    # 先导入 scene-0553 数据
    config = Neo4jConfig(
        uri='bolt://localhost:7600',
        user='neo4j', 
        password='87017563'
    )
    importer = Neo4jImporter(config)
    
    scene_graph_path = SCENE_GRAPH_DIR / "scene-0553_frame8_scene_graph.json"
    if not scene_graph_path.exists():
        print(f"场景图文件不存在: {scene_graph_path}")
        return
    
    print("\n" + "="*60)
    print("导入 scene-0553 frame 8 数据...")
    print("="*60)
    importer.clear_database()
    importer.create_schema()
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    importer.import_scene(scene_graph)
    
    driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))
    
    print("\n" + "="*60)
    print("验证 scene-0553 frame 8")
    print("="*60)
    
    with driver.session() as s:
        # 先检查是否有trailer
        trailers = s.run("MATCH (t:Object) WHERE t.category CONTAINS 'trailer' RETURN t.unique_id, t.type, t.status").data()
        print(f"\n所有trailers: {trailers}")
        
        # Q7: other things same status as trailer, expected: 8
        print("\n[Q7] 'What number of other things are there of the same status as the trailer?'")
        print("     Expected: 8")
        
        if trailers:
            trailer_status = trailers[0].get('t.status')
            print(f"     Trailer status: {trailer_status}")
            
            r = s.run(f'''
                MATCH (obj:Object)
                WHERE obj.status = '{trailer_status}' AND NOT obj.category CONTAINS 'trailer'
                RETURN count(obj) as count
            ''').data()
            print(f"     Other things with same status: {r}")
        else:
            print("     ❌ 场景中没有trailer!")
        
        # Q12: barriers to front of trailer, expected: 5
        print("\n[Q12] 'How many barriers are to the front of the trailer?'")
        print("      Expected: 5")
        
        r = s.run('''
            MATCH (trailer:Object)-[r]->(barrier:Object {type:'barrier'})
            WHERE trailer.category CONTAINS 'trailer' AND 'front' IN r.angle_matches_source
            RETURN count(barrier) as count
        ''').data()
        print(f"      Barriers to front: {r}")
        
        # Q13: stopped things to front-left of trailer, expected: 4
        print("\n[Q13] 'How many stopped things are to the front left of the trailer?'")
        print("      Expected: 4")
        
        r = s.run('''
            MATCH (trailer:Object)-[r]->(obj:Object)
            WHERE trailer.category CONTAINS 'trailer' 
              AND 'front-left' IN r.angle_matches_source
              AND obj.status IN ['stopped', 'parked']
            RETURN count(obj) as count
        ''').data()
        print(f"      Stopped things to front-left: {r}")
        
        # Q18: with rider bicycles to front-left of stopped trailer, expected: yes
        print("\n[Q18] 'There is a stopped trailer; are there any with rider bicycles to the front left of it?'")
        print("      Expected: yes")
        
        r = s.run('''
            MATCH (trailer:Object)-[r]->(bike:Object {type:'bicycle'})
            WHERE trailer.category CONTAINS 'trailer' 
              AND trailer.status IN ['stopped', 'parked']
              AND 'front-left' IN r.angle_matches_source
              AND bike.status = 'with_rider'
            RETURN bike.unique_id, bike.status
        ''').data()
        print(f"      With rider bicycles to front-left: {r}")
        
        # Q20: moving thing to front-left of not standing pedestrian, expected: pedestrian
        print("\n[Q20] 'The moving thing that is to the front left of the not standing pedestrian is what?'")
        print("      Expected: pedestrian")
        
        r = s.run('''
            MATCH (ped:Object {type:'pedestrian'})-[r]->(obj:Object)
            WHERE ped.status <> 'standing'
              AND 'front-left' IN r.angle_matches_source
              AND obj.status = 'moving'
            RETURN obj.type, obj.unique_id LIMIT 5
        ''').data()
        print(f"      Moving things to front-left of not-standing ped: {r}")
    
    driver.close()


def verify_scene_0103():
    """验证 scene-0103 frame 38 的错题"""
    config = Neo4jConfig(
        uri='bolt://localhost:7600',
        user='neo4j', 
        password='87017563'
    )
    importer = Neo4jImporter(config)
    
    scene_graph_path = SCENE_GRAPH_DIR / "scene-0103_frame38_scene_graph.json"
    if not scene_graph_path.exists():
        # 尝试生成
        print(f"场景图文件不存在: {scene_graph_path}")
        print("跳过 scene-0103 验证")
        return
    
    print("\n" + "="*60)
    print("导入 scene-0103 frame 38 数据...")
    print("="*60)
    importer.clear_database()
    importer.create_schema()
    with open(scene_graph_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    importer.import_scene(scene_graph)
    
    driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))
    
    print("\n" + "="*60)
    print("验证 scene-0103 frame 38")
    print("="*60)
    
    with driver.session() as s:
        # Q8: bicycle to front-left of truck, expected: without rider
        print("\n[Q8] 'What is the status of the bicycle to the front left of the truck?'")
        print("     Expected: without rider")
        
        r = s.run('''
            MATCH (truck:Object {type:'truck'})-[r]->(bike:Object {type:'bicycle'})
            WHERE 'front-left' IN r.angle_matches_source
            RETURN bike.unique_id, bike.status
        ''').data()
        print(f"     Bicycles to front-left of truck: {r}")
        
        # 检查所有bicycle
        r2 = s.run("MATCH (b:Object {type:'bicycle'}) RETURN b.unique_id, b.status").data()
        print(f"     All bicycles in scene: {r2}")
        
        # 检查truck的所有关系
        r3 = s.run('''
            MATCH (truck:Object {type:'truck'})-[r]->(obj:Object)
            WHERE 'front-left' IN r.angle_matches_source OR 'front' IN r.angle_matches_source OR 'left' IN r.angle_matches_source
            RETURN obj.type, obj.unique_id, r.angle_matches_source
        ''').data()
        print(f"     Objects to front/left of truck: {r3}")
    
    driver.close()


if __name__ == "__main__":
    # 先验证当前场景 (scene-0916)
    verify_scene_0916()
    
    # 然后验证 scene-0553
    verify_scene_0553()
    
    # 最后验证 scene-0103
    verify_scene_0103()
