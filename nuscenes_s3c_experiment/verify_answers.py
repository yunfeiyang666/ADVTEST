"""
验证58道题测试结果 - 检查预期答案是否正确
"""
import json
import sys
sys.path.insert(0, 'E:/Project/ADVTEST/nuscenes_s3c_experiment')

from vqa_pipeline.neo4j_client import Neo4jClient


def load_scene_graph(scene_name: str, frame: int) -> dict:
    """加载场景图JSON"""
    path = f"E:/Project/ADVTEST/nuscenes_s3c_experiment/output/coverage_analysis/scene_graphs/{scene_name}_frame{frame}_scene_graph.json"
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def import_scene_to_neo4j(client: Neo4jClient, scene_graph: dict):
    """导入场景到Neo4j"""
    # 清空数据库
    client.execute_query("MATCH (n) DETACH DELETE n")
    
    # 创建约束
    try:
        client.execute_query("CREATE CONSTRAINT IF NOT EXISTS FOR (o:Object) REQUIRE o.unique_id IS UNIQUE")
    except:
        pass
    
    # 创建节点 (JSON使用'nodes'而不是'objects')
    nodes = scene_graph.get('nodes', scene_graph.get('objects', []))
    for obj in nodes:
        cypher = """
        CREATE (o:Object {
            unique_id: $unique_id,
            type: $type,
            category: $category,
            status: $status
        })
        """
        params = {
            'unique_id': obj.get('unique_id'),
            'type': obj.get('type'),
            'category': obj.get('category', ''),
            'status': obj.get('status', '')
        }
        client.driver.session().run(cypher, params)
    
    # 创建关系 (JSON使用'edges'而不是'relations')
    edges = scene_graph.get('edges', scene_graph.get('relations', []))
    for rel in edges:
        cypher = """
        MATCH (a:Object {unique_id: $from_id})
        MATCH (b:Object {unique_id: $to_id})
        CREATE (a)-[r:RELATES_TO {
            predicates: $predicates,
            direction_4: $direction_4,
            direction_8: $direction_8,
            distance: $distance
        }]->(b)
        """
        # 获取distance - 可能在metrics字典里
        distance = rel.get('distance', 0)
        if 'metrics' in rel and isinstance(rel['metrics'], dict):
            distance = rel['metrics'].get('distance', distance)
        
        params = {
            'from_id': rel.get('from_id', rel.get('source')),
            'to_id': rel.get('to_id', rel.get('target')),
            'predicates': rel.get('predicates', []),
            'direction_4': rel.get('direction_4', ''),
            'direction_8': rel.get('direction_8', ''),
            'distance': distance
        }
        try:
            client.driver.session().run(cypher, params)
        except Exception as e:
            pass
    
    # 验证导入
    result = client.execute_query("MATCH (n:Object) RETURN count(n) as count")
    print(f"  导入对象: {result['data'][0]['count']}")
    result = client.execute_query("MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count")
    print(f"  导入关系: {result['data'][0]['count']}")


