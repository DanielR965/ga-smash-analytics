import duckdb

con = duckdb.connect("ga_smash.duckdb", read_only=True)
print(con.sql("SELECT COUNT(*) FROM tournaments"))
print(con.sql("SELECT COUNT(*) FROM events"))