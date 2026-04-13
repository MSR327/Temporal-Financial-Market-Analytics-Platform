from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import bcrypt
import database
from datetime import datetime, timezone, timedelta
import os

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.urandom(24)
CORS(app)

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

@app.route("/api/order", methods=["POST"])
def place_order():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    asset_id = data.get("asset_id")
    order_type = data.get("order_type")
    quantity = data.get("quantity")

    if not asset_id or not order_type or not quantity:
        return jsonify({"error": "Missing trade parameters"}), 400

    try:
        # Use execute_query with fetch=True to get the result of the function
        # and ensure the transaction is committed
        result = database.execute_query(
            "SELECT place_order(%s, %s, %s, %s)",
            (user_id, asset_id, order_type, quantity),
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
    prices = database.execute_query(
        "SELECT a.symbol, lp.price, lp.time, a.asset_id FROM latest_prices lp JOIN assets a ON lp.asset_id = a.asset_id",
        fetch=True
    )
    return jsonify([{"symbol": r[0], "price": float(r[1]), "time": r[2], "asset_id": r[3]} for r in prices])

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

@app.route("/api/analytics/history", methods=["GET"])
def get_wealth_history():
    """Fetch total wealth history for the portfolio chart."""
    if 'user_id' not in session:
        return jsonify([])
    
    timeframe = request.args.get('period', '1M')
    days_map = {'1M': 30, '3M': 90, '6M': 180, '1Y': 365}
    days = days_map.get(timeframe, 30)

    # Fetch daily snapshots of portfolio value
    history = database.execute_query(
        """
        SELECT time_bucket('1 day', time) as bucket, AVG(total_value) as total_value
        FROM portfolio_history
        WHERE user_id = %s AND time >= NOW() - INTERVAL '%s day'
        GROUP BY bucket ORDER BY bucket ASC
        """,
        (session['user_id'], days),
        fetch=True
    )
    
    # Fallback: if no portfolio history exists (e.g. new user), 
    # generate a single point with current value
    if not history:
        # Get current wallet balance
        wallet = database.execute_query("SELECT balance FROM wallets WHERE user_id = %s", (session['user_id'],), fetch=True)
        balance = float(wallet[0][0]) if wallet else 0
        
        # Get current holdings value
        holdings = database.execute_query(
            "SELECT SUM(quantity * price) FROM portfolio_summary WHERE user_id = %s", 
            (session['user_id'],), fetch=True
        )
        holdings_val = float(holdings[0][0]) if holdings and holdings[0][0] else 0
        
        return jsonify([{"time": datetime.now().isoformat(), "total_value": balance + holdings_val}])

    return jsonify([{"time": r[0].isoformat(), "total_value": float(r[1])} for r in history])

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

if __name__ == "__main__":
    app.run(debug=True, port=5000)
