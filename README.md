# Temporal Financial Market Analytics Platform

A DBMS-based trading simulation and analytics platform built with **PostgreSQL**, **TimescaleDB**, and **Flask**.

## Features

### Trading System
- **Market Orders**: Instant buy/sell at current market prices
- **Limit Orders**: Set target prices for future execution
- **Stop-Loss Orders**: Automatic sell when price drops to target
- **Order Expiration**: Time-limited orders that auto-cancel

### Portfolio Management
- **Real-time Holdings**: Current positions with live P/L calculation
- **Auto-calculated Average Buy Price**: Proper cost basis tracking
- **Wallet System**: Deposits, withdrawals, and automatic balance updates
- **Wallet History**: Complete audit trail of all wallet transactions

### Market Data & Analytics
- **25 Pre-loaded Assets**: 12 Cryptocurrencies + 13 Stocks
- **Real-time Price Charts**: 1D, 1M, 3M, 6M, 1Y timeframes
- **OHLC Candlesticks**: Daily Open, High, Low, Close aggregation
- **Order Book**: Live bid/ask depth visualization
- **Recent Trades**: Real-time market trade feed

### Database Features (TimescaleDB)
- **Hypertable Partitioning**: Automatic time-based data chunking for `market_data`, `orders`, `trades`, `realized_pnl`
- **Continuous Aggregates**: Pre-computed daily OHLC data for fast chart queries
- **Data Compression**: 10-20x compression on historical data (older than 7 days)
- **Bi-temporal Portfolio Model**: Query portfolio state at any point in time

### Automated Business Logic
- **Auto-Create Wallet**: Trigger automatically creates wallet on user signup
- **Auto-Update Portfolio**: Triggers maintain portfolio on every trade
- **Audit Logging**: All wallet changes logged with before/after values
- **Background Processing**: Scheduled jobs process limit orders every 30 seconds

## Project Structure
```
/backend          - Flask API server and database layer
/scripts          - Real-time data ingestion from Binance & Yahoo Finance
/static           - CSS styling
/templates        - HTML templates with embedded JavaScript
schema.sql        - Complete database schema (TimescaleDB)
/benchmarks       - Performance benchmarking scripts
```

## Prerequisites
1. **PostgreSQL 14+ with TimescaleDB 2.12+**
2. **Python 3.9+**

## Setup Instructions

### 1. Database Setup
```bash
# Create database
psql -U postgres -c "CREATE DATABASE temporal;"

# Enable TimescaleDB extension
psql -U postgres -d temporal -c "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"

# Initialize schema
psql -U postgres -d temporal -f schema.sql
```

### 2. Environment Configuration
Create a `.env` file in the root directory:
```env
DB_HOST=localhost
DB_NAME=temporal
DB_USER=postgres
DB_PASS=your_password
DB_PORT=5432
FLASK_SECRET_KEY=your_secret_key_here
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Platform

#### Terminal 1: Backend API
```bash
cd backend
python app.py
```

#### Terminal 2: Data Ingestion
```bash
cd scripts
python ingest_data.py
```

## Database Schema Highlights

### TimescaleDB Features Used
```sql
-- Hypertable (time-based partitioning)
SELECT create_hypertable('market_data', 'time');

-- Continuous Aggregate (pre-computed daily OHLC)
CREATE MATERIALIZED VIEW market_data_daily
WITH (timescaledb.continuous) AS ...

-- Data Compression (after 7 days)
ALTER TABLE market_data SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'asset_id'
);
```

### Triggers for Automated Logic
| Trigger | Function |
|---------|----------|
| `trg_create_wallet` | Auto-creates wallet on user signup |
| `trg_wallet_touch_updated_at` | Updates timestamp on wallet changes |
| `trg_audit_wallet_changes` | Logs all balance changes to audit_logs |
| `trg_update_latest_price_cache` | Keeps price cache updated |
| `trg_update_portfolio_after_trade` | Maintains bi-temporal portfolio |

### Stored Procedures
| Function | Purpose |
|----------|---------|
| `place_order()` | Creates market/limit/stop-loss orders |
| `execute_trade()` | Validates and executes trades |
| `process_limit_orders()` | Background processor for pending orders |
| `expire_stale_orders()` | Auto-cancels expired orders |

## Technologies Used

| Layer | Technology |
|-------|------------|
| Database | PostgreSQL + TimescaleDB |
| Backend | Flask, psycopg2, bcrypt |
| Frontend | HTML/CSS/JS (Jinja2 templates, Chart.js) |
| Task Scheduling | APScheduler |
| Data Sources | Binance API, Yahoo Finance (yfinance) |

## Security Features
- Password hashing with bcrypt
- Session-based authentication
- SQL injection prevention via parameterized queries
- Case-insensitive credentials with CITEXT extension