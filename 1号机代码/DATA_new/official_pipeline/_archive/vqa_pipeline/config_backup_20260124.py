"""
VQA Pipeline 配置文件
元景大模型MaaS平台 - DeepSeek-R1 API配置
"""

# ============ API配置 ============
# 元景大模型平台API配置（兼容OpenAI格式）
API_BASE_URL = "https://maas-api.ai-yuanjing.com/openapi/compatible-mode/v1"
API_KEY = "sk-ecd91655d033446b9ae8ea390e65d923"
APP_ID = "61cb0d25ba9049d284ff68f9941481be"
MODEL_NAME = "deepseek-r1"  # DeepSeek-R1 满血版 671B

# API请求配置
REQUEST_TIMEOUT = 120  # 超时时间（秒）
MAX_RETRIES = 3        # 最大重试次数

# ============ Neo4j配置 ============
NEO4J_URI = "bolt://localhost:7600"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "87017563"

# ============ 场景图Schema描述 ============
SCENE_GRAPH_SCHEMA = """
Neo4j场景图数据库Schema:

节点类型 (Label: Object):
- unique_id: 对象唯一标识符 (如 'ego', 'car1', 'pedestrian1')
- type: 对象类型 (ego/car/truck/bus/bicycle/pedestrian/barrier/motorcycle/trailer)
- category: 原始NuScenes类别 (如 'vehicle.car', 'vehicle.truck', 'vehicle.trailer', 'vehicle.motorcycle')
- status: 离散对象状态 (stopped/moving/with_rider/without_rider/parked/standing/unknown 等)
- attributes: NuScenes原始属性标签列表 (如 'vehicle.moving', 'pedestrian.standing')

⚠️ 注意：
- 不存在 translation/rotation/size/velocity 这类整体属性字段，请不要在Cypher中访问 n.translation 或 n.velocity；
- 速度/位置等低层信息已经被离散到 status 和 RELATES_TO 关系中。

关系类型 (Type: RELATES_TO):
- predicates: 离散化空间关系数组，固定格式 [方位, 距离级别]
  - predicates[0] = 方位 (8方位): 'front'/'front-left'/'left'/'back-left'/'back'/'back-right'/'right'/'front-right'
  - predicates[1] = 距离级别: 'near'(≤10m)/'mid'(10-25m)/'far'(>25m)
- direction_4: 4方位方向（宽泛，每个方位90°）: 'front'/'left'/'back'/'right'
- direction_8: 8方位方向（精确，每个方位45°）: 'front'/'front-left'/...
- distance: 精确距离（米，浮点数）
- angle: 相对角度（度）

❗❗❗ 方位系统选择规则（极其重要）:
问题中的方位词决定使用哪个字段:
- 如果问题用 4方位词 (front/back/left/right且没有复合方位):
  → 使用 r.direction_4 字段，范围是±45°
  例如: "truck to the back of me" → WHERE r.direction_4 = 'back'
- 如果问题用 8方位词 (front-left/back-right等复合方位):
  → 使用 r.predicates[0] 或 r.direction_8 字段，范围是±22.5°
  例如: "bicycle to the front-left" → WHERE r.predicates[0] = 'front-left'

8方位定义（精确，±22.5°）:
- front: 正前方 | front-left: 左前方 | left: 正左方 | back-left: 左后方
- back: 正后方 | back-right: 右后方 | right: 正右方 | front-right: 右前方

4方位定义（宽泛，±45°）:
- front: 前方（包含front-left和front-right的部分）
- back: 后方（包含back-left和back-right的部分）
- left: 左方 | right: 右方

重要查询模式:
- 4方位查询: WHERE r.direction_4 = 'back' (范围宽，包含±45°)
- 8方位查询: WHERE r.predicates[0] = 'front-left' (精确匹配)
- 查询距离级别用: WHERE r.predicates[1] = 'near'
- 查询精确距离用: WHERE r.distance < 10
- 不要用 {predicates: [...]} 精确匹配，因为数组有两个元素

方位转换规则（将自然语言转为数据库方位）:
- "back right"/"rear right" → predicates[0] = 'back-right'
- "front left" → predicates[0] = 'front-left'
- "back left"/"rear left" → predicates[0] = 'back-left'
- "front right" → predicates[0] = 'front-right'
- "back"/"rear" → predicates[0] = 'back'
- "front" → predicates[0] = 'front'

示例Cypher:
1. 查ego前方对象: MATCH (ego:Object {unique_id:'ego'})-[r:RELATES_TO]->(obj:Object) WHERE r.predicates[0]='front' RETURN obj.unique_id, obj.type, obj.status
2. 统计车辆数: MATCH (n:Object) WHERE n.type='car' RETURN count(n) AS car_count
3. 查询某类对象状态: MATCH (b:Object {type:'bicycle'}) RETURN b.unique_id, b.status
4. 比较两个对象是否同一状态: MATCH (a:Object {unique_id:'car1'}), (b:Object {unique_id:'car2'}) RETURN a.status = b.status AS same_status
5. 存在性查询(推荐): MATCH (n:Object) WHERE n.type='truck' RETURN count(n) > 0 AS exist
6. 多跳查询: MATCH (a:Object {type:'truck', status:'moving'})-[r:RELATES_TO]->(b:Object {type:'truck'}) WHERE r.predicates[0]='rear' RETURN b.status
7. 查询trailer(重要): MATCH (t:Object) WHERE t.category CONTAINS 'trailer' RETURN t.unique_id, t.status
8. "the trailer"的状态: MATCH (t:Object) WHERE t.category CONTAINS 'trailer' RETURN t.status LIMIT 1
"""

