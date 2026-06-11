"""Validate V12 Excel output: iteration_count, cypher_question, timestamps."""
import openpyxl
from collections import Counter

wb = openpyxl.load_workbook("E:/Project/ADVTEST/RQ.xlsx", read_only=True, data_only=True)
ws = wb["question-answer-our"]
rows = list(ws.iter_rows(values_only=True))
header = list(rows[0])
data   = rows[1:]

print(f"Total generated rows: {len(data)}")
print(f"Header: {header}\n")

# Show first 6 rows in detail
for i, r in enumerate(data[:6], 1):
    d = dict(zip(header, r))
    print(f"--- Row {i} ---")
    print(f"  question_id            : {d['question_id']}")
    print(f"  ts_start               : {d['timestamp_start']}")
    print(f"  ts_llm                 : {d['timestamp_llm']}")
    print(f"  ts_cypher_return       : {d['timestamp_cypher_return']}")
    print(f"  ts_end                 : {d['timestamp_end']}")
    ts_diff = (str(d['timestamp_end']) != str(d['timestamp_start']))
    print(f"  ts_start != ts_end?    : {ts_diff}")
    print(f"  iteration_count        : {d['iteration_count']}")
    print(f"  question_type          : {d['question_type']}")
    print(f"  complexity             : {d['complexity']}")
    print(f"  gap_cell               : {d['gap_cell']}")
    cypher = str(d.get("cypher question") or "")
    print(f"  cypher_question (len={len(cypher)}): {cypher[:90].strip()}")
    print(f"  natural_q              : {str(d['natural language question'])[:70]}")
    print(f"  answer                 : {d['answer']}")
    print()

# iteration_count distribution
iter_vals = [r[header.index("iteration_count")] for r in data if r[header.index("iteration_count")] is not None]
print("iteration_count distribution:", dict(Counter(iter_vals).most_common(10)))

# cypher_question non-empty count
cyp_col = header.index("cypher question")
n_cypher_filled = sum(1 for r in data if r[cyp_col])
print(f"cypher_question non-empty   : {n_cypher_filled}/{len(data)}")

# question_type distribution
qt_col = header.index("question_type")
print("question_type distribution  :", dict(Counter(r[qt_col] for r in data).most_common()))

wb.close()
