import sys
import random
import re
from typing import List, Dict
from pathlib import Path

# Path resolution for QAAskeR
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
QAASKER_TOOL_DIR = WORKSPACE_ROOT / "baselines" / "QAAskeR" / "tool"

# Insert to sys.path
if str(QAASKER_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(QAASKER_TOOL_DIR))
if str(QAASKER_TOOL_DIR / "wh_rules") not in sys.path:
    sys.path.insert(0, str(QAASKER_TOOL_DIR / "wh_rules"))

try:
    from Q2S import change
    from S2G import S2I
    HAS_QAASKER = True
    
    # Monkey patch to fix SOTA baseline infinite loop bugs in list_to_order
    def list_to_order_safe(sent, list_items):
        ctnu = False
        order = []
        start = 0
        num = -1
        max_loops = len(sent) * 10
        loop_count = 0
        try:
            while True:
                loop_count += 1
                if loop_count > max_loops:
                    break
                num += 1
                if num >= len(sent):
                    break
                if sent[num] in list_items:
                    if not ctnu:
                        start = num
                    order.append(sent[num])
                    ctnu = True
                    if len(order) == len(list_items):
                        c = [x for x in list_items if x not in order]
                        if not c:
                            break
                        else:
                            num = num - len(list_items) + 1
                            start = 0
                            order = []
                            ctnu = False
                else:
                    start = 0
                    order = []
                    ctnu = False
        except Exception:
            pass
        return start, order

    import wh_rules.how
    import wh_rules.howmany
    import wh_rules.what
    import wh_rules.when
    import wh_rules.where
    import wh_rules.which
    import wh_rules.who
    import wh_rules.whose
    import wh_rules.why
    
    for mod in [wh_rules.how, wh_rules.howmany, wh_rules.what, wh_rules.when, 
                wh_rules.where, wh_rules.which, wh_rules.who, wh_rules.whose, wh_rules.why]:
        if hasattr(mod, "list_to_order"):
            mod.list_to_order = list_to_order_safe
            
except Exception as e:
    print(f"Warning: Failed to import original QAAskeR modules: {e}")
    HAS_QAASKER = False

def clean_question_mark(text: str) -> str:
    return text.rstrip("?").strip()

def coordinate_question_for_qaasker(q_text: str) -> str:
    """
    Coordinating correction: NuScenes-QA specific templates are converted
    to standardized Wh-forms that the QAAskeR parser can understand.
    """
    q_clean = clean_question_mark(q_text)
    
    # 1. "Which [cat] can be found to the (.+)" -> "Which [cat] is located to the (.+)"
    # QAAskeR parser has poor support for "can be found" but handles "is located" perfectly.
    q_clean = re.sub(r"\bcan be found\b", "is located", q_clean, flags=re.IGNORECASE)
    
    # 2. "Identify the [cat] located to the (.+)" -> "Which [cat] is located to the (.+)"
    # QAAskeR parser doesn't support imperative questions starting with "Identify".
    q_clean = re.sub(r"^Identify the\b", "Which", q_clean, flags=re.IGNORECASE)
    
    # 3. "There is a [cat] to the (.+); what is it" -> "Which [cat] is located to the (.+)"
    q_clean = re.sub(r"^There is a ([a-zA-Z0-9_]+) to the (.+);\s*what is it", r"Which \1 is located to the \2", q_clean, flags=re.IGNORECASE)
    
    # 4. "Is [obj] closer to [obj1] or to [obj2]" -> "Which object is closer to [obj]"
    m = re.match(r"Is (.+?) closer to (.+?) or to (.+)", q_clean, re.IGNORECASE)
    if m:
        obj, obj1, obj2 = m.groups()
        return f"Which object is closer to {obj}"
        
    # 5. "Between [obj1] and [obj2], which one is closer to [obj3]" -> "Which object is closer to [obj3]"
    m = re.match(r"Between (.+?) and (.+?),\s*which one is closer to (.+)", q_clean, re.IGNORECASE)
    if m:
        obj1, obj2, obj3 = m.groups()
        return f"Which object is closer to {obj3}"
        
    # 6. "Standing at [obj1] and looking toward [obj2], is [obj3] to the left or the right" -> "Which side is [obj3] on"
    m = re.match(r"Standing at (.+?) and looking toward (.+?),\s*is (.+?) to the left or the right", q_clean, re.IGNORECASE)
    if m:
        obj1, obj2, obj3 = m.groups()
        return f"Which side is {obj3} on"
        
    # 7. "From [obj1], facing [obj2], which side is [obj3] on — left or right" -> "Which side is [obj3] on"
    m = re.match(r"From (.+?),\s*facing (.+?),\s*which side is (.+?) on — left or right", q_clean, re.IGNORECASE)
    if m:
        obj1, obj2, obj3 = m.groups()
        return f"Which side is {obj3} on"
        
    return q_clean