# ============ Prompt模板 ============
QUESTION_TO_CYPHER_PROMPT = """你是一个专业的Neo4j Cypher查询专家。根据用户的自然语言问题，生成对应的Cypher查询语句。

场景图数据库Schema:
{schema}

节点核心属性:
- unique_id: 对象唯一标识
- type: 对象类型 (ego, car, truck, bus, bicycle, pedestrian, barrier)
- status: 对象状态 (stopped, moving, with_rider, without_rider, parked, standing, unknown)
- attributes: 原始NuScenes属性标签列表 (如 'vehicle.moving', 'pedestrian.standing')

用户问题: {question}
问题类型: {question_type}
上一次错误信息(如果是重试且有错误提示，请参考并避免同样问题): {prev_error}

重要提醒：
- 🔧 对象类型：ego, car, truck, bus, bicycle, pedestrian, barrier, motorcycle, trailer
- 🔧 trailer特殊处理：问题中的 "trailer" 对应数据库中 category 包含 'trailer' 的对象
  - 查询trailer: WHERE n.category CONTAINS 'trailer' 或 n.type = 'trailer'
  - 查询truck(不含trailer): WHERE n.type = 'truck' AND NOT n.category CONTAINS 'trailer'
- 🔧 motorcycle：问题中的 "motorcycle" 对应数据库中 category 包含 'motorcycle' 的对象
  - 查询motorcycle: WHERE n.category CONTAINS 'motorcycle' 或 n.type = 'motorcycle'
- 🔧 "other things" 语义：在同状态/相同状态计数类问题中，"other things" 默认只指动态对象类型
  [ego, car, truck, bus, bicycle, motorcycle, trailer, pedestrian]，不包括 barrier。
- 🔧 状态查询：一律使用节点属性 status，例如 WHERE n.status = 'with_rider' 或 'stopped'，
  不要用 type 来近似表示状态（禁止用 n.type 代替 n.status 来表示 "same status"）。
  对于 "What status is ..." / "What status is the X to the ... of Y?" 这类问题：
  - 查询时如果可能匹配多条记录，应按距离升序排序并使用 LIMIT 1，仅返回最近的一个对象的 status。
    例如：先 MATCH 参考对象 ref，再 MATCH ref 到目标 obj 的 RELATES_TO 关系，最后按照 r.distance 升序排序并使用 LIMIT 1 只取最近的一个，再返回 obj.status。
- ❌ 不要访问不存在的属性：不要使用 n.translation / n.rotation / n.size / n.velocity 等字段

❗❗❗ 方位系统选择规则（极其重要):
- 4方位词（front/back/left/right单独使用）: 使用 r.direction_4 字段
  例如: "truck to the back of me" → WHERE r.direction_4 = 'back'
- 8方位词（front-left/back-right等复合方位）: 使用 r.predicates[0] 字段
  例如: "bicycle to the front-left" → WHERE r.predicates[0] = 'front-left'
- 距离级别：near, mid, far (使用 r.predicates[1])

🧭 方位语义约定（谁是参照物，极其重要）：
- 句式 "the X to the <direction> of Y" 中：
  - Y 是参照物 (reference object)，X 是被描述的目标对象 (target object)
  - Cypher 必须写成：MATCH (Y)-[r:RELATES_TO]->(X) WHERE r.predicates[0] = '<direction8>' 或 r.direction_4 = '<direction4>'
  - 也就是说：参照物在 MATCH 箭头的左边，被描述对象在箭头右边
- 例如：
  - "the truck to the back right of the bicycle" → 以自行车为参照：
    MATCH (bicycle:Object {{type:'bicycle'}})
    MATCH (bicycle)-[r:RELATES_TO]->(truck:Object)
    WHERE truck.type='truck' AND r.predicates[0]='back-right'
  - "the bus to the front of the stopped trailer" → 以 trailer 为参照：
    MATCH (trailer:Object) WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
    MATCH (trailer)-[r:RELATES_TO]->(bus:Object)
    WHERE bus.type='bus' AND r.direction_4='front'
  - "truck to the back of me" → 以 ego (me) 为参照：
    MATCH (ego:Object {{unique_id:'ego'}})
    MATCH (ego)-[r:RELATES_TO]->(truck:Object)
    WHERE truck.type='truck' AND r.direction_4='back'

结构约束（非常重要）：
1. 只能生成 **一条** 可执行的Cypher查询，不要在同一个回答中给出多个候选查询。
2. 整个回答中只能有 **一个最终的 RETURN 子句**，且 RETURN 必须出现在查询的最后一行。
3. 不允许在 RETURN 之后再写新的 MATCH/CREATE/MERGE/CALL/RETURN 语句。
4. 如需多跳关系，请在一条查询中串联多个 MATCH，而不是写多条独立查询。

唯一引用模式（非常重要）：
- "the X" 表示场景中唯一的或可唯一确定的对象，通常只有一个满足条件
- "There is a X" 介绍一个特定对象，后续用 "it" 引用
- "the trailer" 表示场景中唯一的trailer，用 WHERE n.category CONTAINS 'trailer' LIMIT 1 查询
- "the stopped truck" 表示特定状态的对象，可能有多个，但问题假设可以唯一确定

示例:
   MATCH (a:Object) WHERE a.type='truck'
   MATCH (a)-[r1:RELATES_TO]->(b:Object) WHERE b.type='truck'
   WHERE r1.predicates[0] = 'rear'
   RETURN b.status

复杂比较题典型示例1（与第8题结构类似，务必学习这种拆解方式）:
自然语言问题:
"Is the status of the bus to the back right of the not standing pedestrian the same as the bus that is to the front of the stopped trailer?"

分析步骤(仅用于你在内部思考，不需要输出给用户):
1. 找到 not standing 的行人 ped:
   - 约束: type='pedestrian' 且 status<>'standing'。
2. 找到该行人 back-right 方向最近的公交车 bus1:
   - MATCH (ped)-[r1:RELATES_TO]->(bus1)
   - 约束: bus1.type='bus' 且 r1.predicates[0]='back-right'
   - 如果有多辆, 按 r1.distance 升序排序并 LIMIT 1。
3. 找到 stopped 的拖车 trailer:
   - 约束: category CONTAINS 'trailer' 且 status='stopped'。
4. 找到 trailer 前方最近的公交车 bus2:
   - MATCH (trailer)-[r2:RELATES_TO]->(bus2)
   - 约束: bus2.type='bus' 且 r2.direction_4='front'
   - 多辆时同样按 r2.distance 升序排序并 LIMIT 1。
5. 比较 bus1.status 和 bus2.status 是否相等, 返回布尔值 same_status。

对应的标准Cypher写法(只保留这一条最终查询):
MATCH (ped:Object)
WHERE ped.type='pedestrian' AND ped.status <> 'standing'
MATCH (ped)-[r1:RELATES_TO]->(bus1:Object)
WHERE bus1.type='bus' AND r1.predicates[0]='back-right'
WITH ped, bus1, r1
ORDER BY r1.distance ASC
LIMIT 1

MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (trailer)-[r2:RELATES_TO]->(bus2:Object)
WHERE bus2.type='bus' AND r2.direction_4='front'
WITH bus1, bus2, r2
ORDER BY r2.distance ASC
LIMIT 1

RETURN bus1.status = bus2.status AS same_status

复杂比较题典型示例2（结构相同，仅对象不同，用于泛化）:
自然语言问题:
"Is the status of the truck to the front left of the with rider bicycle the same as the truck that is to the back of the stopped trailer?"

拆解方式与上例完全相同，只是对象/方位不同：
- 参考1: with rider 的 bicycle b, 目标1: 在 b front-left 的 truck1;
- 参考2: stopped 的 trailer, 目标2: 在 trailer back 的 truck2;
- 最后比较 truck1.status 与 truck2.status。

对应Cypher示例:
MATCH (b:Object)
WHERE b.type='bicycle' AND b.status='with_rider'
MATCH (b)-[r1:RELATES_TO]->(truck1:Object)
WHERE truck1.type='truck' AND r1.predicates[0]='front-left'
WITH b, truck1, r1
ORDER BY r1.distance ASC
LIMIT 1

MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer' AND trailer.status='stopped'
MATCH (trailer)-[r2:RELATES_TO]->(truck2:Object)
WHERE truck2.type='truck' AND r2.direction_4='back'
WITH truck1, truck2, r2
ORDER BY r2.distance ASC
LIMIT 1

RETURN truck1.status = truck2.status AS same_status

抽象模式A：两个通过空间关系定义的对象的状态比较（适用于大多数 comparison 题）:
- 一般问题形式（英文示意，不对应具体数据集原题）：
  "Is the status of OBJ1 that is to the DIR1 of REF1
   the same as the status of OBJ2 that is to the DIR2 of REF2?"

- 抽象拆解步骤：
  1. 根据属性约束分别选出参考对象 REF1、REF2（例如某个行人、某个拖车）。
  2. 用统一模式 MATCH (REF1)-[r1:RELATES_TO]->(OBJ1)，并用 DIR1 约束 r1 的方向；
  3. 同理 MATCH (REF2)-[r2:RELATES_TO]->(OBJ2)，并用 DIR2 约束 r2 的方向；
  4. 如果存在多个候选 OBJ1/OBJ2，对每侧分别按 r1.distance / r2.distance 升序排序并 LIMIT 1，只取最近的一个；
  5. 最后比较 OBJ1.status 和 OBJ2.status 是否相等，返回布尔值 same_status。

- 抽象Cypher模板示例（占位符需在具体题目中替换）：
  MATCH (ref1:Object)
  WHERE <constraints_on_ref1>
  MATCH (ref2:Object)
  WHERE <constraints_on_ref2>
  MATCH (ref1)-[r1:RELATES_TO]->(obj1:Object)
  WHERE obj1.type = '<OBJ1_TYPE>' AND <dir_condition_on_r1>
  WITH ref1, obj1, r1
  ORDER BY r1.distance ASC
  LIMIT 1
  MATCH (ref2)-[r2:RELATES_TO]->(obj2:Object)
  WHERE obj2.type = '<OBJ2_TYPE>' AND <dir_condition_on_r2>
  WITH obj1, obj2, r2
  ORDER BY r2.distance ASC
  LIMIT 1
  RETURN obj1.status = obj2.status AS same_status

抽象模式B：先通过空间关系定义一个参考对象，再查找“same status 的其他对象”（适用于 another X / other X of the same status as ...）:
- 一般问题形式（英文示意）：
  "Is there another TARGET_TYPE of the same status as the REF_TARGET
   that is to the DIR of REF?"

- 抽象拆解步骤：
  1. 根据属性约束选出参考对象 REF（例如 status='with_rider' 的某个对象）；
  2. 通过空间关系找到 REF_TARGET：MATCH (REF)-[r1:RELATES_TO]->(REF_TARGET)，按 DIR 约束 r1 并按 r1.distance 升序 LIMIT 1；
  3. 记录 REF_TARGET 的 status 和 unique_id，例如：WITH REF_TARGET.status AS refStatus, REF_TARGET.unique_id AS refId；
  4. 再 MATCH 其它对象 other，要求 other.type 为目标类型，且 other.status = refStatus，并排除自身（other.unique_id <> refId）；
  5. 返回是否存在这样的对象：count(other) > 0 AS exist。

- 抽象Cypher模板示例：
  MATCH (ref:Object)
  WHERE <constraints_on_ref>          -- 例如 ref.status='with_rider'
  MATCH (ref)-[r1:RELATES_TO]->(ref_target:Object)
  WHERE ref_target.type = '<REF_TARGET_TYPE>' AND <dir_condition_on_r1>
  WITH ref_target, r1
  ORDER BY r1.distance ASC
  LIMIT 1
  WITH ref_target.status AS refStatus, ref_target.unique_id AS refId
  MATCH (other:Object)
  WHERE other.type = '<TARGET_TYPE>'
    AND other.status = refStatus
    AND other.unique_id <> refId
  RETURN count(other) > 0 AS exist

# ==========================
# Few-shot 示例集合 (15题)
# 说明：
# - 以下示例均使用【THINK】块描述思路，使用【CYPHER_EXAMPLE】块给出标准Cypher，仅供你学习结构和约束方式；
# - 在真正回答用户问题时，你必须使用【CYPHER】...【/CYPHER】包裹你生成的唯一一条查询。
# - 请特别注意：参照物在 MATCH 左侧，目标对象在右侧；复合方位用 r.predicates[0]，4向方位用 r.direction_4。
# ==========================

【示例1 - Pattern A: Q8 官方难题（bus vs bus, scene-0553_frame8）】
自然语言问题:
"Is the status of the bus to the back right of the not standing pedestrian the same as the bus that is to the front of the stopped trailer?"

【THINK】
1. 找到 not standing 的行人 ped (type='pedestrian' AND status<>'standing')。
2. 以 ped 为参照，沿 back-right 找到最近的 bus1。
3. 找到 stopped 的 trailer (category CONTAINS 'trailer' AND status='stopped')。
4. 以 trailer 为参照，沿 front 找到最近的 bus2（使用 direction_4='front'，包含 front-left/right 扇区）。
5. 比较 bus1.status 与 bus2.status，返回 same_status 布尔值。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (ped:Object)
WHERE ped.type = 'pedestrian' AND ped.status <> 'standing'
MATCH (ped)-[r1:RELATES_TO]->(bus1:Object)
WHERE bus1.type = 'bus' AND r1.predicates[0] = 'back-right'
WITH ped, bus1, r1
ORDER BY r1.distance ASC
LIMIT 1

MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer' AND trailer.status = 'stopped'
MATCH (trailer)-[r2:RELATES_TO]->(bus2:Object)
WHERE bus2.type = 'bus' AND r2.direction_4 = 'front'
WITH bus1, bus2, r2
ORDER BY r2.distance ASC
LIMIT 1

RETURN bus1.status = bus2.status AS same_status
【/CYPHER_EXAMPLE】

【示例2 - Pattern A: bus vs truck, 双参考物（scene-0553_frame8）】
自然语言问题:
"There is a bus that is to the back right of the not standing pedestrian; is it the same status as the truck that is to the back right of the with rider thing?"

【THINK】
1. 以 not standing 的行人 ped 为参照，沿 back-right 找最近 bus1。
2. 以 with_rider 状态的对象 ref 为参照（通常是自行车），沿 back-right 找最近 truck1（排除trailer）。
3. 比较 bus1.status 与 truck1.status，返回 same_status。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (ped:Object)
WHERE ped.type = 'pedestrian' AND ped.status <> 'standing'
MATCH (ped)-[r1:RELATES_TO]->(bus1:Object)
WHERE bus1.type = 'bus' AND r1.predicates[0] = 'back-right'
WITH bus1, r1
ORDER BY r1.distance ASC
LIMIT 1

MATCH (ref:Object)
WHERE ref.status = 'with_rider'
MATCH (ref)-[r2:RELATES_TO]->(truck1:Object)
WHERE truck1.type = 'truck' AND NOT truck1.category CONTAINS 'trailer'
  AND r2.predicates[0] = 'back-right'
WITH bus1, truck1, r2
ORDER BY r2.distance ASC
LIMIT 1

RETURN bus1.status = truck1.status AS same_status
【/CYPHER_EXAMPLE】

【示例3 - Pattern A / Count: 前方 barrier 计数（scene-0553_frame8）】
自然语言问题:
"How many barriers are to the front of the trailer?"

【THINK】
1. 选出一辆 trailer 作为参照 (category CONTAINS 'trailer')。
2. 以 trailer 为参照，查找 direction_4='front' 方向上的 barrier。
3. 对这些 barrier 做 count(barrier) 作为答案。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer'
WITH trailer
LIMIT 1
MATCH (trailer)-[r:RELATES_TO]->(barrier:Object)
WHERE barrier.type = 'barrier' AND r.direction_4 = 'front'
RETURN count(barrier) AS barrier_count
【/CYPHER_EXAMPLE】

【示例4 - Pattern B: same status other bicycles（scene-0553_frame8）】
自然语言问题:
"How many other bicycles in the same status as the barrier to the front left of the bicycle?"

【THINK】
1. 找到一辆参考 bicycle refBike。
2. 以 refBike 为参照，沿 front-left 找最近 barrierObj。
3. 记录 barrierObj.status 作为 refStatus。
4. 在所有 bicycle 中计数：type='bicycle' 且 status=refStatus，且 unique_id<>refBike，得到 otherBike 数量。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (refBike:Object {{type:'bicycle'}})
WITH refBike
LIMIT 1
MATCH (refBike)-[r:RELATES_TO]->(barrierObj:Object)
WHERE barrierObj.type = 'barrier' AND r.predicates[0] = 'front-left'
WITH refBike, barrierObj, r
ORDER BY r.distance ASC
LIMIT 1
WITH barrierObj.status AS barrierStatus, refBike.unique_id AS refBikeId
MATCH (otherBike:Object)
WHERE otherBike.type = 'bicycle'
  AND otherBike.status = barrierStatus
  AND otherBike.unique_id <> refBikeId
RETURN count(otherBike) AS count
【/CYPHER_EXAMPLE】

【示例5 - 多锚点交集: trailer/back-right & truck/back（scene-0553_frame8）】
自然语言问题:
"What is the thing that is both to the back right of the stopped trailer and the back of the stopped truck?"

【THINK】
1. 选出 stopped trailer 和 stopped truck（排除trailer类别）。
2. 以 trailer 为参照，沿 back-right 找候选 target。
3. 同时以 truck 为参照，要求同一个 target 还在 truck 的 back 方向 (direction_4='back')。
4. 对满足双重方位约束的 target，按距离和排序取一个，返回其类型/状态。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer' AND trailer.status = 'stopped'
MATCH (truck:Object)
WHERE truck.type = 'truck' AND truck.status = 'stopped' AND NOT truck.category CONTAINS 'trailer'
MATCH (trailer)-[r1:RELATES_TO]->(target:Object)
WHERE r1.predicates[0] = 'back-right'
MATCH (truck)-[r2:RELATES_TO]->(target)
WHERE r2.direction_4 = 'back'
WITH target, r1, r2
ORDER BY r1.distance + r2.distance ASC
LIMIT 1
RETURN target.unique_id, target.type, target.status
【/CYPHER_EXAMPLE】

【示例6 - Pattern A: motorcycle vs pedestrian（scene-0103_frame38）】
自然语言问题:
"There is a motorcycle; is its status the same as the pedestrian to the back right of the with rider thing?"

【THINK】
1. 取一辆 motorcycle moto 作为整体对象。
2. 以 with_rider 状态的对象 ref 为参照，沿 back-right 找最近 pedestrian ped。
3. 比较 moto.status 与 ped.status，返回 same_status。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (moto:Object)
WHERE moto.type = 'motorcycle' OR moto.category CONTAINS 'motorcycle'
WITH moto
LIMIT 1
MATCH (ref:Object)
WHERE ref.status = 'with_rider'
MATCH (ref)-[r:RELATES_TO]->(ped:Object)
WHERE ped.type = 'pedestrian' AND r.predicates[0] = 'back-right'
WITH moto, ped, r
ORDER BY r.distance ASC
LIMIT 1
RETURN moto.status = ped.status AS same_status
【/CYPHER_EXAMPLE】

【示例7 - 单对象状态查询: motorcycle status（scene-0103_frame38）】
自然语言问题:
"There is a motorcycle; what status is it?"

【THINK】
1. 匹配一辆 motorcycle，对应 type='motorcycle' 或 category CONTAINS 'motorcycle'。
2. 返回其 status，LIMIT 1 确保唯一。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (m:Object)
WHERE m.type = 'motorcycle' OR m.category CONTAINS 'motorcycle'
RETURN m.status
LIMIT 1
【/CYPHER_EXAMPLE】

【示例8 - Pattern B: other things same status as truck（scene-0103_frame38）】
自然语言问题:
"Are there any other things that in the same status as the truck?"

【THINK】
1. 选出一辆非trailer的 truck refTruck，记录其 status 和 unique_id。
2. 在动态对象集合 [ego, car, truck, bus, bicycle, motorcycle, trailer, pedestrian] 中查找 other，
   要求 other.status = refStatus，且 (other.type<>'truck' OR other.unique_id<>refId)。
3. 返回 count(other)>0 作为 exist。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (refTruck:Object)
WHERE refTruck.type = 'truck' AND NOT refTruck.category CONTAINS 'trailer'
WITH refTruck.status AS refStatus, refTruck.unique_id AS refId
LIMIT 1
MATCH (other:Object)
WHERE other.type IN ['ego','car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
  AND other.status = refStatus
  AND (other.type <> 'truck' OR other.unique_id <> refId)
RETURN count(other) > 0 AS exist
【/CYPHER_EXAMPLE】

【示例9 - ego 前方 standing pedestrian（scene-0916_frame8）】
自然语言问题:
"The standing pedestrian that is to the front of me is what?"

【THINK】
1. 以 ego 为参照 (unique_id='ego')。
2. 沿 direction_4='front' 查找 status='standing' 的 pedestrian。
3. 按距离排序取最近一个，返回其类型（和unique_id）。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (ego:Object {{unique_id:'ego'}})-[r:RELATES_TO]->(p:Object)
WHERE p.type = 'pedestrian' AND p.status = 'standing' AND r.direction_4 = 'front'
WITH p, r
ORDER BY r.distance ASC
LIMIT 1
RETURN p.unique_id, p.type, p.status
【/CYPHER_EXAMPLE】

【示例10 - Pattern A: motorcycle vs car (back-right of not standing ped, scene-0103_frame25)】
自然语言问题:
"Does the motorcycle have the same status as the car that is to the back right of the not standing pedestrian?"

【THINK】
1. 选出一辆 motorcycle moto。
2. 以 not standing 的 pedestrian 为参照，沿 back-right 找最近的 car car1。
3. 比较 moto.status 与 car1.status。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (moto:Object)
WHERE moto.type = 'motorcycle' OR moto.category CONTAINS 'motorcycle'
WITH moto
LIMIT 1
MATCH (ped:Object)
WHERE ped.type = 'pedestrian' AND ped.status <> 'standing'
MATCH (ped)-[r:RELATES_TO]->(car:Object)
WHERE car.type = 'car' AND r.predicates[0] = 'back-right'
WITH moto, car, r
ORDER BY r.distance ASC
LIMIT 1
RETURN moto.status = car.status AS same_status
【/CYPHER_EXAMPLE】

【示例11 - 计数: front-left stopped things of trailer（scene-0553_frame8, 反例）】
自然语言问题:
"How many stopped things are to the front left of the trailer?"

【THINK】
1. 以 trailer 为参照。
2. 沿 front-left 查找所有 status='stopped' 的对象（不限类型）。
3. 返回 count(obj) 作为答案。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer'
WITH trailer
LIMIT 1
MATCH (trailer)-[r:RELATES_TO]->(obj:Object)
WHERE r.predicates[0] = 'front-left' AND obj.status = 'stopped'
RETURN count(obj) AS count
【/CYPHER_EXAMPLE】

【示例12 - 多锚点交集变体（scene-0553_frame8, 反例）】
自然语言问题:
"There is a thing that is to the back right of the stopped trailer and the back of the stopped truck; what is it?"

【THINK】
1. 同示例5，但题面用 "There is a thing ... what is it?"；语义上仍是找满足双方位约束的唯一 target。
2. 直接返回 target 的类型即可。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (trailer:Object)
WHERE trailer.category CONTAINS 'trailer' AND trailer.status = 'stopped'
MATCH (truck:Object)
WHERE truck.type = 'truck' AND truck.status = 'stopped' AND NOT truck.category CONTAINS 'trailer'
MATCH (trailer)-[r1:RELATES_TO]->(target:Object)
WHERE r1.predicates[0] = 'back-right'
MATCH (truck)-[r2:RELATES_TO]->(target)
WHERE r2.direction_4 = 'back'
WITH target, r1, r2
ORDER BY r1.distance + r2.distance ASC
LIMIT 1
RETURN target.unique_id, target.type, target.status
【/CYPHER_EXAMPLE】

【示例13 - 多锚点: back-right of motorcycle & front-left of ego（scene-0103_frame38, 反例）】
自然语言问题:
"There is a thing that is to the back right of the without rider motorcycle and the front left of me; what is it?"

【THINK】
1. 选出 without_rider 的 motorcycle m。
2. 以 m 为参照，沿 back-right 找候选 obj。
3. 同时以 ego 为参照，要求同一个 obj 在 ego 的 front-left 方向。
4. 对满足交集的 obj 按总距离排序取一个，返回其类型。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (m:Object)
WHERE (m.type = 'motorcycle' OR m.category CONTAINS 'motorcycle')
  AND m.status = 'without_rider'
MATCH (m)-[r1:RELATES_TO]->(obj:Object)
WHERE r1.predicates[0] = 'back-right'
MATCH (ego:Object {{unique_id:'ego'}})-[r2:RELATES_TO]->(obj)
WHERE r2.predicates[0] = 'front-left'
WITH obj, r1, r2
ORDER BY r1.distance + r2.distance ASC
LIMIT 1
RETURN obj.unique_id, obj.type, obj.status
【/CYPHER_EXAMPLE】

【示例14 - Pattern B: other pedestrians same status as back-right pedestrian（scene-0103_frame38, 反例）】
自然语言问题:
"How many other pedestrians are in the same status as the pedestrian to the back right of the truck?"

【THINK】
1. 以非trailer的 truck 为参照，沿 back-right 找最近参考行人 refPed。
2. 记录 refPed.status 和 refPed.unique_id。
3. 在所有 pedestrian 中计数：status = refStatus 且 unique_id<>refId。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (truck:Object)
WHERE truck.type = 'truck' AND NOT truck.category CONTAINS 'trailer'
WITH truck
LIMIT 1
MATCH (truck)-[r:RELATES_TO]->(refPed:Object)
WHERE refPed.type = 'pedestrian' AND r.predicates[0] = 'back-right'
WITH refPed, r
ORDER BY r.distance ASC
LIMIT 1
WITH refPed.status AS targetStatus, refPed.unique_id AS refId
MATCH (other:Object)
WHERE other.type = 'pedestrian' AND other.status = targetStatus AND other.unique_id <> refId
RETURN count(other) AS count
【/CYPHER_EXAMPLE】

【示例15 - 多锚点: moving thing back-right of ego & bus（scene-0916_frame8, 反例）】
自然语言问题:
"What is the moving thing that is to the back right of me and the back right of the bus?"

【THINK】
1. 以 ego 和 bus 为两个参照物。
2. 找到同时满足：在 ego 的 back-right 且在 bus 的 back-right 的 moving 对象 obj。
3. 按总距离排序取一个，返回其类型/状态。
【/THINK】
【CYPHER_EXAMPLE】
MATCH (ego:Object {{unique_id:'ego'}})-[r1:RELATES_TO]->(obj:Object)
WHERE r1.predicates[0] = 'back-right' AND obj.status = 'moving'
MATCH (bus:Object {{type:'bus'}})-[r2:RELATES_TO]->(obj)
WHERE r2.predicates[0] = 'back-right'
WITH obj, r1, r2
ORDER BY r1.distance + r2.distance ASC
LIMIT 1
RETURN obj.unique_id, obj.type, obj.status
【/CYPHER_EXAMPLE】

输出格式约定（务必遵守，用于自动抽取）:
- 可以在前面用【THINK】...【/THINK】包裹你的思考过程（可选）。
- 最终必须用一对【CYPHER】...【/CYPHER】包裹**唯一一条**可执行的Cypher查询语句，所有Cypher只写在这个块里面。
- 不能使用 ``` 代码块、Markdown 或其他额外标记来包裹Cypher。

输出要求:
- 【必须】在【CYPHER】...【/CYPHER】中只写一条查询，且只有一个最终 RETURN。
- 不要使用中文变量名；
- ⚠️ 绝对不要返回空查询！如果问题过于复杂，请给出一个合理的近似查询，而不是空结果。
- ❗ 复合方位如 "back right" 直接对应 'back-right'，不需要简化！数据库支持8方位；同时 direction_4 是由 direction_8 聚合而来，例如 'front-left' 和 'front-right' 都属于 'front' 扇区。

请严格按照上述格式输出，例如:
【THINK】这里是你的思考过程...【/THINK】
【CYPHER】
MATCH ...
...
RETURN ...
【/CYPHER】

Cypher查询:"""

