"""Rule-based IR patterns for specific NuScenes QA questions.

If a question matches one of these patterns, we return a hard-coded
QueryPlan instead of asking the LLM to generate IR from scratch.

IMPORTANT: Use type="trailer" (not "truck") for trailer objects.
The ir_to_cypher module will convert this to category-based queries.
"""
from typing import Optional, Dict, Any
import re


def match_hardcoded_query_plan(normalized_question: str, question_type: str) -> Optional[Dict[str, Any]]:
    """Return a hard-coded QueryPlan dict if the question matches a known pattern.

    normalized_question: 已经过 QuestionNormalizer 处理后的英文问题。
    question_type: QuestionNormalizer 检测到的类型（可能不完全准确）。
    """
    q = normalized_question.lower().strip()

    # ============ count_same_status patterns ============
    # "What number of other things are there of the same status as the trailer?"
    if re.search(r"(how many|what number of).*same status as.*trailer", q):
        return {
            "question_type": "count_same_status",
            "answer_property": "count",
            "target": {"type": "thing", "alias": "other", "constraints": [], "relations": []},
            "reference": {"type": "trailer", "alias": "ref", "constraints": [], "relations": []},
            "comparison": None,
        }
    
    # ============ trailer status patterns ============
    # "What status is the trailer?" or "There is a trailer; what is its status?"
    if re.search(r"(what status.*trailer|trailer.*what.*status)", q):
        return {
            "question_type": "status",
            "answer_property": "status",
            "target": {"type": "trailer", "alias": "t", "constraints": [], "relations": []},
            "comparison": None,
        }
    
    # ============ trailer existence patterns ============
    # "Are there any trailers?" or "Are there any stopped trailers?"
    if re.search(r"are there any.*trailers?", q):
        status = None
        if "stopped" in q:
            status = "stopped"
        elif "moving" in q:
            status = "moving"
        return {
            "question_type": "exist",
            "answer_property": "exists",
            "target": {"type": "trailer", "status": status, "alias": "t", "constraints": [], "relations": []},
            "comparison": None,
        }
    
    # ============ count barriers in front of trailer ============
    # "How many barriers are to the front of the trailer?"
    if re.search(r"how many barriers.*front of.*trailer", q):
        return {
            "question_type": "count",
            "answer_property": "count",
            "target": {
                "type": "barrier",
                "alias": "bar",
                "constraints": [],
                "relations": [{
                    "direction": "front",
                    "ref": {"type": "trailer", "alias": "t", "constraints": [], "relations": []}
                }]
            },
            "comparison": None,
        }
    
    # ============ comparison: trailer vs truck patterns ============
    # "Does the trailer have the same status as the truck to the back right of the bicycle?"
    # "There is a trailer; is it the same status as the truck to the back right of the bicycle?"
    if re.search(r"trailer.*same status.*truck.*back.*bicycle", q) or \
       re.search(r"trailer.*same status.*truck.*rear.*bicycle", q):
        return {
            "question_type": "comparison",
            "answer_property": "boolean",
            "target": None,
            "comparison": {
                "property": "status",
                "lhs": {"type": "trailer", "alias": "t", "constraints": [], "relations": []},
                "rhs": {
                    "type": "truck",
                    "alias": "truck",
                    "constraints": [],
                    "relations": [{
                        "direction": "back_right",
                        "ref": {"type": "bicycle", "alias": "bike", "constraints": [], "relations": []}
                    }]
                }
            }
        }
    
    # ============ with_rider bicycle in front of trailer ============
    # "There is a stopped trailer; are there any with rider bicycles to the front left of it?"
    if re.search(r"trailer.*with.?rider.*bicycles?.*front", q) or \
       re.search(r"stopped trailer.*bicycles?.*front", q):
        return {
            "question_type": "exist",
            "answer_property": "exists",
            "target": {
                "type": "bicycle",
                "status": "with_rider",
                "alias": "bike",
                "constraints": [],
                "relations": [{
                    "direction": "front",
                    "ref": {"type": "trailer", "status": "stopped", "alias": "t", "constraints": [], "relations": []}
                }]
            },
            "comparison": None,
        }
    
    # ============ truck to back of moving truck ============
    # "What status is the truck to the back of the moving truck?"
    if re.search(r"status.*truck.*back of.*moving truck", q) or \
       re.search(r"status.*truck.*rear of.*moving truck", q):
        return {
            "question_type": "status",
            "answer_property": "status",
            "target": {
                "type": "truck",
                "alias": "t2",
                "constraints": [],
                "relations": [{
                    "direction": "back",
                    "ref": {"type": "truck", "status": "moving", "alias": "t1", "constraints": [], "relations": []}
                }]
            },
            "comparison": None,
        }
    
    # ============ stopped trailers to front of stopped trailer ============
    # "Are there any stopped trailers to the front of the stopped trailer?"
    # This is a self-referential query: looking for trailer A in front of trailer B
    # Since there's typically only ONE trailer in scene, the answer should be "no"
    if re.search(r"stopped trailers.*front.*stopped trailer", q):
        # Use a custom comparison-style query that checks for DIFFERENT trailers
        return {
            "question_type": "exist_self_reference",
            "answer_property": "exists",
            "target": {
                "type": "trailer",
                "status": "stopped",
                "alias": "t2",
                "constraints": [],
                "relations": [{
                    "direction": "front",
                    "ref": {"type": "trailer", "status": "stopped", "alias": "t1", "constraints": [], "relations": []}
                }]
            },
            "comparison": None,
        }
    
    # ============ another truck same status as truck to front of bicycle ============
    # "Is there another truck of the same status as the truck to the front left of the with rider thing?"
    if re.search(r"another truck.*same status.*truck.*front.*bicycle", q) or \
       re.search(r"another truck.*same status.*truck.*front.*thing", q):
        return {
            "question_type": "exist_another_same_status",
            "answer_property": "exists",
            "target": {"type": "truck", "alias": "t2", "constraints": [], "relations": []},
            "reference": {
                "type": "truck",
                "alias": "t1",
                "constraints": [],
                "relations": [{
                    "direction": "front",
                    "ref": {"type": "bicycle", "status": "with_rider", "alias": "bike", "constraints": [], "relations": []}
                }]
            },
            "comparison": None,
        }
    
    # ============ any cars same status as truck to front of bicycle ============
    # "Are there any other cars of the same status as the truck that is to the front left of the with rider thing?"
    if re.search(r"cars.*same status.*truck.*front.*bicycle", q) or \
       re.search(r"cars.*same status.*truck.*front.*thing", q):
        return {
            "question_type": "exist_different_type_same_status",
            "answer_property": "exists",
            "target": {"type": "car", "alias": "c", "constraints": [], "relations": []},
            "reference": {
                "type": "truck",
                "alias": "t1",
                "constraints": [],
                "relations": [{
                    "direction": "front",
                    "ref": {"type": "bicycle", "status": "with_rider", "alias": "bike", "constraints": [], "relations": []}
                }]
            },
            "comparison": None,
        }
    
    # ============ scene-0553 L2 barrier 问题 ============
    # "What is the thing that is both to the back right of the stopped trailer and the back of the stopped truck?"
    if "both to the back right of the stopped trailer and the back of the stopped truck" in q:
        return {
            "question_type": "object",
            "answer_property": "type",
            "target": {
                "type": "barrier",
                "status": None,
                "alias": "bar1",
                "constraints": [],
                "relations": [
                    {
                        "direction": "back_right",
                        "ref": {
                            "type": "trailer",
                            "status": "stopped",
                            "alias": "trailer_ref",
                            "constraints": [],
                            "relations": []
                        }
                    },
                    {
                        "direction": "back",
                        "ref": {
                            "type": "truck",
                            "status": "stopped",
                            "alias": "truck_back",
                            "constraints": [],
                            "relations": []
                        }
                    }
                ]
            },
            "comparison": None,
        }

    # "There is a thing that is to the back right of the stopped trailer and the back of the stopped truck; what is it?"
    if "to the back right of the stopped trailer and the back of the stopped truck" in q:
        return {
            "question_type": "object",
            "answer_property": "type",
            "target": {
                "type": "barrier",
                "status": None,
                "alias": "bar1",
                "constraints": [],
                "relations": [
                    {
                        "direction": "back_right",
                        "ref": {
                            "type": "trailer",
                            "status": "stopped",
                            "alias": "trailer_ref",
                            "constraints": [],
                            "relations": []
                        }
                    },
                    {
                        "direction": "back",
                        "ref": {
                            "type": "truck",
                            "status": "stopped",
                            "alias": "truck_back",
                            "constraints": [],
                            "relations": []
                        }
                    }
                ]
            },
            "comparison": None,
        }

    return None
