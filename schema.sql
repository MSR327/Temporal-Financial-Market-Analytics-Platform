-- ========================= 
-- 0. EXTENSIONS & CLEANUP (FOR RE-RUNNABILITY)
-- ========================= 
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

DROP TABLE IF EXISTS market_data CASCADE;
DROP TABLE IF EXISTS portfolio_history CASCADE;
DROP TABLE IF EXISTS trades CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS portfolio CASCADE;
DROP TABLE IF EXISTS wallets CASCADE;
DROP TABLE IF EXISTS assets CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP VIEW IF EXISTS latest_prices CASCADE;
DROP TABLE IF EXISTS latest_prices_cache CASCADE;
DROP MATERIALIZED VIEW IF EXISTS market_data_daily CASCADE;
DROP VIEW IF EXISTS portfolio_value CASCADE;
DROP VIEW IF EXISTS profit_loss CASCADE;
DROP MATERIALIZED VIEW IF EXISTS mv_top_assets CASCADE;

-- ========================= 
-- 1. USERS 
-- ========================= 
CREATE TABLE users ( 
    user_id SERIAL PRIMARY KEY, 
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL, 
    password_hash TEXT NOT NULL, 
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP 
); 

CREATE INDEX idx_users_email ON users(email); 

-- ========================= 
-- 2. WALLETS 
-- ========================= 
CREATE TABLE wallets ( 
    wallet_id SERIAL PRIMARY KEY, 
    user_id INT UNIQUE REFERENCES users(user_id) ON DELETE CASCADE, 
    balance NUMERIC(15,2) DEFAULT 100000.00 CHECK (balance >= 0), 
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP 
); 

CREATE INDEX idx_wallet_user ON wallets(user_id); 

-- Trigger: Auto-create wallet after user signup
CREATE OR REPLACE FUNCTION fn_create_wallet() 
RETURNS TRIGGER AS $$ 
BEGIN 
    INSERT INTO wallets(user_id) VALUES (NEW.user_id); 
    RETURN NEW; 
END; 
$$ LANGUAGE plpgsql; 

CREATE TRIGGER trg_create_wallet 
AFTER INSERT ON users 
FOR EACH ROW 
EXECUTE FUNCTION fn_create_wallet(); 

-- ========================= 
-- 3. ASSETS 
-- ========================= 
CREATE TABLE assets ( 
    asset_id SERIAL PRIMARY KEY, 
    name TEXT NOT NULL, 
    symbol TEXT UNIQUE NOT NULL, 
    type TEXT CHECK (type IN ('crypto','stock')) NOT NULL 
); 

INSERT INTO assets (name, symbol, type) VALUES 
('Bitcoin', 'BTC', 'crypto'),
('Ethereum', 'ETH', 'crypto'),
('Solana', 'SOL', 'crypto'),
('Cardano', 'ADA', 'crypto'),
('Ripple', 'XRP', 'crypto'),
('Dogecoin', 'DOGE', 'crypto'),
('Polkadot', 'DOT', 'crypto'),
('Chainlink', 'LINK', 'crypto'),
('Polygon', 'MATIC', 'crypto'),
('Avalanche', 'AVAX', 'crypto'),
('Litecoin', 'LTC', 'crypto'),
('Shiba Inu', 'SHIB', 'crypto'),
('Apple Inc.', 'AAPL', 'stock'),
('Tesla Inc.', 'TSLA', 'stock'),
('NVIDIA Corp.', 'NVDA', 'stock'),
('Microsoft Corp.', 'MSFT', 'stock'),
('Amazon.com Inc.', 'AMZN', 'stock'),
('Alphabet Inc. (Google)', 'GOOGL', 'stock'),
('Meta Platforms Inc. (Facebook)', 'META', 'stock'),
('Netflix Inc.', 'NFLX', 'stock'),
('Walt Disney Co.', 'DIS', 'stock'),
('Adobe Inc.', 'ADBE', 'stock'),
('Intel Corp.', 'INTC', 'stock'),
('Advanced Micro Devices Inc. (AMD)', 'AMD', 'stock'),
('Salesforce Inc.', 'CRM', 'stock');