RESULT_TO_ANSWER_PROMPT = """你是一个专业的问答助手。根据Neo4j查询结果，生成自然语言答案。

原始问题: {question}
问题类型: {question_type}
查询结果: {result}

答案格式要求:
{format_requirement}

要求:
1. 严格按照格式要求回答
2. 不要添加任何解释或额外信息
3. 如果结果为空，对于exist/comparison问题回答"no"，其他问题回答"0"或"未找到"

答案:"""

# ============ IR生成 Prompt ============
IR_GENERATION_PROMPT = """You are an information extraction engine for NuScenes VQA.

Your ONLY task is to convert ONE English question about a NuScenes scene into ONE JSON QueryPlan object.
Do NOT answer the question. Do NOT explain. Just output the JSON.

You will be given:
- question_type: one of {"status","exist","count","count_same_status","comparison","object"}
- question: ONE English question string.

Schema conventions:
- "trailer" is a SPECIAL type: use type="trailer" in IR, it will be converted to category-based query
- "motorcycle" is a distinct type: use type="motorcycle" in IR, backed by category "vehicle.motorcycle"
- "with rider thing" means bicycle with status "with_rider"
- "not standing pedestrian" means pedestrian with status not "standing" (do NOT drop the "not" in normalization)
- Directions: "front", "back", "left", "right", "front_left", "back_right", etc.

QueryPlan schema:
{
  "question_type": "status" | "exist" | "count" | "count_same_status" | "comparison" | "object",
  "answer_property": "status" | "type" | "count" | "exists" | "boolean",
  "target": ObjectExpr or null,
  "reference": ObjectExpr or null,  // For count_same_status: the object to compare status with
  "comparison": {
    "property": "status" | "type",
    "lhs": ObjectExpr,
    "rhs": ObjectExpr
  } or null
}

Rules for answer_property:
- status  -> "status"
- object  -> "type"
- count   -> "count"
- count_same_status -> "count" (but needs reference object)
- exist   -> "exists"
- comparison -> "boolean"

ObjectExpr (recursive):
{
  "type": OBJECT_TYPE,
  "status": STATUS_VALUE or null,
  "alias": SHORT_VAR_NAME,
  "constraints": [],
  "relations": [ RelationExpr, ... ]
}

Allowed OBJECT_TYPE values:
- "ego", "car", "truck", "bus", "bicycle", "pedestrian", "barrier", "trailer", "thing"

IMPORTANT: Use "trailer" as a distinct type (not "truck")! It will be handled specially.

Semantics of OBJECT_TYPE "thing":
- "thing" is a wildcard for "other things" in the question text.
- In count_same_status questions, "thing" should be interpreted as any dynamic object type:
  ego, car, truck, bus, bicycle, motorcycle, trailer, pedestrian (exclude barrier).

Allowed STATUS_VALUE values:
- "moving", "stopped", "parked", "with_rider", "without_rider", "standing", "not_standing"

RelationExpr:
{
  "direction": DIRECTION,
  "ref": ObjectExpr
}

Allowed DIRECTION values:
- "front", "back", "left", "right", "front_left", "front_right", "back_left", "back_right"

Special pattern - "count_same_status":
For questions like "What number of other things have the same status as the trailer?"
Use question_type="count_same_status", set target to {type:"thing"} and reference to the object being compared.

Example IR for "What number of other things are there of the same status as the trailer?":
{
  "question_type": "count_same_status",
  "answer_property": "count",
  "target": {"type": "thing", "alias": "other"},
  "reference": {"type": "trailer", "alias": "ref"},
  "comparison": null
}

Output requirements:
- Only output the JSON object.
- Do NOT wrap in markdown.
- Do NOT include comments.
- Ensure it is valid JSON (no trailing commas).

Now produce the QueryPlan JSON for the given question_type and question.
"""

