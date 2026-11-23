import duckdb

con = duckdb.connect("ga_smash.duckdb", read_only=True)
print(con.sql("SELECT COUNT(*) FROM tournaments"))
print(con.sql("SELECT COUNT(*) FROM events"))

print(con.sql("""
SELECT t.name AS tournament, e.name AS event, e.num_entrants, e.event_id
FROM events e
JOIN tournaments t ON e.tournament_id = t.tournament_id
ORDER BY e.num_entrants DESC
LIMIT 10
"""))

print(con.sql("SELECT COUNT(*) FROM entrants"))
print(con.sql("SELECT SUM(num_entrants) FROM events"))
print(con.sql("""
SELECT COUNT(*) FILTER (WHERE player_id IS NULL) AS no_player,
       COUNT(*) FILTER (WHERE seed IS NULL)      AS no_seed,
       COUNT(*) FILTER (WHERE placement IS NULL) AS no_placement
FROM entrants
"""))