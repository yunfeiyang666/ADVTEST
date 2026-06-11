"""调试Cypher提取过程"""

llm_output = """【CYPHER】
MATCH (bike:Object) WHERE bike.type='bicycle'
WITH bike.status AS refStatus, bike.unique_id AS refId LIMIT 1
MATCH (other:Object)
WHERE other.type IN ['ego','car','truck','bus','bicycle','motorcycle','trailer','pedestrian']
  AND other.status = refStatus
  AND other.unique_id <> refId
RETURN count(other) AS count
【/CYPHER】"""

import re

# 模拟提取【CYPHER】块
block_match = re.search(r"【CYPHER】(.*?)【/CYPHER】", llm_output, flags=re.DOTALL)
if block_match:
    candidate_text = block_match.group(1).strip()
    print("提取的候选文本:")
    print(candidate_text)
    print("\n" + "="*60 + "\n")

# 模拟extract_single_query函数
def extract_single_query_test(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""

    collected = []
    started = False
    seen_return = False

    for ln in lines:
        stripped = ln.strip()
        upper_ln = stripped.upper()

        is_start = upper_ln.startswith(("MATCH ", "MATCH(", "MERGE ", "CREATE ", "CALL ", "WITH ", "UNWIND ", "OPTIONAL ", "RETURN "))
        
        print(f"处理行: {stripped[:50]}")
        print(f"  is_start={is_start}, started={started}, seen_return={seen_return}")
        
        if not started:
            if is_start:
                started = True
                collected.append(stripped)
                print(f"  → 开始收集")
                if upper_ln.startswith("RETURN") and "}" in stripped:
                    seen_return = True
                    print(f"  → 遇到RETURN且有}}，break")
                    break
                if " RETURN " in upper_ln:
                    seen_return = True
                    print(f"  → 遇到RETURN，break")
                    break
            continue

        if not seen_return:
            collected.append(stripped)
            print(f"  → 收集")
            if " RETURN " in upper_ln or upper_ln.startswith("RETURN"):
                seen_return = True
                print(f"  → 遇到RETURN，break")
                break
        else:
            print(f"  → 已见RETURN，break")
            break

    print(f"\n收集的行数: {len(collected)}")
    return "\n".join(collected).strip().rstrip(";")

result = extract_single_query_test(candidate_text)
print("\n" + "="*60)
print("最终提取的Cypher:")
print(result)