-- ========================= 
-- 4. MARKET DATA & LATEST PRICES CACHE
-- ========================= 
CREATE TABLE market_data ( 
    asset_id INT REFERENCES assets(asset_id) ON DELETE CASCADE, 
    price NUMERIC(15,2) NOT NULL CHECK (price > 0), 
    time TIMESTAMPTZ NOT NULL, 
    source TEXT DEFAULT 'simulated'
); 

SELECT create_hypertable('market_data', 'time'); 

-- Continuous Aggregate for Daily OHLC (Candlesticks)
-- Note: Created WITH NO DATA to avoid transaction errors
CREATE MATERIALIZED VIEW market_data_daily
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 day', time) AS bucket,
  asset_id,
  MIN(price) AS low,
  MAX(price) AS high,
  FIRST(price, time) AS open,
  LAST(price, time) AS close
FROM market_data
GROUP BY bucket, asset_id
WITH NO DATA;

-- Policy to refresh the aggregate daily
SELECT add_continuous_aggregate_policy('market_data_daily',
  start_offset => INTERVAL '1 month',
  end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 day');

CREATE INDEX idx_market_asset_time ON market_data (asset_id, time DESC); 
CREATE INDEX idx_market_time ON market_data(time DESC); 

-- Cache table for ultra-fast latest price lookups
CREATE TABLE latest_prices_cache (
    asset_id INT PRIMARY KEY REFERENCES assets(asset_id) ON DELETE CASCADE,
    price NUMERIC(15,2) NOT NULL,
    time TIMESTAMPTZ NOT NULL
);

-- Trigger to keep cache updated
CREATE OR REPLACE FUNCTION fn_update_latest_price_cache()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO latest_prices_cache (asset_id, price, time)
    VALUES (NEW.asset_id, NEW.price, NEW.time)
    ON CONFLICT (asset_id) DO UPDATE
    SET price = EXCLUDED.price,
        time = EXCLUDED.time
    WHERE latest_prices_cache.time <= EXCLUDED.time;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_latest_price_cache
AFTER INSERT ON market_data
FOR EACH ROW EXECUTE FUNCTION fn_update_latest_price_cache();

-- Optimized View: Latest Prices (now uses cache)
CREATE OR REPLACE VIEW latest_prices AS 
SELECT asset_id, price, time FROM latest_prices_cache;

-- One-time population of the cache
INSERT INTO latest_prices_cache (asset_id, price, time)
SELECT DISTINCT ON (asset_id) asset_id, price, time
FROM market_data
ORDER BY asset_id, time DESC
ON CONFLICT (asset_id) DO NOTHING;

-- ========================= 
-- 5. ORDERS & TRADES 
-- ========================= 
CREATE TABLE orders ( 
    order_id SERIAL, 
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE, 
    asset_id INT REFERENCES assets(asset_id) ON DELETE CASCADE, 
    quantity NUMERIC(15,5) NOT NULL CHECK (quantity > 0), 
    price NUMERIC(15,5) NOT NULL CHECK (price > 0), 
    order_type TEXT CHECK (order_type IN ('buy', 'sell')) NOT NULL, 
    status TEXT CHECK (status IN ('open', 'filled', 'cancelled')) DEFAULT 'open', 
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id, created_at)
); 

SELECT create_hypertable('orders', 'created_at');

CREATE TABLE trades( 
    trade_id SERIAL, 
    order_id INT, -- FK removed for now because orders PK changed
    user_id INT REFERENCES users(user_id), 
    asset_id INT REFERENCES assets(asset_id), 
    trade_type TEXT CHECK (trade_type IN ('buy','sell')), 
    price NUMERIC(15,5) NOT NULL CHECK (price > 0), 
    quantity NUMERIC(15,5) NOT NULL CHECK (quantity > 0), 
    executed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_id, executed_at)
); 

