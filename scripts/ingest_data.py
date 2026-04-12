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
DB_PASS = os.getenv("DB_PASS", "051223")
DB_PORT = os.getenv("DB_PORT", "5434")

# Binance API configuration
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

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
                (asset_id, price, datetime.now(datetime.timezone.utc), source)
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

def has_historical_data(asset_id, days=30):
    """Check if the database already has historical data for this asset."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM market_data WHERE asset_id = %s AND time >= NOW() - INTERVAL '%s day'",
                (asset_id, days)
            )
            count = cur.fetchone()[0]
            return count > 10
    finally:
        conn.close()

def backfill_historical_data(assets, days=30):
    """Backfill historical data only if it's missing."""
    print(f"⌛ Checking for historical data ({days} days)...")
    
    missing_assets = []
    for asset in assets:
        if not has_historical_data(asset[0], days):
            missing_assets.append(asset)
    
    if not missing_assets:
        print("✅ Historical data already present. Skipping backfill.")
        refresh_aggregates()
        return

    print(f"⌛ Starting backfill for {len(missing_assets)} assets...")
    print("-" * 50)
    
    for asset_id, symbol, asset_type in missing_assets:
        try:
            if asset_type == 'crypto':
                # Binance Klines API for historical daily data
                ticker = f"{symbol}USDT"
                url = f"https://api.binance.com/api/v3/klines?symbol={ticker}&interval=1d&limit={days}"
                response = requests.get(url, timeout=10)
                data = response.json()
                
                for entry in data:
                    timestamp = datetime.fromtimestamp(entry[0] / 1000, tz=datetime.timezone.utc)
                    price = float(entry[4]) # Closing price
                    insert_market_price_historical(asset_id, price, timestamp, 'binance_history')
                
            else:
                # yfinance historical data
                ticker_obj = yf.Ticker(symbol)
                hist = ticker_obj.history(period=f"{days}d")
                
                for timestamp, row in hist.iterrows():
                    price = float(row['Close'])
                    dt = timestamp.to_pydatetime()
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                    insert_market_price_historical(asset_id, price, dt, 'yfinance_history')
            
            print(f"✅ Backfilled {symbol}")
            
        except Exception as e:
            print(f"❌ Error backfilling {symbol}: {e}")
    
    print("-" * 50)
    print("🚀 Backfill Complete! Refreshing TimescaleDB aggregates...")
    refresh_aggregates()

def refresh_aggregates():
    """Manually refresh continuous aggregates to show historical data immediately."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # This ensures the 1M chart works immediately after backfill
            cur.execute("CALL refresh_continuous_aggregate('market_data_daily', NULL, NULL);")
            conn.commit()
            print("✅ Aggregates Refreshed Successfully!")
    except Exception as e:
        print(f"⚠️ Could not refresh aggregates: {e}")
    finally:
        conn.close()

def insert_market_price_historical(asset_id, price, timestamp, source):
    """Helper to insert historical data with specific timestamps."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO market_data (asset_id, price, time, source) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (asset_id, price, timestamp, source)
            )
            conn.commit()
    except Exception as e:
        pass # Ignore duplicates if re-running
    finally:
        conn.close()

def fetch_market_prices(assets, interval=5):
    """Fetch real-time data from Binance (Crypto) and yfinance (Stocks)."""
    print(f"🚀 UPGRADED: Real-time Data Ingestion Active (Interval: {interval}s)")
    print("-" * 50)
    
    while True:
        for asset_id, symbol, asset_type in assets:
            try:
                if asset_type == 'crypto':
                    # Binance Public API (No key needed)
                    ticker = f"{symbol}USDT"
                    url = f"https://api.binance.com/api/v3/ticker/price?symbol={ticker}"
                    response = requests.get(url, timeout=5)
                    data = response.json()
                    price = float(data['price'])
                    source = 'Binance'
                else:
                    # yfinance Public API (No key needed)
                    ticker_obj = yf.Ticker(symbol)
                    # Get current price from fast_info
                    price = ticker_obj.fast_info['last_price']
                    source = 'yfinance'
                
                # Insert to DB with source tag
                insert_market_price(asset_id, price, source.lower())
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {symbol}: ₹{price:,.2f} ({source})")
                
            except Exception as e:
                print(f"❌ Error fetching {symbol}: {e}")
        
        # Sync portfolio values based on new prices
        record_portfolio_history()
        time.sleep(interval)

if __name__ == "__main__":
    print("Connecting to database...")
    try:
        assets = get_assets()
        if not assets:
            print("⚠️ No assets found. Please run schema.sql first.")
        else:
            # Step 1: Backfill 1 year of history (365 days)
            backfill_historical_data(assets, days=365)
            
            # Step 2: Start continuous real-time ingestion
            fetch_market_prices(assets, interval=5)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
