import json
import math
import os
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from nuscenes.nuscenes import NuScenes

# 配置
NUSCENES_DATAROOT = r"E:\Project\ADVTEST\data\nuscenes"
QA_FILE = r"E:\Project\ADVTEST\data\nuscenes\qa\NuScenes_val_questions.json"
OUTPUT_FILE = r"E:\Project\ADVTEST\nuscenes_s3c_experiment\output\direction_answer_eval.txt"

# 测试的场景和帧
TEST_FRAMES = [
    ("scene-0103", 25),
    ("scene-0103", 38),
    ("scene-0553", 8),
    ("scene-0916", 8),
]

DIRECTIONS = [
    "front-left",
    "front-right",
    "back-left",
    "back-right",
    "front",
    "back",
    "left",
    "right",
]
DIR_REGEX = "|".join(DIRECTIONS)

STATUS_PHRASES = [
    "with rider",
    "without rider",
    "not standing",
    "standing",
    "moving",
    "parked",
    "stopped",
]

TYPE_ALIASES = {
    "construction vehicle": "construction vehicle",
    "construction vehicles": "construction vehicle",
    "traffic cone": "traffic cone",
    "traffic cones": "traffic cone",
    "barrier": "barrier",
    "barriers": "barrier",
    "motorcycle": "motorcycle",
    "motorcycles": "motorcycle",
    "bicycle": "bicycle",
    "bicycles": "bicycle",
    "pedestrian": "pedestrian",
    "pedestrians": "pedestrian",
    "trailer": "trailer",
    "trailers": "trailer",
    "truck": "truck",
    "trucks": "truck",
    "bus": "bus",
    "buses": "bus",
    "car": "car",
    "cars": "car",
    "thing": None,
    "things": None,
    "object": None,
    "objects": None,
}


@dataclass
class Obj:
    token: str
    obj_type: str
    status: str
    pos: Tuple[float, float]
    heading: float


@dataclass
class ObjDesc:
    obj_type: Optional[str]
    status: Optional[str]
    status_ref: Optional[str]
    relations: List[Tuple[str, str]]
    other: bool


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("front left", "front-left")
    text = text.replace("front right", "front-right")
    text = text.replace("back left", "back-left")
    text = text.replace("back right", "back-right")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def quaternion_to_yaw(q):
    """四元数转yaw角(度)"""
    w, x, y, z = q[0], q[1], q[2], q[3]
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return math.degrees(yaw)


