# Runs every gold query with no Gemini calls, so you can sanity-check answers for free.
from evals import EVALS
from ask import run_sql

for i, case in enumerate(EVALS, 1):
    cols, rows = run_sql(case["gold_sql"])
    print(f"{i}. {case['question']}")
    print(f"   {len(rows)} rows, first few: {rows[:3]}\n")