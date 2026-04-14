from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import bcrypt
import database
from datetime import datetime, timezone, timedelta
import os
from apscheduler.schedulers.background import BackgroundScheduler
import yfinance as yf

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-me-in-production")
CORS(app)
scheduler = BackgroundScheduler()

# --- Routes for HTML Pages ---

@app.route("/")
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template("dashboard.html", username=session['username'], page='home')

@app.route("/markets")
def markets():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template("dashboard.html", username=session['username'], page='markets')

@app.route("/portfolio")
def portfolio_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template("dashboard.html", username=session['username'], page='portfolio')

@app.route("/trade")
def trade_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template("dashboard.html", username=session['username'], page='trade')

@app.route("/transactions")
def transactions_page():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template("dashboard.html", username=session['username'], page='transactions')

# --- Authentication API ---

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not username or not email or not password:
        return jsonify({"error": "Missing fields"}), 400

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    try:
        database.execute_query(
            "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
            (username, email, hashed_pw)
        )
        return jsonify({"message": "User registered successfully"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    username = data.get("username")
    password = data.get("password")

    user = database.execute_query(
        "SELECT user_id, username, password_hash FROM users WHERE username = %s",
        (username,),
        fetch=True
    )

    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    user_id, uname, hashed_pw = user[0]
    if bcrypt.checkpw(password.encode("utf-8"), hashed_pw.encode("utf-8")):
        session['user_id'] = user_id
        session['username'] = uname
        return jsonify({"user_id": user_id, "username": uname}), 200
    else:
        return jsonify({"error": "Invalid username or password"}), 401

@app.route("/api/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- Data API ---

@app.route("/api/wallet", methods=["GET"])
def get_wallet():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    wallet = database.execute_query(
        "SELECT balance FROM wallets WHERE user_id = %s",
        (user_id,),
        fetch=True
    )
    return jsonify({"balance": float(wallet[0][0])})

@app.route("/api/wallet/deposit", methods=["POST"])
def deposit_wallet():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    amount = data.get("amount")
    if amount is None:
        return jsonify({"error": "Amount is required"}), 400

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid amount"}), 400

    try:
        database.execute_query(
            "SELECT deposit_money(%s, %s)",
            (user_id, amount),
            fetch=True
        )
        wallet = database.execute_query(
            "SELECT balance FROM wallets WHERE user_id = %s",
            (user_id,),
            fetch=True
        )
        return jsonify({
            "balance": float(wallet[0][0]),
            "message": "Deposit successful"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e).split('\n')[0]}), 400

@app.route("/api/wallet/withdraw", methods=["POST"])
def withdraw_wallet():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    amount = data.get("amount")
    if amount is None:
        return jsonify({"error": "Amount is required"}), 400

    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid amount"}), 400

    try:
        database.execute_query(
            "SELECT withdraw_money(%s, %s)",
            (user_id, amount),
            fetch=True
        )
        wallet = database.execute_query(
            "SELECT balance FROM wallets WHERE user_id = %s",
            (user_id,),
            fetch=True
        )
        return jsonify({
            "balance": float(wallet[0][0]),
            "message": "Withdrawal successful"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e).split('\n')[0]}), 400

@app.route("/api/portfolio", methods=["GET"])
def get_portfolio():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    portfolio = database.execute_query(
        "SELECT * FROM portfolio_summary WHERE user_id = %s",
        (user_id,),
        fetch=True
    )
    return jsonify([
        {
            "asset_id": row[1],
            "symbol": row[2],
            "quantity": float(row[3]),
            "avg_price": float(row[4]),
            "current_price": float(row[5]),
            "current_value": float(row[6]),
            "unrealized_pl": float(row[7])
        } for row in portfolio
    ])

@app.route("/api/wallet/history", methods=["GET"])
def get_wallet_history():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    history = database.execute_query(
        """
        SELECT action, old_value, new_value, timestamp, context
        FROM audit_logs
        WHERE user_id = %s
        ORDER BY timestamp DESC
        LIMIT 50
        """,
        (user_id,),
        fetch=True
    )
    return jsonify([
        {
            "action": row[0],
            "old_value": float(row[1]) if row[1] else 0,
            "new_value": float(row[2]) if row[2] else 0,
            "change": float(row[2]) - float(row[1]) if row[1] and row[2] else 0,
            "timestamp": row[3].isoformat(),
            "context": row[4]
        } for row in history
    ])

@app.route("/api/order", methods=["POST"])
def place_order():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    asset_id = data.get("asset_id")
    order_type = data.get("order_type")
    quantity = data.get("quantity")
    order_kind = (data.get("order_kind") or "market").lower()
    target_price = data.get("target_price")
    expires_at = data.get("expires_at")

    if not asset_id or not order_type or not quantity:
        return jsonify({"error": "Missing trade parameters"}), 400

    try:
        if order_kind in ("limit", "stop_loss"):
            if target_price is None:
                return jsonify({"error": "target_price is required for limit/stop_loss orders"}), 400
            target_price = float(target_price)
        else:
            target_price = None

        if expires_at:
            try:
                # Accept ISO style timestamps from UI.
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": "Invalid expires_at format"}), 400
        else:
            expires_at = None

        # Use execute_query with fetch=True to get the result of the function
        # and ensure the transaction is committed
        result = database.execute_query(
            "SELECT place_order(%s, %s, %s, %s, %s, %s, %s)",
            (user_id, asset_id, order_type, quantity, order_kind, target_price, expires_at),
            fetch=True
        )
        order_id = result[0][0]
        return jsonify({
            "status": "success",
            "message": f"Order #{order_id} executed successfully",
            "order_id": order_id
        }), 200
    except Exception as e:
        error_msg = str(e).split('\n')[0] # Get the first line of the error
        return jsonify({"status": "error", "error": error_msg}), 400

@app.route("/api/portfolio/stats", methods=["GET"])
def get_portfolio_stats():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    
    stats = database.execute_query(
        """
        SELECT 
            COALESCE(SUM(avg_price * quantity), 0) as total_invested,
            COALESCE(SUM(current_value), 0) as current_value,
            COALESCE(SUM(unrealized_pl), 0) as total_pl
        FROM portfolio_summary 
        WHERE user_id = %s
        """,
        (user_id,),
        fetch=True
    )
    
    wallet = database.execute_query(
        "SELECT balance FROM wallets WHERE user_id = %s",
        (user_id,),
        fetch=True
    )
    balance = float(wallet[0][0]) if wallet else 0
    
    return jsonify({
        "invested": float(stats[0][0]),
        "current_value": float(stats[0][1]),
        "total_pl": float(stats[0][2]),
        "wallet_balance": balance,
        "total_wealth": float(stats[0][1]) + balance
    })

@app.route("/api/transactions", methods=["GET"])
def get_transactions():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    
    transactions = database.execute_query(
        """
        SELECT t.trade_id, a.symbol, t.trade_type, t.quantity, t.price, (t.quantity * t.price) as total, t.executed_at 
        FROM trades t
        JOIN assets a ON t.asset_id = a.asset_id
        WHERE t.user_id = %s
        ORDER BY t.executed_at DESC
        """,
        (user_id,),
        fetch=True
    )
    
    return jsonify([
        {
            "id": row[0],
            "symbol": row[1],
            "type": row[2],
            "quantity": float(row[3]),
            "price": float(row[4]),
            "total": float(row[5]),
            "time": row[6].isoformat()
        } for row in transactions
    ])

@app.route("/api/prices", methods=["GET"])
def get_latest_prices():
    try:
        database.execute_query("SELECT expire_stale_orders()", fetch=True)
    except Exception:
        pass

    prices = database.execute_query(
        "SELECT a.symbol, a.name, lp.price, lp.time, a.asset_id FROM latest_prices lp JOIN assets a ON lp.asset_id = a.asset_id",
        fetch=True
    )
    for r in prices:
        try:
            database.execute_query("SELECT process_limit_orders(%s)", (r[4],), fetch=True)
        except Exception:
            # Keep price API resilient even if limit processing fails for one asset.
            continue
    return jsonify([{"symbol": r[0], "name": r[1], "price": float(r[2]), "time": r[3], "asset_id": r[4]} for r in prices])

@app.route("/api/analytics/ohlc/<int:asset_id>", methods=["GET"])
def get_ohlc_history(asset_id):
    """Endpoint to fetch historical OHLC data with timeframe support."""
    timeframe = request.args.get('period', '1M')
    
    # Map timeframe to days
    days_map = {'1M': 30, '3M': 90, '6M': 180, '1Y': 365}
    days = days_map.get(timeframe, 30)
    
    # Use continuous aggregates if available, otherwise fallback to raw
    ohlc = database.execute_query(
        """
        SELECT bucket, open, high, low, close 
        FROM market_data_daily 
        WHERE asset_id = %s AND bucket >= NOW() - INTERVAL '%s day'
        ORDER BY bucket ASC
        """,
        (asset_id, days),
        fetch=True
    )
    
    if not ohlc:
        # Manual bucketing if the continuous aggregate hasn't refreshed yet
        ohlc = database.execute_query(
            """
            SELECT time_bucket('1 day', time) AS bucket, 
                   FIRST(price, time) as open, MAX(price) as high, 
                   MIN(price) as low, LAST(price, time) as close 
            FROM market_data 
            WHERE asset_id = %s AND time >= NOW() - INTERVAL '%s day'
            GROUP BY bucket ORDER BY bucket ASC
            """,
            (asset_id, days),
            fetch=True
        )
    
    return jsonify([
        {
            "time": r[0].isoformat(),
            "open": float(r[1]),
            "high": float(r[2]),
            "low": float(r[3]),
            "close": float(r[4])
        } for r in ohlc
    ])

@app.route("/api/analytics/price_history/<int:asset_id>", methods=["GET"])
def get_price_history(asset_id):
    """Fetch recent price points for the 1D chart (Last 24 hours or last 50 ticks)."""
    # First, try to get only data from the last 24 hours for a true '1D' view
    history = database.execute_query(
        """
        SELECT time, price FROM market_data 
        WHERE asset_id = %s AND time >= NOW() - INTERVAL '24 hours'
        ORDER BY time ASC
        """,
        (asset_id,),
        fetch=True
    )
    
    # If no data in last 24h (e.g. market closed or script wasn't running), 
    # fallback to last 50 most recent points to show something
    if not history:
        history = database.execute_query(
            """
            SELECT time, price FROM (
                SELECT time, price FROM market_data 
                WHERE asset_id = %s 
                ORDER BY time DESC LIMIT 50
            ) sub ORDER BY time ASC
            """,
            (asset_id,),
            fetch=True
        )
    
    return jsonify([{"time": r[0].isoformat(), "price": float(r[1])} for r in history])

@app.route("/api/analytics/recent_trades/<int:asset_id>", methods=["GET"])
def get_recent_market_trades(asset_id):
    """Recent executed trades for the selected asset."""
    rows = database.execute_query(
        """
        SELECT executed_at, price, quantity, trade_type
        FROM trades
        WHERE asset_id = %s
        ORDER BY executed_at DESC
        LIMIT 30
        """,
        (asset_id,),
        fetch=True
    )
    return jsonify([
        {
            "time": r[0].isoformat(),
            "price": float(r[1]),
            "quantity": float(r[2]),
            "side": r[3]
        } for r in rows
    ])

@app.route("/api/analytics/orderbook/<int:asset_id>", methods=["GET"])
def get_market_orderbook(asset_id):
    """Price-level depth derived from recent executed trades."""
    bids = database.execute_query(
        """
        SELECT ROUND(price::numeric, 2) AS price_level, SUM(quantity) AS total_qty
        FROM trades
        WHERE asset_id = %s
          AND trade_type = 'buy'
          AND executed_at >= NOW() - INTERVAL '24 hours'
        GROUP BY 1
        ORDER BY price_level DESC
        LIMIT 10
        """,
        (asset_id,),
        fetch=True
    )
    asks = database.execute_query(
        """
        SELECT ROUND(price::numeric, 2) AS price_level, SUM(quantity) AS total_qty
        FROM trades
        WHERE asset_id = %s
          AND trade_type = 'sell'
          AND executed_at >= NOW() - INTERVAL '24 hours'
        GROUP BY 1
        ORDER BY price_level ASC
        LIMIT 10
        """,
        (asset_id,),
        fetch=True
    )

    return jsonify({
        "bids": [{"price": float(r[0]), "quantity": float(r[1])} for r in bids],
        "asks": [{"price": float(r[0]), "quantity": float(r[1])} for r in asks]
    })

@app.route("/api/analytics/yf_candles/<int:asset_id>", methods=["GET"])
def get_yfinance_candles(asset_id):
    supported_intervals = ["1m", "2m", "5m", "15m", "30m", "60m", "90m", "1d"]
    interval = (request.args.get("interval") or "1d").lower()
    period = (request.args.get("range") or "1mo").lower()

    if interval not in supported_intervals:
        return jsonify({"error": "Unsupported interval"}), 400

    asset = database.execute_query(
        "SELECT symbol, type FROM assets WHERE asset_id = %s",
        (asset_id,),
        fetch=True
    )
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    symbol, asset_type = asset[0]
    ticker_symbol = f"{symbol}-USD" if asset_type == "crypto" else symbol

    # Enforce yfinance interval constraints.
    intraday_intervals = {"1m", "2m", "5m", "15m", "30m", "60m", "90m"}
    warning = None
    effective_period = period

    if interval == "1m":
        effective_period = "7d"
        if period != "7d":
            warning = "1m data is only available for the last 7 days; range adjusted to 7d."
    elif interval in intraday_intervals:
        allowed = {"1d", "5d", "7d", "1mo", "2mo"}
        if period not in allowed:
            effective_period = "2mo"
            warning = "Intraday intervals (<1d) are available for about 60 days; range adjusted to 2mo."

    try:
        hist = yf.Ticker(ticker_symbol).history(period=effective_period, interval=interval, auto_adjust=False)
    except Exception as e:
        return jsonify({"error": f"yfinance fetch failed: {e}"}), 500

    if hist.empty:
        return jsonify({
            "meta": {
                "interval": interval,
                "requested_range": period,
                "effective_range": effective_period,
                "warning": warning
            },
            "candles": []
        })

    candles = []
    for idx, row in hist.iterrows():
        dt = idx.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        adj_close = row.get("Adj Close", row.get("Close", 0))
        candles.append({
            "time": dt.isoformat(),
            "open": float(row.get("Open", 0) or 0),
            "high": float(row.get("High", 0) or 0),
            "low": float(row.get("Low", 0) or 0),
            "close": float(row.get("Close", 0) or 0),
            "adj_close": float(adj_close or 0),
            "volume": float(row.get("Volume", 0) or 0)
        })

    return jsonify({
        "meta": {
            "interval": interval,
            "requested_range": period,
            "effective_range": effective_period,
            "warning": warning,
            "supported_intervals": supported_intervals
        },
        "candles": candles
    })

def process_pending_limit_orders():
    try:
        assets = database.execute_query("SELECT asset_id FROM assets", fetch=True)
        for (asset_id,) in assets:
            database.execute_query("SELECT process_limit_orders(%s)", (asset_id,), fetch=True)
    except Exception as e:
        print(f"[scheduler] limit order processing failed: {e}")

def expire_old_orders():
    try:
        result = database.execute_query("SELECT expire_stale_orders()", fetch=True)
        count = result[0][0] if result else 0
        if count:
            print(f"[scheduler] expired {count} stale orders")
    except Exception as e:
        print(f"[scheduler] order expiry failed: {e}")

def start_scheduler():
    if scheduler.running:
        return
    scheduler.add_job(process_pending_limit_orders, "interval", seconds=30, id="process_limits", replace_existing=True)
    scheduler.add_job(expire_old_orders,           "interval", minutes=5,  id="expire_orders",   replace_existing=True)
    scheduler.start()
    print("[scheduler] started")

if __name__ == "__main__":
    # Avoid duplicate schedulers with Flask reloader.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        if os.getenv("AUTO_INIT_DB", "false").lower() == "true":
            database.init_db()
            print("[startup] schema applied")
        start_scheduler()
    app.run(debug=True, port=5000)