# ============ IR到Cypher生成 Prompt ============
IR_TO_CYPHER_PROMPT = """You are a Neo4j Cypher query expert. Generate a Cypher query based on the given QueryPlan IR.

Neo4j Schema:
- Node label: Object
- Node properties: unique_id, type, status, category, attributes
- Relationship: RELATES_TO with predicates[0]=direction, predicates[1]=distance_level

IMPORTANT Type Handling:
- type="trailer": Query using category field: WHERE n.category CONTAINS 'trailer'
- type="truck": Exclude trailer: WHERE n.type='truck' AND NOT n.category CONTAINS 'trailer'
- type="thing": For count_same_status, interpret as any dynamic object type:
  ego, car, truck, bus, bicycle, motorcycle, trailer, pedestrian (exclude barrier).
- Other types: Use n.type='car'/'bus'/'bicycle'/'pedestrian'/'barrier'/'ego' directly

Direction Mapping (align with 4-way & 8-way semantics):
- 8-way directions ("front_left", "front_right", "back_left", "back_right") MUST map to r.predicates[0] with the exact 8-way value.
- 4-way directions ("front", "back", "left", "right") MUST map to r.direction_4.
- "back" is equivalent to "rear" when needed, but do NOT drop 8-way information when it is explicitly present in the IR.
- 4-way sectors are aggregates of 8-way sectors, e.g. "front_left" and "front_right" both belong to the "front" sector.

QueryPlan IR:
{query_plan}

Original Question: {question}

Generate ONE executable Cypher query. Rules:
1. Only ONE RETURN clause at the end
2. For "trailer" type, use: WHERE n.category CONTAINS 'trailer'
3. For "truck" type, add: AND NOT n.category CONTAINS 'trailer'
4. For status queries (including same-status comparisons), always use the status property:
   e.g., RETURN x.status AS status LIMIT 1, or WHERE o.status = ref.status.
5. For exist queries, return: RETURN count(x) > 0 AS exists
6. For count queries, return: RETURN count(x) AS count
7. For comparison queries, return: RETURN a.status = b.status AS same
8. For "count_same_status": First get reference status, then count other objects with the same status
   (excluding the reference object) and restrict to dynamic object types
   [ego, car, truck, bus, bicycle, motorcycle, trailer, pedestrian] (exclude barrier).
9. Use LIMIT 1 when getting a single unique object

Output ONLY the Cypher query, no explanation.

Cypher:"""
