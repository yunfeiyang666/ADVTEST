import random
from typing import List, Dict, Set

# Import real QATest and QAAskeR implementations
from selectors_qatest import select_and_mutate_qatest
from selectors_qaasker import select_recursive_asking_qaasker

def get_normalized_family(q: Dict) -> str:
    """Normalize the family/template key from a question dict."""
    return str(q.get("l2_family") or q.get("template_id") or "general").strip().lower()

def select_ours_complete(questions: List[Dict], B: int, seed: int = 42) -> List[Dict]:
    """
    Ours (Complete): Selects the first B questions in their active greedy order.
    The input list must be pre-sorted in the order of generation/selection.
    """
    return questions[:B]

def select_ours_random(questions: List[Dict], B: int, seed: int = 42) -> List[Dict]:
    """
    Ours-Random (Ablation): Randomly samples B questions from the candidate pool.
    """
    if len(questions) <= B:
        return questions.copy()
    rng = random.Random(seed)
    return rng.sample(questions, B)

def select_qatest(questions: List[Dict], B: int, seed: int = 42) -> List[Dict]:
    """
    Qatest (Uniform Fuzzing): Simulates Qatest by choosing templates uniformly at random,
    and then applying character and word level metamorphic text mutations.
    """
    return select_and_mutate_qatest(questions, B, seed=seed)

def select_recursive_asking(questions: List[Dict], B: int, seed: int = 42) -> List[Dict]:
    """
    Recursive Asking (QAAskeR): Simulates query dependency chains with recursive asking.
    Picks starting questions and generates follow-up general verification questions.
    """
    return select_recursive_asking_qaasker(questions, B, seed=seed)