def generate_follow_up_fallback(q_text: str, answer: str, answer_type: str) -> tuple:
    """Fallback heuristics to generate follow-up when the parser fails."""
    ans_str = str(answer).strip()
    q_clean = clean_question_mark(q_text)
    
    if answer_type == "object" or "Which" in q_text or "What" in q_text or "Identify" in q_text:
        m = re.match(r"Which ([a-zA-Z0-9_]+) can be found (.+)", q_clean, re.IGNORECASE)
        if m:
            cat, rest = m.groups()
            return f"Is {ans_str} the {cat} that can be found {rest}?", "yes"
        m = re.match(r"Which ([a-zA-Z0-9_]+) is (.+)", q_clean, re.IGNORECASE)
        if m:
            cat, rest = m.groups()
            return f"Is {ans_str} the {cat} that is {rest}?", "yes"
        return f"Confirm that {ans_str} is the object referred to in: \"{q_text}\"?", "yes"
        
    elif answer_type == "choice" or "closer to" in q_text or "left or the right" in q_text:
        m = re.match(r"Is (.+?) closer to (.+?) or to (.+)", q_clean, re.IGNORECASE)
        if m:
            obj, obj1, obj2 = m.groups()
            obj2 = obj2.replace("to", "").strip()
            if ans_str.lower() == obj2.lower():
                return f"Is {obj} closer to {obj2} than to {obj1}?", "yes"
            else:
                return f"Is {obj} closer to {obj1} than to {obj2}?", "yes"
        return f"Is the answer {ans_str} for the question: \"{q_text}\"?", "yes"
        
    else:
        if ans_str.lower() in ("true", "yes", "correct"):
            return f"Is it true that {q_clean}?", "yes"
        else:
            return f"Is it true that {q_clean}?", "no"

def generate_follow_up(q_text: str, answer: str, answer_type: str) -> tuple:
    """
    Generate a follow-up general question (Yes/No) based on the original Wh-question and answer.
    First runs the original SOTA QAAskeR codebase modules with coordinating corrections.
    """
    ans_str = str(answer).strip()
    q_clean = clean_question_mark(q_text)
    
    # 1. Handle Boolean questions directly
    if answer_type == "boolean" or ans_str.lower() in ("true", "false", "yes", "no"):
        if ans_str.lower() in ("true", "yes", "correct"):
            return f"Is it true that {q_clean}?", "yes"
        else:
            return f"Is it true that {q_clean}?", "no"
            
    # 2. Try running original QAAskeR parser
    if HAS_QAASKER:
        try:
            coord_q = coordinate_question_for_qaasker(q_text)
            statement = change(coord_q, ans_str)
            if statement and statement != "None":
                general_q = S2I(statement)
                if general_q and general_q != "None":
                    return str(general_q), "yes"
        except Exception:
            pass
            
    # 3. Fallback if original QAAskeR fails
    return generate_follow_up_fallback(q_text, answer, answer_type)


def select_recursive_asking_qaasker(questions: List[Dict], B: int, seed: int = 42) -> List[Dict]:
    """
    QAAskeR strategy:
    1. Select starting question and follow up along overlapping footprint chains.
    2. For each selected original Wh-question, generate a follow-up general (yes/no) metamorphic question.
    3. Return B questions total (composed of original + follow-up pairs).
    """
    if not questions:
        return []
        
    if len(questions) <= B // 2:
        # Fallback if candidates are too few
        return questions.copy()
        
    rng = random.Random(seed)
    pool = questions.copy()
    rng.shuffle(pool)
    
    # We need to select N original questions such that N + N_followups = B
    # Since each original question has exactly 1 follow-up, N = B // 2
    N = (B + 1) // 2
    
    selected_originals = []
    visited_nodes = set()
    
    # 1. Pick a random starting question
    q_start = pool.pop(0)
    selected_originals.append(q_start)
    for n in (q_start.get("footprint_nodes") or []):
        visited_nodes.add(str(n))
        
    # 2. Recursive loop following overlapping chains
    while len(selected_originals) < N and pool:
        overlap_candidates = []
        for q in pool:
            q_nodes = set(str(n) for n in (q.get("footprint_nodes") or []))
            if q_nodes.intersection(visited_nodes):
                overlap_candidates.append(q)
                
        if overlap_candidates:
            q_next = rng.choice(overlap_candidates)
            pool.remove(q_next)
        else:
            q_next = pool.pop(0)
            
        selected_originals.append(q_next)
        for n in (q_next.get("footprint_nodes") or []):
            visited_nodes.add(str(n))
            
    # 3. Generate follow-up general questions
    combined_list = []
    for q in selected_originals:
        combined_list.append(q)
        
        # Create follow-up general question
        q_text = q["question"]
        ans = q["answer"]
        ans_type = q.get("answer_type") or "object"
        
        try:
            fq_text, fq_ans = generate_follow_up(q_text, ans, ans_type)
        except Exception:
            # Resilient fallback
            fq_text = f"Confirm that {ans} is correct for: \"{q_text}\"?"
            fq_ans = "yes"
            
        fq = q.copy()
        fq["question_id"] = str(q.get("question_id", "")) + "_followup"
        fq["question"] = fq_text
        fq["answer"] = fq_ans
        fq["answer_type"] = "boolean"
        fq["is_qaasker_followup"] = True
        fq["original_question"] = q_text
        
        combined_list.append(fq)
        
    # Slice to exactly B questions
    return combined_list[:B]
