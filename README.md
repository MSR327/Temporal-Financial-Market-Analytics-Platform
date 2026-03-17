# Temporal Financial Market Analytics Platform

A full-stack trading simulation and analytics platform built with TimescaleDB, Flask, and Streamlit.

## Features
- **User System**: Secure registration, login, and auto-generated wallet (₹100,000).
- **Trading System**: Real-time simulated trading for Stocks and Crypto.
- **Portfolio Analytics**: Unrealized P/L tracking and historical wealth growth graphs.
- **Market Data Ingestion**: Supports both simulated (random) and real-time (API) data.
- **TimescaleDB Time-Series**: Implemented using hypertables for market data, portfolio history, orders, and trades.

## Project Structure
- `/backend`: Flask API server.
- `/frontend`: Streamlit dashboard.
- `/scripts`: Data ingestion scripts.
- `schema.sql`: Database schema (TimescaleDB).

## Prerequisites
1. **PostgreSQL with TimescaleDB**: Install PostgreSQL and the TimescaleDB extension. Create a database named `temporal_db`.
2. **Python 3.9+**: Recommended.

## Setup Instructions

### 1. Database Initialization
1. Ensure PostgreSQL is running.
2. Create the database:
   ```bash
   psql -U postgres -c "CREATE DATABASE temporal_db;"
   ```
3. Initialize the schema:
   ```bash
   psql -U postgres -d temporal_db -f schema.sql
   ```

### 2. Environment Configuration
Edit the `.env` file in the root directory with your database credentials:
```env
DB_HOST=localhost
DB_NAME=temporal_db
DB_USER=postgres
DB_PASS=your_password
DB_PORT=5432
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Platform (Run in separate terminals)

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


## Analytics Implementation
- **Time-Series Partitioning**: `market_data` and `portfolio_history` are partitioned by month.
- **Triggers**: `trg_create_wallet` for new users.
- **Stored Functions**: `place_order`, `execute_trade`, `record_portfolio_history`.
- **Views**: `latest_prices`, `portfolio_summary` for simplified analytics.
- **Materialized Views**: `mv_top_assets` for aggregated trading volume.
