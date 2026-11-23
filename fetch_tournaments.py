import os
import requests
import time
import json
import hashlib
import duckdb

from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

# --- Setup -------------------------------------------------------------------

# Read STARTGG_TOKEN from the .env file so the token never lives in the code
# (and never gets committed to GitHub).
load_dotenv()
token = os.getenv("STARTGG_TOKEN")

DB_PATH = "ga_smash.duckdb"

# start.gg's GraphQL endpoint. Every query goes to this one URL.
url = "https://api.start.gg/gql/alpha"

#Seconds to wait after each request. Start.gg allows 80 requests/minute

REQUEST_DELAY = 0.8

#Error constants
MAX_ATTEMPTS = 4

MIN_ENTRANTS = 2

CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

# Sent with every request so start.gg knows who is asking.
headers = {"Authorization": f"Bearer {token}"}

# GraphQL query: one page of past Ultimate tournaments in Georgia.
# Words starting with $ are placeholders; their values come from `variables`.
#   addrState "GA"     -> Georgia only
#   videogameIds 1386  -> Smash Ultimate's start.gg ID
#   past: true         -> tournaments that already happened
#   afterDate          -> only tournaments after this Unix timestamp
#   sortBy             -> newest first
query = """query GATournaments($perPage: Int, $afterDate: Timestamp, $page: Int) {
    tournaments(query: {
        perPage: $perPage
        page: $page
        sortBy: "startAt desc"
        filter: {
            addrState: "GA"
            videogameIds: [1386]
            past: true
            afterDate: $afterDate
        }
    }) {
        pageInfo { total totalPages }
        nodes {
            id
            name
            startAt
            numAttendees
        }
    }
}"""

events_query = """query TournamentEvents($tournamentId: ID!) {
    tournament(id: $tournamentId) {
        name
        events(filter: { videogameId: [1386] }) {
            id
            name
            numEntrants
            type
        }
    }
}"""

entrants_query = """query EventEntrants($eventId: ID!, $page: Int!, $perPage: Int!) {
    event(id: $eventId) {
        entrants(query: { page: $page, perPage: $perPage }) {
            nodes {
                id
                initialSeedNum
                standing { placement }
                participants { player { id gamerTag } }
            }
        }
    }
}"""


# --- Functions ---------------------------------------------------------------

def run_query(query, variables):
    """Send any GraphQL query to start.gg and return the JSON response as a dict.

    Generic on purpose: tournaments, events, sets, and standings queries all
    go through here, so caching, throttling, and retries only need to be
    written once, in this function.
    """
    
    key_text = json.dumps({"query": query, "variables": variables}, sort_keys=True)
    key = hashlib.sha256(key_text.encode()).hexdigest()
    path = os.path.join(CACHE_DIR, f"{key}.json")

    if os.path.exists(path):
        print("cache hit")
        with open(path) as f:
            data = json.load(f)
        return data
    

    for attempt in range(MAX_ATTEMPTS):
        response = requests.post(url, headers=headers, json={"query": query, "variables": variables})
        time.sleep(REQUEST_DELAY)
        print(f"attempt {attempt}: {response.status_code}")

        if response.status_code == 200:
            break

        if response.status_code == 429 or 500 <= response.status_code <= 599:
            if attempt != MAX_ATTEMPTS - 1:
                wait = 2 ** attempt
                print(f"retryable error {response.status_code}, waiting {wait}")
                time.sleep(wait)
        else:
            raise Exception(f"start.gg request failed with status: {response.status_code}")

    if response.status_code != 200:
        raise Exception(f"start.gg request failed with status: {response.status_code}")

    # Turn the response body (JSON text) into a Python dictionary.
    data = response.json()
    if "errors" in data:
        raise Exception(f"start.gg returned GraphQL errors: {data['errors']}")

    with open(path, "w") as f:
        json.dump(data, f)
    
    return data


def fetch_page(page, after_date):
    """Return one page (a list) of Georgia Ultimate tournaments.

    page:       which page to fetch, starting at 1
    after_date: Unix timestamp; only tournaments after this are returned

    Returns an empty list once we've gone past the last page.
    """
    variables = {"perPage": 50, "page": page, "afterDate": after_date}

    # Store what run_query returns. Variables created inside run_query
    # don't exist out here; only the returned value comes back.
    data = run_query(query, variables)

    # Dig into the response to get just the list of tournaments.
    nodes = data["data"]["tournaments"]["nodes"]

    return nodes

