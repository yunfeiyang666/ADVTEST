from neo4j import GraphDatabase

driver = GraphDatabase.driver('bolt://localhost:7600', auth=('neo4j', '87017563'))

with driver.session() as session:
    # 查看所有not standing的pedestrian
    print('=== Not Standing Pedestrians ===')
    result = session.run('''
        MATCH (p:Object) 
        WHERE p.type='pedestrian' AND p.status<>'standing'
        RETURN p.unique_id, p.status
    ''')
    for r in result:
        print(f"  {r['p.unique_id']}: status={r['p.status']}")
    
    # 查看所有car及其status
    print('\n=== All Cars ===')
    result = session.run('''
        MATCH (c:Object) WHERE c.type='car'
        RETURN c.unique_id, c.status
    ''')
    for r in result:
        print(f"  {r['c.unique_id']}: status={r['c.status']}")
    
    # 查看pedestrian到car的back-right关系 (angle_matches_ego)
    print('\n=== Pedestrian -> Car (back-right in angle_matches_ego) ===')
    result = session.run('''
        MATCH (ped:Object)-[r:RELATES_TO]->(car:Object)
        WHERE ped.type='pedestrian' AND ped.status<>'standing' AND car.type='car'
        AND 'back-right' IN r.angle_matches_ego
        RETURN ped.unique_id, car.unique_id, car.status, r.distance, 
               r.angle_matches_ego, r.angle_matches_source, r.direction_8_ego, r.direction_8_source
        ORDER BY r.distance
    ''')
    for r in result:
        print(f"  {r['ped.unique_id']} -> {r['car.unique_id']}: status={r['car.status']}, dist={r['r.distance']:.1f}")
        print(f"    ego_angles: {r['r.angle_matches_ego']}, dir8={r['r.direction_8_ego']}")
        print(f"    src_angles: {r['r.angle_matches_source']}, dir8={r['r.direction_8_source']}")

    # 查看pedestrian到car的back-right关系 (angle_matches_source)
    print('\n=== Pedestrian -> Car (back-right in angle_matches_source) ===')
    result = session.run('''
        MATCH (ped:Object)-[r:RELATES_TO]->(car:Object)
        WHERE ped.type='pedestrian' AND ped.status<>'standing' AND car.type='car'
        AND 'back-right' IN r.angle_matches_source
        RETURN ped.unique_id, car.unique_id, car.status, r.distance, 
               r.angle_matches_ego, r.angle_matches_source, r.direction_8_ego, r.direction_8_source
        ORDER BY r.distance
    ''')
    for r in result:
        print(f"  {r['ped.unique_id']} -> {r['car.unique_id']}: status={r['car.status']}, dist={r['r.distance']:.1f}")
        print(f"    ego_angles: {r['r.angle_matches_ego']}, dir8={r['r.direction_8_ego']}")
        print(f"    src_angles: {r['r.angle_matches_source']}, dir8={r['r.direction_8_source']}")

    # 查看moving的car在什么方向
    print('\n=== Moving Car - What directions from pedestrian? ===')
    result = session.run('''
        MATCH (ped:Object)-[r:RELATES_TO]->(car:Object)
        WHERE ped.type='pedestrian' AND ped.status<>'standing' AND car.type='car' AND car.status='moving'
        RETURN ped.unique_id, car.unique_id, r.distance, 
               r.angle_matches_ego, r.direction_8_ego
        ORDER BY r.distance
    ''')
    for r in result:
        print(f"  {r['ped.unique_id']} -> {r['car.unique_id']}: dist={r['r.distance']:.1f}")
        print(f"    ego_angles: {r['r.angle_matches_ego']}, dir8={r['r.direction_8_ego']}")

driver.close()