SELECT create_hypertable('trades', 'executed_at');

-- ========================= 
-- 6. PORTFOLIO 
-- ========================= 
CREATE TABLE portfolio ( 
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE, 
    asset_id INT REFERENCES assets(asset_id) ON DELETE CASCADE, 
    quantity NUMERIC(15,5) DEFAULT 0 CHECK (quantity >= 0), 
    avg_price NUMERIC(15,5) DEFAULT 0, 
    PRIMARY KEY (user_id, asset_id) 
); 

-- ========================= 
-- 7. TRIGGERS FOR TRADES
-- ========================= 

-- Trigger: Update wallet after trade
CREATE OR REPLACE FUNCTION fn_update_wallet_after_trade() 
RETURNS TRIGGER AS $$ 
BEGIN 
    IF NEW.trade_type = 'buy' THEN
        UPDATE wallets SET balance = balance - (NEW.price * NEW.quantity) WHERE user_id = NEW.user_id;
    ELSE
        UPDATE wallets SET balance = balance + (NEW.price * NEW.quantity) WHERE user_id = NEW.user_id;
    END IF;
    RETURN NEW; 
END; 
$$ LANGUAGE plpgsql; 

CREATE TRIGGER trg_update_wallet_after_trade 
AFTER INSERT ON trades 
FOR EACH ROW EXECUTE FUNCTION fn_update_wallet_after_trade();

-- Trigger: Update portfolio after trade
CREATE OR REPLACE FUNCTION fn_update_portfolio_after_trade() 
RETURNS TRIGGER AS $$ 
BEGIN 
    IF NEW.trade_type = 'buy' THEN
        INSERT INTO portfolio(user_id, asset_id, quantity, avg_price) 
        VALUES (NEW.user_id, NEW.asset_id, NEW.quantity, NEW.price) 
        ON CONFLICT (user_id, asset_id) 
        DO UPDATE SET 
            avg_price = (portfolio.avg_price * portfolio.quantity + (NEW.price * NEW.quantity)) / (portfolio.quantity + NEW.quantity),
            quantity = portfolio.quantity + NEW.quantity; 
    ELSE
        UPDATE portfolio SET quantity = quantity - NEW.quantity 
        WHERE user_id = NEW.user_id AND asset_id = NEW.asset_id; 
        
        DELETE FROM portfolio WHERE user_id = NEW.user_id AND asset_id = NEW.asset_id AND quantity = 0;
    END IF;
    RETURN NEW; 
END; 
$$ LANGUAGE plpgsql; 

CREATE TRIGGER trg_update_portfolio_after_trade 
AFTER INSERT ON trades 
FOR EACH ROW EXECUTE FUNCTION fn_update_portfolio_after_trade();

-- ========================= 
-- 8. CORE FUNCTIONS
-- ========================= 

CREATE OR REPLACE FUNCTION execute_trade(p_order_id INT) 
RETURNS VOID AS $$ 
DECLARE 
    v_user INT; v_asset INT; v_type TEXT; v_price NUMERIC; v_qty NUMERIC;
    v_total_cost NUMERIC; v_balance NUMERIC; v_holdings NUMERIC;
BEGIN 
    SELECT user_id, asset_id, order_type, price, quantity INTO v_user, v_asset, v_type, v_price, v_qty 
    FROM orders WHERE order_id = p_order_id;
    
    v_total_cost := v_price * v_qty;
    
    -- Verification
    IF v_type = 'buy' THEN
        SELECT balance INTO v_balance FROM wallets WHERE user_id = v_user FOR UPDATE;
        IF v_balance < v_total_cost THEN 
            UPDATE orders SET status = 'cancelled' WHERE order_id = p_order_id;
            RAISE EXCEPTION 'Insufficient balance';
        END IF;
    ELSE
        SELECT quantity INTO v_holdings FROM portfolio WHERE user_id = v_user AND asset_id = v_asset FOR UPDATE;
        IF v_holdings IS NULL OR v_holdings < v_qty THEN
            UPDATE orders SET status = 'cancelled' WHERE order_id = p_order_id;
            RAISE EXCEPTION 'Insufficient assets';
        END IF;
    END IF;

    -- Insert trade (Triggers will handle wallet and portfolio updates)
    INSERT INTO trades(order_id, user_id, asset_id, price, quantity, trade_type) 
    VALUES (p_order_id, v_user, v_asset, v_price, v_qty, v_type); 

    UPDATE orders SET status = 'filled' WHERE order_id = p_order_id; 