def normalize_angle(angle):
    """标准化角度到-180~180"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def angle_to_direction(angle):
    """角度转8方向"""
    angle = normalize_angle(angle)
    if -22.5 <= angle < 22.5:
        return "front"
    elif 22.5 <= angle < 67.5:
        return "front-left"
    elif 67.5 <= angle < 112.5:
        return "left"
    elif 112.5 <= angle < 157.5:
        return "back-left"
    elif angle >= 157.5 or angle < -157.5:
        return "back"
    elif -157.5 <= angle < -112.5:
        return "back-right"
    elif -112.5 <= angle < -67.5:
        return "right"
    else:
        return "front-right"


def calculate_direction(
    method: str, source: Obj, target: Obj, ego_heading: float
) -> str:
    dx = target.pos[0] - source.pos[0]
    dy = target.pos[1] - source.pos[1]
    global_angle = math.degrees(math.atan2(dx, dy))

    if method == "global":
        return angle_to_direction(global_angle)

    if method == "ego_frame":
        ego_heading_north = normalize_angle(90 - ego_heading)
        ego_frame_angle = normalize_angle(global_angle - ego_heading_north)
        return angle_to_direction(ego_frame_angle)

    # source_frame
    source_heading_north = normalize_angle(90 - source.heading)
    source_frame_angle = normalize_angle(global_angle - source_heading_north)
    return angle_to_direction(source_frame_angle)


def get_object_by_type_status(ann, nusc):
    """从annotation获取对象类型和状态"""
    category = ann["category_name"]

    obj_type = None
    if "vehicle.car" in category:
        obj_type = "car"
    elif "vehicle.truck" in category:
        obj_type = "truck"
    elif "vehicle.bus" in category:
        obj_type = "bus"
    elif "vehicle.trailer" in category:
        obj_type = "trailer"
    elif "vehicle.construction" in category:
        obj_type = "construction vehicle"
    elif "vehicle.bicycle" in category:
        obj_type = "bicycle"
    elif "vehicle.motorcycle" in category:
        obj_type = "motorcycle"
    elif "human.pedestrian" in category:
        obj_type = "pedestrian"
    elif "movable_object.barrier" in category:
        obj_type = "barrier"
    elif "movable_object.trafficcone" in category:
        obj_type = "traffic cone"

    if obj_type is None:
        return None, None

    attrs = [nusc.get("attribute", a)["name"] for a in ann["attribute_tokens"]]
    obj_status = "unknown"
    for attr in attrs:
        if "with_rider" in attr:
            obj_status = "with rider"
        elif "without_rider" in attr:
            obj_status = "without rider"
        elif "parked" in attr:
            obj_status = "parked"
        elif "stopped" in attr:
            obj_status = "stopped"
        elif "moving" in attr:
            obj_status = "moving"
        elif "standing" in attr:
            obj_status = "standing"
        elif "sitting" in attr or "lying" in attr:
            obj_status = "not standing"

    return obj_type, obj_status


def parse_desc(desc_text: str) -> ObjDesc:
    text = normalize_text(desc_text)
    text = re.sub(r"[?.,]", "", text)

    other = bool(re.search(r"\b(other|another)\b", text))

    status_ref = None
    m = re.search(
        r"(?:same status as|in the same status as|of the same status as)\s+(.+)",
        text,
    )
    if m:
        status_ref = m.group(1).strip()
        text = text[: m.start()].strip()

    for d in DIRECTIONS:
        text = re.sub(rf"\band the {d} of ", f" and to the {d} of ", text)

    rel_pattern = re.compile(
        rf"\bto the ({DIR_REGEX}) of (.+?)(?=\s+and\s+to the|\s+and\s+the|\s+and\s+|$)"
    )
    relations = [(m.group(1), m.group(2).strip()) for m in rel_pattern.finditer(text)]

    base = rel_pattern.sub("", text)
    base = re.sub(r"\band\b", " ", base)
    base = re.sub(r"\b(the|a|an)\b", " ", base)
    base = re.sub(r"\s+", " ", base).strip()

    status = None
    for s in STATUS_PHRASES:
        if s in base:
            status = s
            base = base.replace(s, " ")
            base = re.sub(r"\s+", " ", base).strip()
            break

    obj_type = None
    for phrase, mapped in sorted(TYPE_ALIASES.items(), key=lambda x: -len(x[0])):
        if phrase in base:
            obj_type = mapped
            break

    return ObjDesc(
        obj_type=obj_type,
        status=status,
        status_ref=status_ref,
        relations=relations,
        other=other,
    )

def status_matches(query_status: str, obj_status: str) -> bool:
    if obj_status == "unknown":
        return False
    if query_status == "stopped":
        return obj_status in ["stopped", "parked"]
    if query_status == "not standing":
        return obj_status in ["not standing", "moving"]
    return obj_status == query_status


def extract_context_desc(question: str) -> Tuple[Optional[str], str]:
    if ";" in question:
        prefix, suffix = question.split(";", 1)
        m = re.match(r"\s*there is (?:a|an|the)?\s*(.+)", prefix.strip())
        if m:
            return m.group(1).strip(), suffix.strip()
    return None, question.strip()


def resolve_desc(
    desc_text: str,
    method: str,
    objects: List[Obj],
    ego: Obj,
    ego_heading: float,
    context_desc: Optional[str],
    cache: dict,
) -> List[Obj]:
    key = (method, desc_text, context_desc)
    if key in cache:
        return cache[key]

    text = normalize_text(desc_text)
    text = re.sub(r"[?.,]", "", text)
    if text in ["me", "i"]:
        cache[key] = [ego]
        return cache[key]
    if text in ["it", "its"] and context_desc:
        text = context_desc

    desc = parse_desc(text)

    candidates = []
    for obj in objects:
        if desc.obj_type and obj.obj_type != desc.obj_type:
            continue
        if desc.status and not status_matches(desc.status, obj.status):
            continue
        candidates.append(obj)

    if desc.status_ref:
        ref_objs = resolve_desc(
            desc.status_ref, method, objects, ego, ego_heading, context_desc, cache
        )
        ref_statuses = {o.status for o in ref_objs if o.status != "unknown"}
        if ref_statuses:
            candidates = [o for o in candidates if o.status in ref_statuses]
        else:
            candidates = []

    for rel_dir, rel_source in desc.relations:
        sources = resolve_desc(
            rel_source, method, objects, ego, ego_heading, context_desc, cache
        )
        if not sources:
            candidates = []
            break

        new_candidates = []
        for obj in candidates:
            if any(
                calculate_direction(method, src, obj, ego_heading) == rel_dir
                for src in sources
            ):
                new_candidates.append(obj)
        candidates = new_candidates

    cache[key] = candidates
    return candidates

def select_one(candidates: List[Obj], ego_pos: Tuple[float, float]) -> Optional[Obj]:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda o: math.sqrt((o.pos[0] - ego_pos[0]) ** 2 + (o.pos[1] - ego_pos[1]) ** 2),
    )


def answer_exist(desc_text, method, objects, ego, ego_heading, context_desc, cache) -> set:
    desc = parse_desc(desc_text)
    candidates = resolve_desc(
        desc_text, method, objects, ego, ego_heading, context_desc, cache
    )
    if desc.other and desc.status_ref:
        ref_objs = resolve_desc(
            desc.status_ref, method, objects, ego, ego_heading, context_desc, cache
        )
        ref_tokens = {o.token for o in ref_objs}
        candidates = [o for o in candidates if o.token not in ref_tokens]
    return {"yes"} if candidates else {"no"}


def answer_count(desc_text, method, objects, ego, ego_heading, context_desc, cache) -> set:
    desc = parse_desc(desc_text)
    candidates = resolve_desc(
        desc_text, method, objects, ego, ego_heading, context_desc, cache
    )
    if desc.other and desc.status_ref:
        ref_objs = resolve_desc(
            desc.status_ref, method, objects, ego, ego_heading, context_desc, cache
        )
        ref_tokens = {o.token for o in ref_objs}
        candidates = [o for o in candidates if o.token not in ref_tokens]
    count = len(candidates)
    if count > 10:
        count = 10
    return {str(count)}


def answer_object(desc_text, method, objects, ego, ego_heading, context_desc, cache) -> set:
    candidates = resolve_desc(
        desc_text, method, objects, ego, ego_heading, context_desc, cache
    )
    if not candidates:
        return set()
    return {o.obj_type for o in candidates if o.obj_type}


def answer_status(desc_text, method, objects, ego, ego_heading, context_desc, cache) -> set:
    candidates = resolve_desc(
        desc_text, method, objects, ego, ego_heading, context_desc, cache
    )
    if not candidates:
        return set()
    return {o.status for o in candidates if o.status != "unknown"}


def parse_desc_from_question(question: str, patterns: List[Tuple[str, int]]) -> Optional[str]:
    for pat, group in patterns:
        m = re.match(pat, question)
        if m:
            return m.group(group).strip()
    return None


def answer_question(question_raw: str, template_type: str, method: str, objects: List[Obj], ego: Obj, ego_heading: float) -> set:
    question = normalize_text(question_raw)
    context_desc, main_q = extract_context_desc(question)
    cache = {}

    if template_type == "exist":
        desc = parse_desc_from_question(
            main_q,
            [
                (r"are there any (.+)", 1),
                (r"is there any (.+)", 1),
            ],
        )
        if not desc:
            return set()
        return answer_exist(desc, method, objects, ego, ego_heading, context_desc, cache)

    if template_type == "count":
        desc = parse_desc_from_question(
            main_q,
            [
                (r"how many (.+)", 1),
                (r"what number of (.+)", 1),
            ],
        )
        if not desc:
            return set()
        return answer_count(desc, method, objects, ego, ego_heading, context_desc, cache)

    if template_type == "object":
        if context_desc and re.search(r"what is it\??$", main_q):
            return answer_object(context_desc, method, objects, ego, ego_heading, context_desc, cache)

        desc = parse_desc_from_question(
            main_q,
            [
                (r"the (.+) is what", 1),
                (r"what is the (.+)", 1),
                (r"what is (?:a|an|the) (.+)", 1),
            ],
        )
        if not desc:
            return set()
        return answer_object(desc, method, objects, ego, ego_heading, context_desc, cache)

    if template_type == "status":
        if context_desc and re.search(r"what status is it\??$|what is its status\??$", main_q):
            return answer_status(context_desc, method, objects, ego, ego_heading, context_desc, cache)

        desc = parse_desc_from_question(
            main_q,
            [
                (r"what status is the (.+)", 1),
                (r"what is the status of the (.+)", 1),
                (r"the (.+) is in what status", 1),
                (r"there is (?:a|an|the) (.+) what status is it", 1),
            ],
        )
        if not desc:
            return set()
        return answer_status(desc, method, objects, ego, ego_heading, context_desc, cache)

    if template_type == "comparison":
        # existence of other same-status objects
        if re.match(r"^is there another ", main_q) or re.match(
            r"^are there any other ", main_q
        ):
            desc = parse_desc_from_question(
                main_q,
                [
                    (r"is there another (.+)", 1),
                    (r"are there any other (.+)", 1),
                ],
            )
            if not desc:
                return set()
            return answer_exist(desc, method, objects, ego, ego_heading, context_desc, cache)

        # status comparison between two objects
        desc1 = None
        desc2 = None
        if context_desc:
            m = re.match(r"is it the same status as the (.+)", main_q)
            if m:
                desc1, desc2 = context_desc, m.group(1)
            m = re.match(r"is its status the same as the (.+)", main_q)
            if m:
                desc1, desc2 = context_desc, m.group(1)
        m = re.match(
            r"is the status of the (.+) the same as the (.+)", main_q
        )
        if m:
            desc1, desc2 = m.group(1), m.group(2)
        m = re.match(
            r"does the (.+) have the same status as the (.+)", main_q
        )
        if m:
            desc1, desc2 = m.group(1), m.group(2)
        m = re.match(
            r"there is (?:a|an|the) (.+) is it the same status as the (.+)", main_q
        )
        if m:
            desc1, desc2 = m.group(1), m.group(2)
        m = re.match(
            r"there is (?:a|an|the) (.+) is its status the same as the (.+)",
            main_q,
        )
        if m:
            desc1, desc2 = m.group(1), m.group(2)

        if not desc1 or not desc2:
            return set()

        # clean possible leading "status of the" in desc2
        desc2 = re.sub(r"^status of the ", "", desc2).strip()

        objs1 = resolve_desc(desc1, method, objects, ego, ego_heading, context_desc, cache)
        objs2 = resolve_desc(desc2, method, objects, ego, ego_heading, context_desc, cache)
        if not objs1 or not objs2:
            return set()
        statuses1 = {o.status for o in objs1 if o.status != "unknown"}
        statuses2 = {o.status for o in objs2 if o.status != "unknown"}
        if not statuses1 or not statuses2:
            return set()
        answers = set()
        if statuses1 & statuses2:
            answers.add("yes")
        if any(s1 != s2 for s1 in statuses1 for s2 in statuses2):
            answers.add("no")
        return answers

    return set()


def extract_direction_from_question(question):
    q_lower = normalize_text(question)
    return [d for d in DIRECTIONS if d in q_lower]


def main():
    print("初始化NuScenes...")
    nusc = NuScenes(version="v1.0-trainval", dataroot=NUSCENES_DATAROOT, verbose=False)

    print("加载QA数据集...")
    with open(QA_FILE, "r", encoding="utf-8") as f:
        qa_data = json.load(f)

    # 建立sample_token到场景帧的映射
    sample_to_scene = {}
    for scene in nusc.scene:
        scene_name = scene["name"]
        sample_token = scene["first_sample_token"]
        frame_idx = 0
        while sample_token:
            sample_to_scene[sample_token] = (scene_name, frame_idx)
            sample = nusc.get("sample", sample_token)
            sample_token = sample["next"]
            frame_idx += 1

    # 找出测试帧的sample_token
    test_tokens = set()
    for scene_name, frame_idx in TEST_FRAMES:
        for scene in nusc.scene:
            if scene["name"] == scene_name:
                sample_token = scene["first_sample_token"]
                for _ in range(frame_idx):
                    sample = nusc.get("sample", sample_token)
                    sample_token = sample["next"]
                test_tokens.add(sample_token)
                break

    # 筛选相关问题（包含方向词）
    direction_questions = []
    for q in qa_data["questions"]:
        if q["sample_token"] in test_tokens:
            if extract_direction_from_question(q["question"]):
                direction_questions.append(q)

    print(f"找到 {len(direction_questions)} 道涉及方向的题目")

    methods = ["global", "ego_frame", "source_frame"]
    stats = {
        m: {"total": 0, "correct": 0, "unresolved": 0} for m in methods
    }

    results = []

    for q in direction_questions:
        sample_token = q["sample_token"]
        scene_name, frame_idx = sample_to_scene[sample_token]
        sample = nusc.get("sample", sample_token)

        # ego pose
        ego_pose_token = sample["data"]["LIDAR_TOP"]
        sample_data = nusc.get("sample_data", ego_pose_token)
        ego_pose = nusc.get("ego_pose", sample_data["ego_pose_token"])
        ego_pos = (ego_pose["translation"][0], ego_pose["translation"][1])
        ego_heading = quaternion_to_yaw(ego_pose["rotation"])
        ego_obj = Obj(token="ego", obj_type="ego", status="ego", pos=ego_pos, heading=ego_heading)

        # build objects
        objects = []
        for ann_token in sample["anns"]:
            ann = nusc.get("sample_annotation", ann_token)
            obj_type, obj_status = get_object_by_type_status(ann, nusc)
            if obj_type is None:
                continue
            pos = ann["translation"]
            objects.append(
                Obj(
                    token=ann_token,
                    obj_type=obj_type,
                    status=obj_status,
                    pos=(pos[0], pos[1]),
                    heading=quaternion_to_yaw(ann["rotation"]),
                )
            )

        per_q = {
            "scene": scene_name,
            "frame": frame_idx,
            "question": q["question"],
            "answer": q["answer"],
            "template_type": q["template_type"],
            "pred": {},
        }

        for m in methods:
            stats[m]["total"] += 1
            pred = answer_question(q["question"], q["template_type"], m, objects, ego_obj, ego_heading)
            per_q["pred"][m] = pred
            if not pred:
                stats[m]["unresolved"] += 1
            elif str(q["answer"]) in pred:
                stats[m]["correct"] += 1

        results.append(per_q)

    # 输出到文件
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("NuScenes-QA 方向答案反推坐标系分析\n")
        f.write("=" * 80 + "\n\n")
        f.write("评估方式: 对每种坐标系方法，直接计算问题答案并与GT对比\n")
        f.write("注意: 若解析失败或对象匹配不唯一则标记为 unresolved\n\n")

        for i, r in enumerate(results, 1):
            f.write(f"问题 {i}: [{r['scene']} frame {r['frame']}]\n")
            f.write(f"Type: {r['template_type']}\n")
            f.write(f"Q: {r['question']}\n")
            f.write(f"A: {r['answer']}\n")
            for m in methods:
                pred_list = ", ".join(sorted(r["pred"][m])) if r["pred"][m] else "unresolved"
                f.write(f"  {m}: {pred_list}\n")
            f.write("-" * 60 + "\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("统计汇总\n")
        f.write("=" * 80 + "\n\n")
        for m in methods:
            total = stats[m]["total"]
            correct = stats[m]["correct"]
            unresolved = stats[m]["unresolved"]
            acc = 100 * correct / total if total else 0
            f.write(
                f"{m}: correct {correct}/{total} ({acc:.1f}%), unresolved {unresolved}\n"
            )

    print(f"分析完成! 结果保存到: {OUTPUT_FILE}")
    for m in methods:
        total = stats[m]["total"]
        correct = stats[m]["correct"]
        unresolved = stats[m]["unresolved"]
        acc = 100 * correct / total if total else 0
        print(f"{m}: correct {correct}/{total} ({acc:.1f}%), unresolved {unresolved}")


if __name__ == "__main__":
    main()
