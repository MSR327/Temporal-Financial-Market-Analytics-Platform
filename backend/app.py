from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import bcrypt
import database
from datetime import datetime
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

@app.route("/api/assets", methods=["GET"])
def get_assets():
    assets = database.execute_query("SELECT * FROM assets", fetch=True)
    return jsonify([{"asset_id": r[0], "name": r[1], "symbol": r[2], "type": r[3]} for r in assets])

@app.route("/api/prices", methods=["GET"])
def get_latest_prices():
    prices = database.execute_query(
        "SELECT a.symbol, lp.price, lp.time, a.asset_id FROM latest_prices lp JOIN assets a ON lp.asset_id = a.asset_id",
        fetch=True
    )
    return jsonify([{"symbol": r[0], "price": float(r[1]), "time": r[2], "asset_id": r[3]} for r in prices])

@app.route("/api/analytics/history", methods=["GET"])
def get_portfolio_history():
    user_id = session.get('user_id')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    # Get last 50 data points for performance and smooth charting
    history = database.execute_query(
        "SELECT time, total_value FROM portfolio_history WHERE user_id = %s ORDER BY time DESC LIMIT 50",
        (user_id,),
        fetch=True
    )
    # Reverse to show chronological order
    history.reverse()
    return jsonify([{"time": r[0].isoformat(), "total_value": float(r[1])} for r in history])

@app.route("/api/analytics/ohlc/<int:asset_id>", methods=["GET"])
def get_ohlc_history(asset_id):
    """Endpoint to fetch historical OHLC data with timeframe support."""
    timeframe = request.args.get('period', '1M')
    
    # Map timeframe to days
    days_map = {'1M': 30, '3M': 90, '6M': 180, '1Y': 365}
    days = days_map.get(timeframe, 30)
    
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
    
    # Fallback to raw data if aggregates are empty
    if not ohlc:
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
    history = database.execute_query(
        "SELECT time, price FROM market_data WHERE asset_id = %s ORDER BY time DESC LIMIT 20",
        (asset_id,),
        fetch=True
    )
    # Reverse to get chronological order for charting
    history.reverse()
    return jsonify([{"time": r[0].isoformat(), "price": float(r[1])} for r in history])

if __name__ == "__main__":
    app.run(debug=True, port=5000)
