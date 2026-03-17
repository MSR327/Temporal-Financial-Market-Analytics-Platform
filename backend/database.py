import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "temporal")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "051223")
DB_PORT = os.getenv("DB_PORT", "5434")

# Create connection pool (Threaded for Flask)
db_pool = psycopg2.pool.ThreadedConnectionPool(
    1, 20,
    host=DB_HOST,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASS,
    port=DB_PORT
)

def get_db_connection():
    return db_pool.getconn()

def release_db_connection(conn):
    db_pool.putconn(conn)

def execute_query(query, params=None, fetch=False):
    conn = get_db_connection()
    try:
        conn.autocommit = False # Ensure we control transactions
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                result = cur.fetchall()
                conn.commit()
                return result
            conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"DATABASE ERROR: {e}")
        raise e
    finally:
        release_db_connection(conn)

def init_db():
    # Read schema.sql and execute it
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    with open(schema_path, "r") as f:
        schema_sql = f.read()
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
            conn.commit()
    finally:
        release_db_connection(conn)
