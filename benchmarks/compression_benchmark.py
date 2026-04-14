import os
import random
import time
from datetime import datetime, timedelta, timezone

import psycopg2
from dotenv import load_dotenv


load_dotenv()


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "temporal"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", ""),
        port=os.getenv("DB_PORT", "5434"),
    )


def measure_query_ms(cur, query, params=None, runs=5):
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        cur.execute(query, params or ())
        cur.fetchall()
        samples.append((time.perf_counter() - start) * 1000)
    return sum(samples) / len(samples)


def main():
    conn = get_conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("SELECT asset_id FROM assets ORDER BY asset_id LIMIT 5")
        asset_ids = [r[0] for r in cur.fetchall()]
        if not asset_ids:
            raise RuntimeError("No assets found. Seed assets first.")

        rows_to_insert = 100000
        now = datetime.now(timezone.utc)
        base = now - timedelta(days=60)

        print(f"Inserting {rows_to_insert} synthetic market_data rows...")
        insert_sql = """
            INSERT INTO market_data(asset_id, price, time, source)
            VALUES (%s, %s, %s, 'benchmark')
        """
        batch = []
        for i in range(rows_to_insert):
            aid = asset_ids[i % len(asset_ids)]
            price = round(50 + random.random() * 2000, 6)
            ts = base + timedelta(seconds=i * 30)
            batch.append((aid, price, ts))
            if len(batch) >= 5000:
                cur.executemany(insert_sql, batch)
                batch.clear()
        if batch:
            cur.executemany(insert_sql, batch)

        query = """
            SELECT asset_id, AVG(price), MIN(price), MAX(price)
            FROM market_data
            WHERE time >= NOW() - INTERVAL '30 days'
            GROUP BY asset_id
            ORDER BY asset_id
        """

        before_ms = measure_query_ms(cur, query)

        print("Applying compression to old chunks...")
        cur.execute(
            """
            ALTER TABLE market_data SET (
              timescaledb.compress,
              timescaledb.compress_segmentby = 'asset_id'
            )
            """
        )
        cur.execute("SELECT compress_chunk(c) FROM show_chunks('market_data', older_than => INTERVAL '7 days') c")

        after_ms = measure_query_ms(cur, query)

        print("\nCompression Benchmark Report")
        print("-" * 60)
        print(f"Rows inserted:                {rows_to_insert}")
        print(f"Avg query time (before):      {before_ms:.2f} ms")
        print(f"Avg query time (after):       {after_ms:.2f} ms")
        if after_ms > 0:
            print(f"Speedup:                      {before_ms / after_ms:.2f}x")
        print("-" * 60)

    conn.close()


if __name__ == "__main__":
    main()
