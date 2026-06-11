import sys
sys.path.insert(0, r'E:\Project\ADVTEST\nuscenes_s3c_experiment')
from vqa_pipeline import config
import re

# 查找所有 {type 或 {ref 等模式
patterns = [r'\{type[^}]', r'\{ref[^}]', r'\{alias', r'\{target', r'\{other']

for pattern in patterns:
    matches = list(re.finditer(pattern, config.QUESTION_TO_CYPHER_PROMPT))
    if matches:
        print(f"\n找到 {len(matches)} 个匹配: {pattern}")
        for m in matches[:2]:
            start = max(0, m.start()-30)
            end = min(len(config.QUESTION_TO_CYPHER_PROMPT), m.end()+30)
            print(f"  上下文: ...{repr(config.QUESTION_TO_CYPHER_PROMPT[start:end])}...")