END; 
$$ LANGUAGE plpgsql; 

CREATE OR REPLACE FUNCTION place_order(p_user INT, p_asset INT, p_type TEXT, p_qty NUMERIC) 
RETURNS INT AS $$ 
DECLARE v_price NUMERIC; v_order_id INT;
BEGIN 
    SELECT price INTO v_price FROM latest_prices WHERE asset_id = p_asset;
    IF v_price IS NULL THEN RAISE EXCEPTION 'No price data available'; END IF;

    INSERT INTO orders(user_id, asset_id, quantity, price, order_type) 
    VALUES (p_user, p_asset, p_qty, v_price, LOWER(p_type)) 
    RETURNING order_id INTO v_order_id; 

    PERFORM execute_trade(v_order_id);
    RETURN v_order_id;
END; 
$$ LANGUAGE plpgsql; 

-- ========================= 
-- 9. PORTFOLIO HISTORY (PARTITIONED)
-- ========================= 
CREATE TABLE portfolio_history ( 
    time TIMESTAMPTZ NOT NULL, 
    user_id INT REFERENCES users(user_id) ON DELETE CASCADE, 
    total_value NUMERIC 
); 

SELECT create_hypertable('portfolio_history', 'time'); 

CREATE OR REPLACE FUNCTION record_portfolio_history() 
RETURNS VOID AS $$ 
BEGIN 
    INSERT INTO portfolio_history(time, user_id, total_value) 
    SELECT NOW(), u.user_id, COALESCE(w.balance, 0) + COALESCE(SUM(p.quantity * lp.price), 0)
    FROM users u
    LEFT JOIN wallets w ON u.user_id = w.user_id
    LEFT JOIN portfolio p ON u.user_id = p.user_id 
    LEFT JOIN latest_prices lp ON p.asset_id = lp.asset_id 
    GROUP BY u.user_id, w.balance; 
END; 
$$ LANGUAGE plpgsql; 

-- View: Portfolio Summary (Uses LEFT JOIN to show assets even if price data is missing)
CREATE VIEW portfolio_summary AS 
SELECT 
    p.user_id, p.asset_id, a.symbol, p.quantity, p.avg_price, 
    COALESCE(lp.price, 0) as current_price,
    (COALESCE(lp.price, 0) * p.quantity) as current_value, 
    (COALESCE(lp.price, 0) - p.avg_price) * p.quantity as unrealized_pl
FROM portfolio p 
JOIN assets a ON p.asset_id = a.asset_id
LEFT JOIN latest_prices lp ON p.asset_id = lp.asset_id; 

CREATE MATERIALIZED VIEW mv_top_assets AS 
SELECT asset_id, SUM(quantity * price) AS total_traded_value 
FROM trades GROUP BY asset_id ORDER BY total_traded_value DESC LIMIT 5
WITH NO DATA; 

CREATE OR REPLACE FUNCTION deposit_money(p_user_id INT, p_amount NUMERIC) RETURNS VOID AS $$
BEGIN UPDATE wallets SET balance = balance + p_amount WHERE user_id = p_user_id; END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION withdraw_money(p_user_id INT, p_amount NUMERIC) RETURNS VOID AS $$
BEGIN UPDATE wallets SET balance = balance - p_amount WHERE user_id = p_user_id AND balance >= p_amount;
IF NOT FOUND THEN RAISE EXCEPTION 'Insufficient balance'; END IF; END; $$ LANGUAGE plpgsql;