def verify_question(client: Neo4jClient, question: str, expected: str, cypher: str):
    """验证单个问题"""
    print(f"\n{'='*60}")
    print(f"问题: {question}")
    print(f"预期答案: {expected}")
    print(f"验证Cypher: {cypher}")
    
    result = client.execute_query(cypher)
    print(f"查询结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    return result


def main():
    client = Neo4jClient()
    if not client.connect():
        print("连接失败")
        return
    
    print("\n" + "="*70)
    print("  场景1: scene-0103 帧38 验证")
    print("="*70)
    
    sg = load_scene_graph("scene-0103", 38)
    import_scene_to_neo4j(client, sg)
    
    # 验证问题4: thing to back-right of motorcycle AND front-left of me
    # 预期: truck
    verify_question(
        client,
        "thing to back-right of motorcycle AND front-left of me",
        "truck",
        """
        // 查看motorcycle的back-right有哪些对象
        MATCH (moto:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE moto.type='motorcycle' OR moto.category CONTAINS 'motorcycle'
        RETURN obj.unique_id, obj.type, obj.status, r.predicates, r.direction_8, r.distance
        ORDER BY r.distance
        LIMIT 20
        """
    )
    
    # 验证问题7: pedestrian to back-right of truck; status?
    # 预期: moving
    verify_question(
        client,
        "pedestrian to back-right of truck; status?",
        "moving",
        """
        // 查看truck的所有方向有哪些pedestrian
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND ped.type='pedestrian'
        RETURN ped.unique_id, ped.status, r.predicates, r.direction_8, r.direction_4
        ORDER BY r.distance
        """
    )
    
    # 验证问题8: bicycle to front-left of truck; status?
    # 预期: without rider
    verify_question(
        client,
        "bicycle to front-left of truck; status?",
        "without rider",
        """
        // 查看truck的所有方向有哪些bicycle
        MATCH (truck:Object)-[r:RELATES_TO]->(bike:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND bike.type='bicycle'
        RETURN bike.unique_id, bike.status, r.predicates, r.direction_8, r.direction_4
        ORDER BY r.distance
        """
    )
    
    # 验证问题9: How many other pedestrians same status as pedestrian to back-right of truck?
    # 预期: 7
    verify_question(
        client,
        "How many other pedestrians same status as pedestrian to back-right of truck?",
        "7",
        """
        // 首先找truck back-right的pedestrian
        MATCH (truck:Object)-[r:RELATES_TO]->(ped:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND ped.type='pedestrian'
          AND r.predicates[0]='back-right'
        WITH ped.status AS refStatus, ped.unique_id AS refId
        LIMIT 1
        // 然后计数同状态的其他pedestrian
        MATCH (other:Object)
        WHERE other.type='pedestrian' AND other.status=refStatus AND other.unique_id<>refId
        RETURN count(other) AS count, refStatus
        """
    )
    
    # 检查所有pedestrian的状态分布
    verify_question(
        client,
        "检查所有pedestrian状态分布",
        "N/A",
        """
        MATCH (p:Object) WHERE p.type='pedestrian'
        RETURN p.status, count(*) as cnt
        ORDER BY cnt DESC
        """
    )
    
    # 验证问题13: Are there any parked cars to the back of the motorcycle?
    # 预期: yes
    verify_question(
        client,
        "Are there any parked cars to the back of the motorcycle?",
        "yes",
        """
        MATCH (moto:Object)-[r:RELATES_TO]->(car:Object)
        WHERE (moto.type='motorcycle' OR moto.category CONTAINS 'motorcycle')
          AND car.type='car' AND car.status='parked'
          AND r.direction_4='back'
        RETURN car.unique_id, car.status, r.predicates, r.direction_4
        """
    )
    
    print("\n" + "="*70)
    print("  场景2: scene-0103 帧25 验证")
    print("="*70)
    
    sg = load_scene_graph("scene-0103", 25)
    import_scene_to_neo4j(client, sg)
    
    # 验证问题8: What status is the car to back-right of not standing pedestrian?
    # 预期: moving
    verify_question(
        client,
        "What status is the car to back-right of not standing pedestrian?",
        "moving",
        """
        // 找not standing pedestrian的back-right的car
        MATCH (ped:Object)-[r:RELATES_TO]->(car:Object)
        WHERE ped.type='pedestrian' AND ped.status <> 'standing'
          AND car.type='car'
          AND r.predicates[0]='back-right'
        RETURN car.unique_id, car.status, r.predicates, r.distance
        ORDER BY r.distance
        """
    )
    
    # 检查所有not standing pedestrian
    verify_question(
        client,
        "检查所有not standing pedestrian",
        "N/A",
        """
        MATCH (p:Object) WHERE p.type='pedestrian' AND p.status <> 'standing'
        RETURN p.unique_id, p.status
        """
    )
    
    print("\n" + "="*70)
    print("  场景3: scene-0553 帧8 验证")
    print("="*70)
    
    sg = load_scene_graph("scene-0553", 8)
    import_scene_to_neo4j(client, sg)
    
    # 验证问题7: What number of other things same status as trailer?
    # 预期: 8
    verify_question(
        client,
        "What number of other things same status as trailer?",
        "8",
        """
        // 找trailer的状态
        MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer'
        WITH trailer.status AS refStatus, trailer.unique_id AS refId LIMIT 1
        // 计数同状态的other things (排除barrier)
        MATCH (other:Object)
        WHERE other.type IN ['ego','car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
          AND other.status = refStatus
          AND other.unique_id <> refId
        RETURN count(other) AS count, refStatus
        """
    )
    
    # 检查trailer的状态
    verify_question(
        client,
        "检查trailer状态",
        "N/A",
        """
        MATCH (t:Object) WHERE t.category CONTAINS 'trailer'
        RETURN t.unique_id, t.status
        """
    )
    
    # 检查所有对象的状态分布
    verify_question(
        client,
        "检查所有对象状态分布",
        "N/A",
        """
        MATCH (o:Object)
        WHERE o.type IN ['ego','car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
        RETURN o.status, count(*) as cnt
        ORDER BY cnt DESC
        """
    )
    
    # 验证问题13: How many stopped things to front-left of trailer?
    # 预期: 4
    verify_question(
        client,
        "How many stopped things to front-left of trailer?",
        "4",
        """
        MATCH (trailer:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE trailer.category CONTAINS 'trailer'
          AND obj.status = 'stopped'
          AND r.predicates[0] = 'front-left'
        RETURN count(obj) AS count
        """
    )
    
    # 查看trailer front-left的所有对象
    verify_question(
        client,
        "查看trailer front-left的所有对象",
        "N/A",
        """
        MATCH (trailer:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE trailer.category CONTAINS 'trailer'
          AND r.predicates[0] = 'front-left'
        RETURN obj.unique_id, obj.type, obj.status
        """
    )
    
    # 验证问题18: stopped trailer; with rider bicycles to front-left?
    # 预期: yes
    verify_question(
        client,
        "stopped trailer; with rider bicycles to front-left?",
        "yes",
        """
        MATCH (trailer:Object)-[r:RELATES_TO]->(bike:Object)
        WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
          AND bike.type='bicycle' AND bike.status='with_rider'
          AND r.predicates[0]='front-left'
        RETURN bike.unique_id, bike.status, r.predicates
        """
    )
    
    # 查看stopped trailer的front-left有哪些对象
    verify_question(
        client,
        "查看stopped trailer的front-left有哪些对象",
        "N/A",
        """
        MATCH (trailer:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
          AND r.predicates[0]='front-left'
        RETURN obj.unique_id, obj.type, obj.status
        """
    )
    
    # 验证问题20: other cars same status as truck front-left of with rider?
    # 预期: yes
    verify_question(
        client,
        "other cars same status as truck front-left of with rider?",
        "yes",
        """
        // 找with_rider对象
        MATCH (wr:Object) WHERE wr.status='with_rider'
        // 找其front-left的truck
        MATCH (wr)-[r:RELATES_TO]->(truck:Object)
        WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND r.predicates[0]='front-left'
        WITH truck.status AS refStatus LIMIT 1
        // 找同状态的car
        MATCH (car:Object) WHERE car.type='car' AND car.status=refStatus
        RETURN count(car) AS count, refStatus
        """
    )
    
    print("\n" + "="*70)
    print("  场景4: scene-0916 帧8 验证")
    print("="*70)
    
    sg = load_scene_graph("scene-0916", 8)
    import_scene_to_neo4j(client, sg)
    
    # 验证问题2-3: moving thing back-right of me AND back-right of bus
    # 预期: pedestrian
    verify_question(
        client,
        "moving thing back-right of me AND back-right of bus",
        "pedestrian",
        """
        // 找同时在ego和bus back-right的moving对象
        MATCH (ego:Object {unique_id:'ego'})-[r1:RELATES_TO]->(obj:Object)
        WHERE r1.predicates[0]='back-right' AND obj.status='moving'
        MATCH (bus:Object)-[r2:RELATES_TO]->(obj)
        WHERE bus.type='bus' AND r2.predicates[0]='back-right'
        RETURN obj.unique_id, obj.type, obj.status
        """
    )
    
    # 查看ego的back-right有哪些moving对象
    verify_question(
        client,
        "查看ego的back-right的moving对象",
        "N/A",
        """
        MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(obj:Object)
        WHERE r.predicates[0]='back-right' AND obj.status='moving'
        RETURN obj.unique_id, obj.type, obj.status, r.distance
        ORDER BY r.distance
        """
    )
    
    # 查看bus的back-right有哪些对象
    verify_question(
        client,
        "查看bus的back-right有哪些对象",
        "N/A",
        """
        MATCH (bus:Object)-[r:RELATES_TO]->(obj:Object)
        WHERE bus.type='bus' AND r.predicates[0]='back-right'
        RETURN obj.unique_id, obj.type, obj.status, r.distance
        ORDER BY r.distance
        """
    )
    
    # 验证问题4-5: truck front-left of bus; status?
    # 预期: parked
    verify_question(
        client,
        "truck front-left of bus; status?",
        "parked",
        """
        MATCH (bus:Object)-[r:RELATES_TO]->(truck:Object)
        WHERE bus.type='bus'
          AND truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND r.predicates[0]='front-left'
        RETURN truck.unique_id, truck.status, r.predicates
        """
    )
    
    # 查看bus的front方向所有truck
    verify_question(
        client,
        "查看bus的front方向所有truck",
        "N/A",
        """
        MATCH (bus:Object)-[r:RELATES_TO]->(truck:Object)
        WHERE bus.type='bus'
          AND truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
          AND r.direction_4='front'
        RETURN truck.unique_id, truck.status, r.predicates, r.direction_4, r.direction_8
        """
    )
    
    client.close()
    print("\n验证完成!")


if __name__ == "__main__":
    main()
