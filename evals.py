import time
from collections import Counter
from ask import ask, run_sql

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

    {
        "question": "How many distinct players entered at least one event? Return a single number.",
        "gold_sql": "SELECT COUNT(DISTINCT player_id) FROM entrants",
    },

    {
        "question": "How many tournaments have no main event in the events table? Return a single number.",
        "gold_sql": "SELECT COUNT(*) FROM tournaments t LEFT JOIN events e ON t.tournament_id = e.tournament_id WHERE e.event_id IS NULL",
    },

    {
        "question": "Return the player_id and number of wins (placement 1) for every player with at least 5 wins.",
        "gold_sql": "SELECT player_id, COUNT(*) FROM entrants WHERE placement = 1 GROUP BY player_id HAVING COUNT(*) >= 5",
    },

    {
        "question": "Return the tournament name, num_attendees, and the main event's num_entrants for tournaments where num_attendees is more than twice the main event's num_entrants.",
        "gold_sql": "SELECT t.name, t.num_attendees, e.num_entrants FROM events e JOIN tournaments t ON e.tournament_id = t.tournament_id WHERE t.num_attendees > 2 * e.num_entrants",
    },

    {
        "question": "For players with at least 20 events where they have both a seed and a placement, return the player_id and the fraction of those events where they placed better than their seed.",
        "gold_sql": "SELECT player_id, AVG(CASE WHEN placement < seed THEN 1 ELSE 0 END) FROM entrants WHERE placement IS NOT NULL AND seed IS NOT NULL GROUP BY player_id HAVING COUNT(*) >= 20",
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
    return normalize(gold_rows) == normalize(pred_rows)


def main():
    passed = 0
    errors = 0
    models_used = Counter()
    for i, case in enumerate(EVALS, 1):
        print(f"running {i}/{len(EVALS)}...", flush=True)
        _, gold_rows = run_sql(case["gold_sql"])
        try:
            sql, model, _, pred_rows = ask(case["question"])
            models_used[model] += 1
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
    print(f"\n{passed}/{len(EVALS)} = {passed / len(EVALS):.0%}")
    print(f"answered by: {dict(models_used)}")
    print(f"errors (API/guardrail, not wrong SQL): {errors}")
    if answered:
        print(f"accuracy on answered questions: {passed}/{answered} = {passed / answered:.0%}")

 
if __name__ == "__main__":
    main()
