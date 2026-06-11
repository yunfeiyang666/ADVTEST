"""
详细错误分析脚本
逐一验证每道错题，确定是LLM问题还是数据/语义问题
"""
import json
from pathlib import Path
from neo4j import GraphDatabase

# Neo4j连接配置
NEO4J_URI = "bolt://localhost:7600"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "87017563"

def get_driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def run_query(driver, cypher):
    """执行Cypher查询"""
    with driver.session() as session:
        result = session.run(cypher)
        return [dict(record) for record in result]

def load_scene_to_neo4j(driver, scene_path):
    """加载场景到Neo4j"""
    with open(scene_path, 'r', encoding='utf-8') as f:
        scene_graph = json.load(f)
    
    nodes = scene_graph['nodes']
    edges = scene_graph['edges']
    
    with driver.session() as session:
        # 清空数据库
        session.run("MATCH (n) DETACH DELETE n")
        
        # 创建节点
        for n in nodes:
            session.run("""
                CREATE (o:Object {
                    unique_id: $uid,
                    type: $type,
                    status: $status,
                    category: $category
                })
            """, uid=n['unique_id'], type=n['type'], 
                status=n.get('status', 'unknown'),
                category=n.get('category', ''))
        
        # 创建关系
        for e in edges:
            session.run("""
                MATCH (s:Object {unique_id: $source})
                MATCH (t:Object {unique_id: $target})
                CREATE (s)-[r:RELATES_TO {
                    predicates: $predicates,
                    direction_4: $direction_4,
                    direction_8: $direction_8,
                    distance: $distance
                }]->(t)
            """, source=e['source'], target=e['target'],
                predicates=e.get('predicates', []),
                direction_4=e.get('direction_4', ''),
                direction_8=e.get('direction_8', ''),
                distance=e.get('distance', 0))
    
    return len(nodes), len(edges)

def analyze_error(driver, question, expected, actual, generated_cypher, scene_name):
    """分析单个错误"""
    print(f"\n{'='*70}")
    print(f"问题: {question}")
    print(f"预期: {expected}")
    print(f"实际: {actual}")
    print(f"场景: {scene_name}")
    print("-"*70)
    
    # 尝试重新执行生成的Cypher
    print(f"生成的Cypher:\n{generated_cypher}")
    print("-"*40)
    
    try:
        result = run_query(driver, generated_cypher)
        print(f"Cypher执行结果: {result}")
    except Exception as e:
        print(f"Cypher执行错误: {e}")
        return "cypher_error"
    
    # 分析错误类型
    if not result:
        return "empty_result"
    
    return "result_mismatch"

