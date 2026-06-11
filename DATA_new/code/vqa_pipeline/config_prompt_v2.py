"""
精简优化后的Prompt配置 - V2
目标：减少冗余，提升LLM生成准确性
"""

# ============ 场景图Schema（精简版）============
SCENE_GRAPH_SCHEMA_V2 = """
Neo4j场景图Schema:

节点 (Label: Object):
- unique_id: 对象唯一标识 (如'ego', 'car1', 'pedestrian1')
- type: 对象类型 (ego/car/truck/bus/bicycle/pedestrian/barrier/motorcycle/trailer)
- category: NuScenes类别 (如'vehicle.car', 'vehicle.trailer', 'vehicle.motorcycle')
- status: 对象状态 (stopped/moving/with_rider/without_rider/parked/standing/unknown)
⚠️ 不存在translation/rotation/velocity等属性，不要访问

关系 (Type: RELATES_TO):
- predicates: [方位, 距离级别]
  * predicates[0]: 8方位 'front'/'front-left'/'left'/'back-left'/'back'/'back-right'/'right'/'front-right'
  * predicates[1]: 距离级别 'near'(≤10m)/'mid'(10-25m)/'far'(>25m)
- direction_4: 4方位 'front'/'left'/'back'/'right' (±45°范围)
- direction_8: 8方位，同predicates[0] (±22.5°范围)
- distance: 精确距离（米）

方位选择规则（重要）:
- 问题用单一方位词(front/back/left/right) → 使用 r.direction_4
  例: "truck to the back of me" → WHERE r.direction_4 = 'back'
- 问题用复合方位词(front-left/back-right等) → 使用 r.predicates[0]
  例: "bicycle to the front-left" → WHERE r.predicates[0] = 'front-left'

特殊类型处理:
- trailer: WHERE n.category CONTAINS 'trailer'
- truck(不含trailer): WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
- motorcycle: WHERE n.type='motorcycle' OR n.category CONTAINS 'motorcycle'

方位语义（参照物关系）:
"the X to the <direction> of Y" → Y是参照物，X是目标
Cypher写法: MATCH (Y)-[r:RELATES_TO]->(X) WHERE r.<direction_field>='<direction>'
例: "truck to the back right of bicycle"
    MATCH (bicycle)-[r:RELATES_TO]->(truck) WHERE r.predicates[0]='back-right'
"""

