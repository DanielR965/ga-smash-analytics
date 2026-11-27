import time
from collections import Counter
from ask import ask, run_sql, MODEL

EVALS = [
    {
        "question": "How many tournaments are in the database?",
        "gold_sql": "SELECT COUNT(*) FROM tournaments",
    },

    {
        "question": "How many events had 64 or more entrants? Return a single number.",
        "gold_sql": "SELECT COUNT(*) FROM events WHERE num_entrants >= 64",
    },

    {
        "question": "For each tournament whose main event had at least 100 entrants, return the tournament name and the event's number of entrants.",
        "gold_sql": "SELECT t.name, e.num_entrants FROM events e JOIN tournaments t ON e.tournament_id = t.tournament_id WHERE e.num_entrants >= 100",
    },

    {
        "question": "Return the player_id and number of events entered for every player who entered at least 20 events.",
        "gold_sql": "SELECT player_id, COUNT(*) FROM entrants GROUP BY player_id HAVING COUNT(*) >= 20",
    },

    {
        "question": "How many tournaments started in each month? Return the month (as date_trunc('month', start_at)) and the tournament count.",
        "gold_sql": "SELECT date_trunc('month', start_at) AS month, COUNT(*) FROM tournaments GROUP BY month",
    },

    {
        "question": "How many entrants placed better than their seed? Ignore entrants with no placement. Return a single number.",
        "gold_sql": "SELECT COUNT(*) FROM entrants WHERE placement IS NOT NULL AND placement < seed",
    },
]


def normalize(rows):
    """Turn rows into a Counter so row ORDER doesn't matter but DUPLICATES do.
    Floats are rounded so 2.3333333 and 2.33 count as equal."""
    return Counter(
        tuple(round(v, 2) if isinstance(v, float) else v for v in row)
        for row in rows
    )


def results_match(gold_rows, pred_rows):
    ...  # you write this (one line)
    return normalize(gold_rows) == normalize(pred_rows)


def main():
    passed = 0
    errors = 0
    for i, case in enumerate(EVALS, 1):
        print(f"running {i}/{len(EVALS)}...", flush=True)
        _, gold_rows = run_sql(case["gold_sql"])
        try:
            sql, _, pred_rows = ask(case["question"])
            ok = results_match(gold_rows, pred_rows)
            note = ""
        except Exception as e:  # model error, guardrail block, or 503
            sql, ok, note = None, False, f"error: {e}"
            errors += 1

        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {i}. {case['question']} {note}")
        if not ok and sql:
            print("    model SQL:", " ".join(sql.split()))
        time.sleep(7)  # stay under the free tier's requests-per-minute limit

    answered = len(EVALS) - errors
    print(f"\n{MODEL}: {passed}/{len(EVALS)} = {passed / len(EVALS):.0%}")
    print(f"errors (API/guardrail, not wrong SQL): {errors}")
    if answered:
        print(f"accuracy on answered questions: {passed}/{answered} = {passed / answered:.0%}")

 
if __name__ == "__main__":
    main()



