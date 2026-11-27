import os
import re
import duckdb
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
client = genai.Client(http_options=types.HttpOptions(timeout=60_000))  # reads GEMINI_API_KEY from the environment

#Tried in order; if one errors or times out (503/504 on the free tier), use the next.
MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
MODEL = MODELS[0]  # evals.py prints this in the score line
DB_PATH = "ga_smash.duckdb"
ALLOWED_TABLES = {"tournaments", "events", "entrants"}
MAX_ROWS = 200

SYSTEM_PROMPT = """You write DuckDB SQL for a database of Georgia Super Smash Bros. Ultimate
tournaments from the past 12 months (data from start.gg).

Tables:
tournaments(tournament_id BIGINT, name VARCHAR, start_at TIMESTAMPTZ, num_attendees INTEGER)
  - one row per tournament; num_attendees counts everyone registered, across all games
events(event_id BIGINT, tournament_id BIGINT, name VARCHAR, num_entrants INTEGER)
  - the main Ultimate singles bracket of a tournament (at most one per tournament)
entrants(entrant_id BIGINT, event_id BIGINT, player_id BIGINT, gamer_tag VARCHAR, seed INTEGER, placement INTEGER)
  - one row per player per event

Notes:
- seed: pre-tournament ranking within an event. 1 = top seed; lower number = stronger expected player.
- placement: final result. Lower is better (1 = winner). Ties are normal (two 5ths, two 7ths, four 9ths...). Some placements are NULL; exclude them with placement IS NOT NULL when using placement.
- An upset is when a player places better than their seed predicts (placement < seed) or worse (placement > seed).
- A player's gamer_tag can change between events. Identify players by player_id (GROUP BY player_id) and show a tag with MAX(gamer_tag) or the most recent one.

Rules:
- Return exactly one SQL SELECT statement. No explanation, no markdown.
- Use only the tables above.
"""


def generate_sql(question, bad_sql=None, error=None):
    """Ask the model for SQL. On a retry, show it the SQL that failed and the error."""
    content = f"Question: {question}"
    if bad_sql:
        content += f"\n\nThis SQL failed:\n{bad_sql}\nError: {error}\nWrite a corrected query."

    last_error = None
    for model in MODELS:
        try:
            resp = client.models.generate_content(
                model=model,
                contents=content,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            break  # got an answer, stop trying models
        except Exception as e:
            print(f"  {model} failed: {str(e)[:80]}", flush=True)
            last_error = e
    else:
        raise last_error  # every model failed
    text = resp.text.strip()
    # Models sometimes wrap SQL in ```sql fences anyway; strip them.
    return re.sub(r"^```(?:sql)?\s*|\s*```$", "", text).strip()


def validate_sql(sql):
    """Guardrails. Return the cleaned SQL, or raise ValueError."""
    s = sql.strip().rstrip(";").strip()
    lowered = s.lower()

    # 1. One statement only (a leftover ';' means a second statement)
    if ";" in s:
        raise ValueError("only one statement allowed")

    # 2. Read queries only
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise ValueError("only SELECT queries allowed")

    # 3. Table allowlist. DuckDB's own parser lists the tables a query uses.
    #    CTE names (WITH name AS (...)) aren't real tables, so allow those too.
    used = {t.lower() for t in duckdb.connect().get_table_names(s)}
    cte_names = set(re.findall(r"\b([a-z_]\w*)\s+as\s*\(", lowered))
    bad = used - ALLOWED_TABLES - cte_names
    if bad:
        raise ValueError(f"tables not allowed: {bad}")

    return s


def run_sql(sql):
    """Run on a READ-ONLY connection and cap the rows returned."""
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(MAX_ROWS)
        return cols, rows
    finally:
        con.close()


def ask(question):
    """Full flow with one retry. Returns (sql, cols, rows); raises if the retry also fails."""
    sql = generate_sql(question)
    try:
        sql = validate_sql(sql)
        return (sql, *run_sql(sql))
    except Exception as e:
        sql = generate_sql(question, bad_sql=sql, error=str(e))
        sql = validate_sql(sql)
        return (sql, *run_sql(sql))
    
if __name__ == "__main__":
    for bad in ["DROP TABLE events", "SELECT 1; DROP TABLE events", "SELECT * FROM secrets"]:
        try:
            validate_sql(bad)
            print("NOT BLOCKED:", bad)
        except ValueError as e:
            print("blocked:", bad, "->", e)

    sql, cols, rows = ask("Which 5 events had the most entrants?")
    print(sql)
    print(cols)
    for r in rows:
        print(r)