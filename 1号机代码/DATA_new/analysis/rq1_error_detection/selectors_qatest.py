import sys
import random
import re
from typing import List, Dict
from pathlib import Path

# Path resolution for QATest
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
QATEST_DIR = WORKSPACE_ROOT / "baselines" / "QATest"

# Insert path of QATest to sys.path
if str(QATEST_DIR) not in sys.path:
    sys.path.insert(0, str(QATEST_DIR))

try:
    from question_trans import (
        keybord_mistake,
        ocr_mistake,
        spelling_mistake,
        synonym_replace,
        adverbial_preposition,
        wps,
        double_question_mark
    )
    HAS_QATEST = True
except Exception as e:
    print(f"Warning: Failed to import original QATest modules: {e}")
    HAS_QATEST = False

def extract_string(augmented) -> str:
    """Helper to extract a string if nlpaug returns a list."""
    if isinstance(augmented, list) and len(augmented) > 0:
        return str(augmented[0])
    return str(augmented)

def mutate_question(q_text: str, seed: int = 42) -> str:
    """
    Apply a random metamorphic mutation from the original QATest codebase.
    """
    if not HAS_QATEST:
        # Fallback to simple regex/string manipulation if imports failed
        return q_text + "?"
        
    rng = random.Random(seed)
    
    # QATest operators:
    # 0: keybord_mistake, 1: ocr_mistake, 2: spelling_mistake, 3: synonym_replace, 
    # 4: adverbial_preposition, 5: insert_word, 6: back_translate, 7: entity_replace, 
    # 8: wps, 9: double_question_mark
    available_ops = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
    rng.shuffle(available_ops)
    
    for op in available_ops:
        try:
            if op == 0:
                res = keybord_mistake(q_text)
                return extract_string(res)
            elif op == 1:
                res = ocr_mistake(q_text)
                return extract_string(res)
            elif op == 2:
                res = spelling_mistake(q_text)
                return extract_string(res)
            elif op == 3:
                res = synonym_replace(q_text)
                return extract_string(res)
            elif op == 4:
                return adverbial_preposition(q_text)
            elif op == 8:
                return wps(q_text)
            elif op == 9:
                return double_question_mark(q_text)
            # Operators 5, 6, 7 require local models or online APIs which are unavailable:
            elif op in (5, 6, 7):
                continue
        except Exception:
            continue
            
    # Ultimate fallback if all selected mutations fail
    try:
        return double_question_mark(q_text)
    except Exception:
        return q_text


def select_and_mutate_qatest(questions: List[Dict], B: int, seed: int = 42) -> List[Dict]:
    """
    QATest strategy:
    1. Group questions by template family.
    2. Uniformly pick templates to build a representative subset of size B.
    3. Apply character and sentence level metamorphic text fuzzing to the selected questions.
    """
    if not questions:
        return []
        
    rng = random.Random(seed)
    
    # 1. Group questions by family
    family_groups = {}
    for q in questions:
        fam = str(q.get("l2_family") or q.get("template_id") or "general").strip().lower()
        family_groups.setdefault(fam, []).append(q)
        
    for fam in family_groups:
        rng.shuffle(family_groups[fam])
        
    selected = []
    
    # Uniformly pull from families up to budget B
    while len(selected) < B:
        active_families = [f for f, qs in family_groups.items() if len(qs) > 0]
        if not active_families:
            break
            
        chosen_family = rng.choice(active_families)
        q = family_groups[chosen_family].pop()
        selected.append(q)
        
    # 2. Mutate the selected questions textually
    fuzzed_selected = []
    for idx, q in enumerate(selected):
        # We must copy to avoid mutating the original candidate list
        q_copy = q.copy()
        original_text = q_copy["question"]
        
        # Unique seed per question
        q_seed = seed + idx + hash(original_text) % 1000
        mutated_text = mutate_question(original_text, q_seed)
        
        q_copy["question"] = mutated_text
        q_copy["is_fuzzed"] = True
        q_copy["qatest_mutated"] = True
        q_copy["original_question"] = original_text
        fuzzed_selected.append(q_copy)
        
    return fuzzed_selected
