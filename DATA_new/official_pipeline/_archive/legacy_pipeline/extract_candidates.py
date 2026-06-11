"""
从 verify_cypher 中提取候选集对象
"""
import re
from typing import List


def extract_candidates_from_cypher(verify_cypher: str) -> List[str]:
    if not verify_cypher or not verify_cypher.strip():
        return []

    candidates = set()

    # 提取 unique_id: 'xxx'
    pattern1 = r"unique_id:\s*['\"]([^'\"]+)['\"]"
    matches1 = re.findall(pattern1, verify_cypher)
    candidates.update(matches1)

    # 提取 unique_id = 'xxx'
    pattern2 = r"unique_id\s*=\s*['\"]([^'\"]+)['\"]"
    matches2 = re.findall(pattern2, verify_cypher)
    candidates.update(matches2)

    # 提取 IN [...] 列表
    pattern3 = r"IN\s*\[([^\]]+)\]"
    matches3 = re.findall(pattern3, verify_cypher)
    for match in matches3:
        ids = re.findall(r"['\"]([^'\"]+)['\"]", match)
        candidates.update(ids)

    return sorted(list(candidates))


def extract_candidates_from_verify_text(verify_text: str) -> List[str]:
    if not verify_text or not verify_text.strip():
        return []

    candidates = set()

    # 提取 candidates: [...]
    pattern = r"candidates?:\s*\[([^\]]+)\]"
    matches = re.findall(pattern, verify_text, re.IGNORECASE)
    for match in matches:
        ids = re.findall(r"['\"]([^'\"]+)['\"]", match)
        candidates.update(ids)

    # 提取 ids: [...]
    pattern2 = r"ids?:\s*\[([^\]]+)\]"
    matches2 = re.findall(pattern2, verify_text, re.IGNORECASE)
    for match in matches2:
        ids = re.findall(r"['\"]([^'\"]+)['\"]", match)
        candidates.update(ids)

    return sorted(list(candidates))


def expand_l0_with_candidates(l0_base: List[str], verify_cypher: str, verify_text: str) -> List[str]:
    """返回 QA 真正涉及的 L0 节点。

    旧版本会从 verify_cypher 中抽取所有 literal unique_id，甚至把候选/过滤条件里的
    节点也加入 l0_objects，导致落盘 coverage 字段虚高。现在只保留：
      1) path 上的基础节点；
      2) verify_text ids=[...] 中真实返回的节点。
    """
    all_nodes = set(l0_base)
    text_candidates = extract_candidates_from_verify_text(verify_text)
    all_nodes.update(text_candidates)
    return sorted(list(all_nodes))
