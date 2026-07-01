import duckdb

def run_query(query):
    conn = duckdb.connect()

    result = conn.execute(query).fetchall()

    conn.close()

    return result