# ============ 简化Prompt模板 ============
QUESTION_TO_CYPHER_PROMPT_V2 = """你是Neo4j Cypher查询专家。根据自然语言问题生成Cypher查询。

{schema}

用户问题: {question}
问题类型: {question_type}
上次错误: {prev_error}

核心规则:
1. 对象类型: ego, car, truck, bus, bicycle, pedestrian, barrier, motorcycle, trailer
2. trailer查询: WHERE n.category CONTAINS 'trailer'
   truck查询(不含trailer): WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
3. motorcycle查询: WHERE n.type='motorcycle' OR n.category CONTAINS 'motorcycle'
4. "other things" 默认指: [ego,car,truck,bus,bicycle,motorcycle,trailer,pedestrian]，不含barrier
5. 状态查询用status属性: WHERE n.status='with_rider'/'stopped'等
6. 多个候选时按距离排序: ORDER BY r.distance ASC LIMIT 1

方位语义（极其重要）:
- "X to the <dir> of Y" → Y是参照物: MATCH (Y)-[r]->(X) WHERE r.<dir_field>='<dir>'
- 4方位词 → 用 r.direction_4
- 8方位词 → 用 r.predicates[0]

输出约束:
1. 只生成一条查询，只有一个RETURN
2. 不允许RETURN后再有新的MATCH/RETURN
3. 用【CYPHER】...【/CYPHER】包裹查询

模式A: 双参照物状态比较 (comparison题型)
问题形式: "Is status of OBJ1 to DIR1 of REF1 same as OBJ2 to DIR2 of REF2?"
Cypher模板:
MATCH (ref1:Object) WHERE <ref1_constraints>
MATCH (ref1)-[r1:RELATES_TO]->(obj1:Object) WHERE <obj1_constraints> AND <dir1>
WITH ref1, obj1, r1 ORDER BY r1.distance ASC LIMIT 1

MATCH (ref2:Object) WHERE <ref2_constraints>  
MATCH (ref2)-[r2:RELATES_TO]->(obj2:Object) WHERE <obj2_constraints> AND <dir2>
WITH obj1, obj2, r2 ORDER BY r2.distance ASC LIMIT 1

RETURN obj1.status = obj2.status AS same_status

模式B: 同状态其他对象 (count_same_status题型)
问题形式: "How many other X have same status as REF_TARGET to DIR of REF?"
Cypher模板:
MATCH (ref:Object) WHERE <ref_constraints>
MATCH (ref)-[r1:RELATES_TO]->(ref_target:Object) WHERE <ref_target_constraints> AND <dir>
WITH ref_target, r1 ORDER BY r1.distance ASC LIMIT 1
WITH ref_target.status AS refStatus, ref_target.unique_id AS refId

MATCH (other:Object)
WHERE other.type='<target_type>' 
  AND other.status=refStatus 
  AND other.unique_id<>refId
RETURN count(other) AS count

模式C: 多锚点交集 (object题型)
问题形式: "What is thing to DIR1 of REF1 and DIR2 of REF2?"
Cypher模板:
MATCH (ref1:Object) WHERE <ref1_constraints>
MATCH (ref2:Object) WHERE <ref2_constraints>
MATCH (ref1)-[r1:RELATES_TO]->(target:Object) WHERE <dir1>
MATCH (ref2)-[r2:RELATES_TO]->(target) WHERE <dir2>
WITH target, r1, r2 ORDER BY r1.distance+r2.distance ASC LIMIT 1
RETURN target.unique_id, target.type, target.status

Few-shot示例（5个关键示例）:

【示例1 - 双参照物比较 (Pattern A)】
问题: "Is status of bus to back right of not standing pedestrian same as bus to front of stopped trailer?"

【CYPHER_EXAMPLE】
MATCH (ped:Object) WHERE ped.type='pedestrian' AND ped.status<>'standing'
MATCH (ped)-[r1:RELATES_TO]->(bus1:Object) WHERE bus1.type='bus' AND r1.predicates[0]='back-right'
WITH ped, bus1, r1 ORDER BY r1.distance ASC LIMIT 1

MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (trailer)-[r2:RELATES_TO]->(bus2:Object) WHERE bus2.type='bus' AND r2.direction_4='front'
WITH bus1, bus2, r2 ORDER BY r2.distance ASC LIMIT 1

RETURN bus1.status=bus2.status AS same_status
【/CYPHER_EXAMPLE】

【示例2 - 同状态计数 (Pattern B)】
问题: "How many other bicycles same status as barrier to front left of bicycle?"

【CYPHER_EXAMPLE】
MATCH (refBike:Object {type:'bicycle'}) WITH refBike LIMIT 1
MATCH (refBike)-[r:RELATES_TO]->(barrierObj:Object)
WHERE barrierObj.type='barrier' AND r.predicates[0]='front-left'
WITH refBike, barrierObj, r ORDER BY r.distance ASC LIMIT 1
WITH barrierObj.status AS barrierStatus, refBike.unique_id AS refBikeId

MATCH (otherBike:Object)
WHERE otherBike.type='bicycle' 
  AND otherBike.status=barrierStatus 
  AND otherBike.unique_id<>refBikeId
RETURN count(otherBike) AS count
【/CYPHER_EXAMPLE】

【示例3 - 多锚点交集 (Pattern C)】
问题: "What is thing to back right of stopped trailer and back of stopped truck?"

【CYPHER_EXAMPLE】
MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (truck:Object) WHERE truck.type='truck' AND truck.status='stopped' AND NOT truck.category CONTAINS 'trailer'
MATCH (trailer)-[r1:RELATES_TO]->(target:Object) WHERE r1.predicates[0]='back-right'
MATCH (truck)-[r2:RELATES_TO]->(target) WHERE r2.direction_4='back'
WITH target, r1, r2 ORDER BY r1.distance+r2.distance ASC LIMIT 1
RETURN target.unique_id, target.type, target.status
【/CYPHER_EXAMPLE】

【示例4 - "other things"同状态存在性查询】
问题: "Are there other things that in same status as truck?"

【CYPHER_EXAMPLE】
MATCH (refTruck:Object) WHERE refTruck.type='truck' AND NOT refTruck.category CONTAINS 'trailer'
WITH refTruck.status AS refStatus, refTruck.unique_id AS refId LIMIT 1

MATCH (other:Object)
WHERE other.type IN ['ego','car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
  AND other.status=refStatus
  AND (other.type<>'truck' OR other.unique_id<>refId)
RETURN count(other)>0 AS exist
【/CYPHER_EXAMPLE】

【示例5 - 前方对象计数】
问题: "How many barriers are to front of trailer?"

【CYPHER_EXAMPLE】
MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer' WITH trailer LIMIT 1
MATCH (trailer)-[r:RELATES_TO]->(barrier:Object) WHERE barrier.type='barrier' AND r.direction_4='front'
RETURN count(barrier) AS barrier_count
【/CYPHER_EXAMPLE】

输出格式:
【CYPHER】
<你的唯一一条查询>
【/CYPHER】
"""
