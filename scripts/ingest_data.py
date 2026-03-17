import os
import time
import random
import requests
import yfinance as yf
from datetime import datetime
import psycopg2
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "temporal")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "8978770469")
DB_PORT = os.getenv("DB_PORT", "5432")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )

def insert_market_price(asset_id, price, source='simulated'):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO market_data (asset_id, price, time, source) VALUES (%s, %s, %s, %s)",
                (asset_id, price, datetime.now(), source)
            )
            conn.commit()
    except Exception as e:
        print(f"Error inserting price: {e}")
    finally:
        conn.close()

def record_portfolio_history():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT record_portfolio_history()")
            conn.commit()
    except Exception as e:
        print(f"Error recording portfolio history: {e}")
    finally:
        conn.close()

def get_assets():
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT asset_id, symbol, type FROM assets")
            return cur.fetchall()
    finally:
        conn.close()

def simulate_prices(assets, interval=1):
    print(f"Starting ultra-fast data ingestion (interval: {interval}s)...")
    prices = {a[1]: random.uniform(50000, 60000) if a[2] == 'crypto' else random.uniform(100, 500) for a in assets}
    
    while True:
        for asset_id, symbol, asset_type in assets:
            volatility = 0.005 if asset_type == 'stock' else 0.02
            prices[symbol] *= (1 + random.uniform(-volatility, volatility))
            insert_market_price(asset_id, prices[symbol], 'simulated')
        
        # Record portfolio history every cycle for high-resolution graphs
        record_portfolio_history()
        # Suppress log to prevent terminal clutter
        # print(f"[{datetime.now().strftime('%H:%M:%S')}] Market updated.")
        time.sleep(interval)

def fetch_real_prices(assets, interval=60):
    print(f"Starting real-time data ingestion (interval: {interval}s)...")
    while True:
        for asset_id, symbol, asset_type in assets:
            try:
                if asset_type == 'crypto':
                    # Binance API for crypto
                    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
                    response = requests.get(url)
                    price = float(response.json()['price'])
                else:
                    # yfinance for stocks
                    ticker = yf.Ticker(symbol)
                    price = ticker.fast_info['last_price']
                
                insert_market_price(asset_id, price, 'api')
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
        
        record_portfolio_history()
        time.sleep(interval)

if __name__ == "__main__":
    assets = get_assets()
    if not assets:
        print("No assets found in database. Please run schema initialization first.")
        exit(1)
    
    # Choose mode based on environment or user preference
    mode = os.getenv("INGESTION_MODE", "simulated")
    interval = int(os.getenv("INGESTION_INTERVAL", 2))
    
    if mode == "simulated":
        simulate_prices(assets, interval)
    else:
        fetch_real_prices(assets, 60)
