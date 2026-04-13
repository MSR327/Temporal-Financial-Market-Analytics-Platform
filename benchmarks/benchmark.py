import os
import time
from statistics import mean

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


def timed_runs(cur, query, params=None, runs=5):
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        cur.execute(query, params or ())
        cur.fetchall()
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)
    return mean(timings)


def speedup(base_ms, candidate_ms):
    if candidate_ms <= 0:
        return "N/A"
    return f"{(base_ms / candidate_ms):.2f}x"


def print_table(rows):
    headers = ["Benchmark", "Method", "Avg Time (ms)", "Speedup"]
    widths = [30, 55, 14, 10]
    line = "+-" + "-+-".join("-" * w for w in widths) + "-+"
    print(line)
    print(
        "| "
        + " | ".join(h.ljust(w) for h, w in zip(headers, widths))
        + " |"
    )
    print(line)
    for r in rows:
        print(
            "| "
            + " | ".join(str(c).ljust(w) for c, w in zip(r, widths))
            + " |"
        )
    print(line)


def main():
    conn = get_conn()
    conn.autocommit = True
    with conn.cursor() as cur:
        benchmark_rows = []

        # 1a) Latest price lookup
        q_cache = "SELECT asset_id, price, time FROM latest_prices_cache"
        q_distinct = """
            SELECT DISTINCT ON (asset_id) asset_id, price, time
            FROM market_data
            ORDER BY asset_id, time DESC
        """
        cache_ms = timed_runs(cur, q_cache)
        distinct_ms = timed_runs(cur, q_distinct)
        benchmark_rows.append(
            ("Latest price lookup", "latest_prices_cache", f"{cache_ms:.2f}", speedup(distinct_ms, cache_ms))
        )
        benchmark_rows.append(
            ("Latest price lookup", "DISTINCT ON market_data", f"{distinct_ms:.2f}", "1.00x")
        )

        # 1b) OHLC aggregation
        q_cagg = """
            SELECT bucket, asset_id, open, high, low, close
            FROM market_data_daily
            WHERE bucket >= NOW() - INTERVAL '30 days'
            ORDER BY bucket ASC
        """
        q_manual = """
            SELECT time_bucket('1 day', time) AS bucket, asset_id,
                   FIRST(price, time) AS open,
                   MAX(price) AS high,
                   MIN(price) AS low,
                   LAST(price, time) AS close
            FROM market_data
            WHERE time >= NOW() - INTERVAL '30 days'
            GROUP BY bucket, asset_id
            ORDER BY bucket ASC
        """
        cagg_ms = timed_runs(cur, q_cagg)
        manual_ms = timed_runs(cur, q_manual)
        benchmark_rows.append(
            ("OHLC aggregation", "market_data_daily (continuous agg)", f"{cagg_ms:.2f}", speedup(manual_ms, cagg_ms))
        )
        benchmark_rows.append(
            ("OHLC aggregation", "manual time_bucket on market_data", f"{manual_ms:.2f}", "1.00x")
        )

        # 1c) Portfolio history range query (hypertable vs regular temp table)
        cur.execute("DROP TABLE IF EXISTS portfolio_history_temp")
        cur.execute(
            """
            CREATE TEMP TABLE portfolio_history_temp AS
            SELECT * FROM portfolio_history
            """
        )
        q_hyper = """
            SELECT user_id, time, total_value
            FROM portfolio_history
            WHERE time >= NOW() - INTERVAL '30 days'
            ORDER BY time DESC
        """
        q_temp = """
            SELECT user_id, time, total_value
            FROM portfolio_history_temp
            WHERE time >= NOW() - INTERVAL '30 days'
            ORDER BY time DESC
        """
        hyper_ms = timed_runs(cur, q_hyper)
        temp_ms = timed_runs(cur, q_temp)
        benchmark_rows.append(
            ("Portfolio history range query", "portfolio_history hypertable", f"{hyper_ms:.2f}", speedup(temp_ms, hyper_ms))
        )
        benchmark_rows.append(
            ("Portfolio history range query", "portfolio_history_temp regular table", f"{temp_ms:.2f}", "1.00x")
        )

        # 1d) SMA-7 window function on last 1000 rows for one asset
        q_sma = """
            WITH latest_asset AS (
                SELECT asset_id
                FROM market_data
                GROUP BY asset_id
                ORDER BY COUNT(*) DESC
                LIMIT 1
            ),
            last_rows AS (
                SELECT md.asset_id, md.time, md.price
                FROM market_data md
                JOIN latest_asset la ON md.asset_id = la.asset_id
                ORDER BY md.time DESC
                LIMIT 1000
            )
            SELECT
                time,
                price,
                AVG(price) OVER (
                    PARTITION BY asset_id
                    ORDER BY time
                    ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
                ) AS sma_7
            FROM (
                SELECT * FROM last_rows ORDER BY time ASC
            ) ordered_rows
        """
        sma_ms = timed_runs(cur, q_sma)
        benchmark_rows.append(
            ("SMA-7 window function", "window function over last 1000 rows", f"{sma_ms:.2f}", "N/A")
        )

        print("\nTimescaleDB Trading Benchmark Results\n")
        print_table(benchmark_rows)

        # 4) EXPLAIN ANALYZE summary for hypertable OHLC query
        cur.execute(
            """
            EXPLAIN ANALYZE
            SELECT bucket, asset_id, open, high, low, close
            FROM market_data_daily
            WHERE bucket >= NOW() - INTERVAL '30 days'
            ORDER BY bucket ASC
            """
        )
        plan = [r[0] for r in cur.fetchall()]
        print("\nEXPLAIN ANALYZE (first 5 lines) - Hypertable OHLC query")
        for line in plan[:5]:
            print(line)

    conn.close()


if __name__ == "__main__":
    main()