def main():
    """主函数"""
    print("="*70)
    print("  详细错误分析")
    print("="*70)
    
    # 从日志中提取的错误案例
    # 格式: (scene_file, question, expected, actual, cypher)
    errors = [
        # scene-0103_frame25 (3错)
        (
            "output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json",
            "scene-0103_frame25",
            "There is a truck; what status is it?",
            "parked",
            "stopped",
            "MATCH (truck:Object) WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer' RETURN truck.status AS status LIMIT 1"
        ),
        (
            "output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json",
            "scene-0103_frame25",
            "What status is the car to the back right of the not standing pedestrian?",
            "moving",
            "stopped",
            """MATCH (ped:Object) WHERE ped.type='pedestrian' AND ped.status<>'standing'
MATCH (ped)-[r:RELATES_TO]->(car:Object)
WHERE car.type='car' AND r.predicates[0]='back-right'
WITH car, r ORDER BY r.distance ASC LIMIT 1
RETURN car.status"""
        ),
        (
            "output/coverage_analysis/scene_graphs/scene-0103_frame25_scene_graph.json",
            "scene-0103_frame25",
            "There is a car to the back right of the not standing pedestrian; what is its status?",
            "moving",
            "stopped",
            """MATCH (ped:Object) WHERE ped.type='pedestrian' AND ped.status<>'standing'
MATCH (ped)-[r:RELATES_TO]->(car:Object) 
WHERE car.type='car' AND r.predicates[0]='back-right'
WITH car, r ORDER BY r.distance ASC LIMIT 1
RETURN car.status"""
        ),
        
        # scene-0103_frame38 (7错)
        (
            "output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json",
            "scene-0103_frame38",
            "What is the status of the truck?",
            "parked",
            "stopped",
            "MATCH (truck:Object) WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer' RETURN truck.status LIMIT 1"
        ),
        (
            "output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json",
            "scene-0103_frame38",
            "There is a thing that is to the back right of the without rider motorcycle and the front left of me; what is it?",
            "truck",
            "未找到",
            """MATCH (motorcycle:Object) WHERE (motorcycle.type='motorcycle' OR motorcycle.category CONTAINS 'motorcycle') AND motorcycle.status='without_rider'
MATCH (ego:Object) WHERE ego.unique_id='ego'
MATCH (motorcycle)-[r1:RELATES_TO]->(target:Object) WHERE r1.predicates[0]='back-right'
MATCH (ego)-[r2:RELATES_TO]->(target) WHERE r2.predicates[0]='front-left'
WITH target, r1, r2 ORDER BY r1.distance + r2.distance ASC LIMIT 1
RETURN target.unique_id, target.type, target.status"""
        ),
        (
            "output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json",
            "scene-0103_frame38",
            "There is a parked thing that is to the back right of the without rider motorcycle and the front left of me; what is it?",
            "truck",
            "未找到",
            """MATCH (motorcycle:Object) WHERE (motorcycle.type='motorcycle' OR motorcycle.category CONTAINS 'motorcycle') AND motorcycle.status='without_rider'
MATCH (ego:Object) WHERE ego.unique_id='ego'
MATCH (motorcycle)-[r1:RELATES_TO]->(target:Object) WHERE r1.predicates[0]='back-right'
MATCH (ego)-[r2:RELATES_TO]->(target) WHERE r2.predicates[0]='front-left' AND target.status='parked'
WITH target, r1, r2 ORDER BY r1.distance + r2.distance ASC LIMIT 1
RETURN target.unique_id, target.type, target.status"""
        ),
        (
            "output/coverage_analysis/scene_graphs/scene-0103_frame38_scene_graph.json",
            "scene-0103_frame38",
            "There is a pedestrian to the back right of the truck; what is its status?",
            "moving",
            "未找到",
            """MATCH (truck:Object) WHERE truck.type='truck' AND NOT truck.category CONTAINS 'trailer'
MATCH (truck)-[r:RELATES_TO]->(pedestrian:Object) 
WHERE pedestrian.type='pedestrian' AND r.predicates[0]='back-right'
WITH pedestrian, r ORDER BY r.distance ASC LIMIT 1
RETURN pedestrian.status"""
        ),
    ]
    
    driver = get_driver()
    
    current_scene = None
    
    for scene_file, scene_name, question, expected, actual, cypher in errors:
        # 如果场景变了，重新加载
        if current_scene != scene_name:
            print(f"\n>>> 加载场景: {scene_name}")
            nodes, edges = load_scene_to_neo4j(driver, scene_file)
            print(f"    已加载 {nodes} 节点, {edges} 条关系")
            current_scene = scene_name
        
        error_type = analyze_error(driver, question, expected, actual, cypher, scene_name)
        print(f"\n错误类型: {error_type}")
        
        # 补充分析
        if "back-right" in question and "pedestrian" in question.lower():
            # 检查实际有哪些pedestrian的back-right有car
            print("\n--- 补充验证: 检查所有not standing pedestrian的back-right方向 ---")
            check_cypher = """
MATCH (ped:Object) WHERE ped.type='pedestrian' AND ped.status<>'standing'
MATCH (ped)-[r:RELATES_TO]->(car:Object)
WHERE car.type='car' AND r.predicates[0]='back-right'
RETURN ped.unique_id, car.unique_id, car.status, r.distance
ORDER BY r.distance
LIMIT 10
"""
            try:
                check_result = run_query(driver, check_cypher)
                print(f"有back-right方向car的pedestrian:")
                for row in check_result:
                    print(f"  {row}")
            except Exception as e:
                print(f"验证查询错误: {e}")
    
    driver.close()
    print("\n" + "="*70)
    print("分析完成")
    print("="*70)

if __name__ == "__main__":
    main()
