import json
import advtest_env
from gap_pipeline.l2_llm_client import LLMClient

advtest_env.load_advtest_env()
c = LLMClient.from_env()
payload = {
    "model": c.model,
    "messages": [
        {"role": "system", "content": "Return strict JSON only."},
        {"role": "user", "content": 'Return {"nodes":["ego"],"edges":[]} as JSON only.'},
    ],
    "temperature": 0,
    "max_tokens": 2048,
}
data = c._post_json("/chat/completions", payload)
print(json.dumps(data, ensure_ascii=False, indent=2))