def fetch_entrants(event_id):
    entrants = []
    page = 1
    while True:
        data = run_query(entrants_query, {"eventId": event_id, "page": page, "perPage": 50})
        nodes = data["data"]["event"]["entrants"]["nodes"]
        if not nodes:
            break
        entrants.extend(nodes)
        if len(nodes) < 50:
            break
        page += 1
    return entrants

SIDE_EVENT_WORDS = ["redemption", "ladder", "squad strike", "doubles", "amateur", "grudge", "ice stage"]

def is_main_singles(event):
    name = event['name'].lower()
    if event['type'] != 1:
        return False
    if not event['numEntrants'] or event['numEntrants'] < MIN_ENTRANTS:
        return False
    for word in SIDE_EVENT_WORDS:
        if word in name:
            return False
    return True


# --- Main --------------------------------------------------------------------

# Rolling 12-month window, rounded to midnight UTC so the cache key is stable within a day.
start_date = int(
    (datetime.now(timezone.utc) - timedelta(days=365))
    .replace(hour=0, minute=0, second=0, microsecond=0)
    .timestamp()
)


all_tournaments = []
page = 1

# Keep requesting pages until start.gg sends back an empty one.
while True:
    page_results = fetch_page(page, start_date)

    # An empty list means there are no more pages.
    if not page_results:
        break

    # extend (not append) adds each tournament individually,
    # instead of adding the whole list as a single item.
    all_tournaments.extend(page_results)

    # Move on to the next page, otherwise we'd fetch page 1 forever.
    page += 1

# Sanity check: 627 as of Oct 22, 2026.
print(len(all_tournaments))

all_events = []

for t in all_tournaments:
    result = run_query(events_query, {"tournamentId": t["id"]})
    events = result["data"]["tournament"]["events"]

    # Track the biggest event that passes the filter. The main bracket
    # is almost always the largest; side events are smaller.
    best = None
    for e in events:
        if is_main_singles(e):
            if best is None or e["numEntrants"] > best["numEntrants"]:
                best = e

    # Some tournaments have no qualifying event (canceled, 0–1 entrants).
    if best is not None:
        all_events.append({
            "event_id": best["id"],
            "tournament_id": t["id"],
            "name": best["name"],
            "num_entrants": best["numEntrants"],
        })

all_entrants = []

for i, ev in enumerate(all_events, 1):
    for en in fetch_entrants(ev["event_id"]):
        # Guards: some entrants have no player linked or no standing (e.g. DQ'd).
        participants = en["participants"] or []
        player = participants[0]["player"] if participants else None
        standing = en["standing"]

        all_entrants.append((
            en["id"],
            ev["event_id"],
            player["id"] if player else None,
            player["gamerTag"] if player else None,
            en["initialSeedNum"],
            standing["placement"] if standing else None,
        ))

    if i % 50 == 0:
        print(f"{i}/{len(all_events)} events")

print(len(all_events))


# --- Load into DuckDB --------------------------------------------------------

# Opens the database file, or creates it the first time.
con = duckdb.connect(DB_PATH)

# CREATE OR REPLACE wipes and rebuilds the table on every run, so re-running
# the script never leaves duplicate rows.
# PRIMARY KEY makes DuckDB throw an error if an ID shows up twice. That's a free data check.
con.execute("""
CREATE OR REPLACE TABLE tournaments (
    tournament_id BIGINT PRIMARY KEY,
    name          VARCHAR,
    start_at      TIMESTAMPTZ,
    num_attendees INTEGER
)
""")

con.execute("""
CREATE OR REPLACE TABLE events (
    event_id      BIGINT PRIMARY KEY,
    tournament_id BIGINT,
    name          VARCHAR,
    num_entrants  INTEGER
)
""")

# executemany runs one INSERT per tuple. The ? marks are filled in from the tuple, in order.
# start.gg gives startAt as a Unix timestamp; to_timestamp() turns it into a real date.
con.executemany(
    "INSERT INTO tournaments VALUES (?, ?, to_timestamp(?), ?)",
    [(t["id"], t["name"], t["startAt"], t["numAttendees"]) for t in all_tournaments],
)

con.executemany(
    "INSERT INTO events VALUES (?, ?, ?, ?)",
    [(e["event_id"], e["tournament_id"], e["name"], e["num_entrants"]) for e in all_events],
)

con.execute("""
CREATE OR REPLACE TABLE entrants (
    entrant_id BIGINT PRIMARY KEY,
    event_id   BIGINT,
    player_id  BIGINT,
    gamer_tag  VARCHAR,
    seed       INTEGER,
    placement  INTEGER
)
""")

con.executemany("INSERT INTO entrants VALUES (?, ?, ?, ?, ?, ?)", all_entrants)

con.close()
print("loaded into", DB_PATH)
