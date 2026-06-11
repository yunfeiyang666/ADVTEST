"""
手动验证问题11和13的ground truth
检查场景图中是否真实存在符合条件的对象
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from import_single_scene_to_neo4j import Neo4jImporter
import json

def check_q11():
    """
    Q11: There is a stopped trailer; are there any with rider bicycles to the front left of it?
    预期答案: yes
    """
    print("\n" + "=" * 70)
    print("检查问题11: 停止的trailer前左方是否有with_rider的bicycle?")
    print("=" * 70)
    
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    
    try:
        with importer.driver.session() as session:
            # 先找到stopped trailer
            result = session.run("""
                MATCH (trailer:Object)
                WHERE trailer.category CONTAINS 'trailer' AND trailer.status = 'stopped'
                RETURN trailer.unique_id AS id, trailer.status AS status
                LIMIT 1
            """)
            trailer_record = result.single()
            if trailer_record:
                print(f"\n✓ 找到停止的trailer: {trailer_record['id']}, status={trailer_record['status']}")
            else:
                print("\n✗ 没有找到停止的trailer!")
                return
            
            # 查找所有与trailer相关的关系
            print("\n查找trailer的所有空间关系:")
            result = session.run("""
                MATCH (trailer:Object {unique_id: $trailer_id})-[r:RELATES_TO]->(obj:Object)
                RETURN obj.type AS type, obj.status AS status, obj.unique_id AS id,
                       r.predicates[0] AS dir8, r.direction_4 AS dir4, r.distance AS dist
                ORDER BY r.distance
            """, trailer_id=trailer_record['id'])
            
            bicycles_found = []
            for record in result:
                print(f"  {record['dir8']:15s} (dir4={record['dir4']:6s}) {record['type']:12s} status={record['status']:15s} dist={record['dist']:.2f} id={record['id']}")
                if record['type'] == 'bicycle':
                    bicycles_found.append(record)
            
            # 特别关注front-left的bicycle
            print("\n筛选: front-left方向的bicycle:")
            front_left_bicycles = [b for b in bicycles_found if b['dir8'] == 'front-left']
            if front_left_bicycles:
                for b in front_left_bicycles:
                    print(f"  ✓ 找到: status={b['status']}, id={b['id']}")
            else:
                print("  ✗ 没有front-left方向的bicycle")
            
            # 检查with_rider的bicycle
            with_rider_bicycles = [b for b in bicycles_found if b['status'] == 'with_rider']
            print(f"\n筛选: with_rider状态的bicycle (任意方向): {len(with_rider_bicycles)}个")
            for b in with_rider_bicycles:
                print(f"  - dir8={b['dir8']}, dir4={b['dir4']}, dist={b['dist']:.2f}")
            
            # 最终判断
            front_left_with_rider = [b for b in bicycles_found if b['dir8'] == 'front-left' and b['status'] == 'with_rider']
            print(f"\n最终结果: front-left + with_rider 的bicycle: {len(front_left_with_rider)}个")
            if front_left_with_rider:
                print("  → 答案应该是: YES")
            else:
                print("  → 答案应该是: NO")
                print("  ⚠️ 这与官方答案(yes)不符，可能是语义问题!")
                
    finally:
        importer.close()


def check_q13():
    """
    Q13: Are there any other cars of the same status as the truck that is to the front left of the with rider thing?
    预期答案: yes
    """
    print("\n" + "=" * 70)
    print("检查问题13: with_rider对象前左方的truck的状态，是否有other cars同状态?")
    print("=" * 70)
    
    importer = Neo4jImporter("bolt://localhost:7600", "neo4j", "87017563")
    
    try:
        with importer.driver.session() as session:
            # 先找到with_rider对象
            result = session.run("""
                MATCH (ref:Object)
                WHERE ref.status = 'with_rider'
                RETURN ref.unique_id AS id, ref.type AS type, ref.status AS status
            """)
            with_rider_objs = list(result)
            print(f"\n✓ 找到{len(with_rider_objs)}个with_rider对象:")
            for obj in with_rider_objs:
                print(f"  - {obj['type']:12s} id={obj['id']}")
            
            # 对每个with_rider对象，找其front-left的truck
            for ref_obj in with_rider_objs:
                print(f"\n检查参考对象: {ref_obj['type']} ({ref_obj['id']})")
                result = session.run("""
                    MATCH (ref:Object {unique_id: $ref_id})-[r:RELATES_TO]->(truck:Object)
                    WHERE truck.type = 'truck' AND NOT truck.category CONTAINS 'trailer'
                          AND r.predicates[0] = 'front-left'
                    RETURN truck.unique_id AS id, truck.status AS status, r.distance AS dist
                    ORDER BY r.distance
                    LIMIT 1
                """, ref_id=ref_obj['id'])
                
                truck_record = result.single()
                if not truck_record:
                    print("  ✗ 没有找到front-left方向的truck")
                    continue
                
                truck_status = truck_record['status']
                print(f"  ✓ 找到truck: id={truck_record['id']}, status={truck_status}, dist={truck_record['dist']:.2f}")
                
                # 查找同状态的cars
                result = session.run("""
                    MATCH (car:Object)
                    WHERE car.type = 'car' AND car.status = $status
                    RETURN car.unique_id AS id, car.status AS status
                """, status=truck_status)
                
                cars = list(result)
                print(f"  查找同状态({truck_status})的cars: {len(cars)}个")
                if cars:
                    print("  → 答案应该是: YES")
                    for car in cars[:3]:  # 只显示前3个
                        print(f"    - car id={car['id']}")
                else:
                    print("  → 答案应该是: NO")
                    print("  ⚠️ 这与官方答案(yes)不符，可能是语义问题!")
                
                break  # 只检查第一个with_rider对象
                
    finally:
        importer.close()


if __name__ == "__main__":
    # 确保scene-0553_frame8已经导入到Neo4j
    print("请确保已经将scene-0553_frame8导入到Neo4j!")
    print("如果没有，请先运行: python test_failed_cases_retest.py")
    
    check_q11()
    check_q13()
