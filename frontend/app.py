import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time

# Configuration
BACKEND_URL = "http://localhost:5000/api"

# Session state initialization
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'username' not in st.session_state:
    st.session_state.username = None

def register_user(username, email, password):
    try:
        response = requests.post(f"{BACKEND_URL}/register", json={"username": username, "email": email, "password": password})
        if response.status_code == 201:
            st.success("Registration successful! Please login.")
        else:
            st.error(response.json().get("error", "Registration failed"))
    except Exception as e:
        st.error(f"Connection error: {e}")

def login_user(username, password):
    try:
        response = requests.post(f"{BACKEND_URL}/login", json={"username": username, "password": password})
        if response.status_code == 200:
            data = response.json()
            st.session_state.user_id = data['user_id']
            st.session_state.username = data['username']
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Invalid credentials")
    except Exception as e:
        st.error(f"Connection error: {e}")

def get_wallet_balance():
    response = requests.get(f"{BACKEND_URL}/wallet/{st.session_state.user_id}")
    return response.json()['balance']

def get_portfolio():
    response = requests.get(f"{BACKEND_URL}/portfolio/{st.session_state.user_id}")
    return pd.DataFrame(response.json())

def get_assets():
    response = requests.get(f"{BACKEND_URL}/assets")
    return pd.DataFrame(response.json())

def get_latest_prices():
    response = requests.get(f"{BACKEND_URL}/prices")
    return pd.DataFrame(response.json())

def get_portfolio_history():
    response = requests.get(f"{BACKEND_URL}/analytics/history/{st.session_state.user_id}")
    return pd.DataFrame(response.json())

def place_order(asset_id, order_type, quantity):
    try:
        response = requests.post(f"{BACKEND_URL}/order", json={
            "user_id": st.session_state.user_id,
            "asset_id": asset_id,
            "order_type": order_type,
            "quantity": quantity
        })
        if response.status_code == 200:
            st.success("Trade executed successfully!")
        else:
            st.error(response.json().get("error", "Trade failed"))
    except Exception as e:
        st.error(f"Connection error: {e}")

# Sidebar
st.sidebar.title("Temporal Market Platform")
if st.session_state.user_id:
    st.sidebar.write(f"Logged in as: {st.session_state.username}")
    if st.sidebar.button("Logout"):
        st.session_state.user_id = None
        st.session_state.username = None
        st.rerun()

# Main logic
if not st.session_state.user_id:
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pw")
        if st.button("Login"):
            login_user(username, password)
    with tab2:
        new_username = st.text_input("Username", key="reg_user")
        new_email = st.text_input("Email", key="reg_email")
        new_password = st.text_input("Password", type="password", key="reg_pw")
        if st.button("Register"):
            register_user(new_username, new_email, new_password)
else:
    # Dashboard layout
    st.title("Market Analytics Dashboard")
    
    # Portfolio summary
    balance = get_wallet_balance()
    portfolio_df = get_portfolio()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Wallet Balance", f"₹{balance:,.2f}")
    if not portfolio_df.empty:
        total_pl = portfolio_df['unrealized_pl'].sum()
        total_value = portfolio_df['current_value'].sum()
        col2.metric("Portfolio Value", f"₹{total_value:,.2f}")
        col3.metric("Total P/L", f"₹{total_pl:,.2f}", delta=f"{total_pl:,.2f}")
    else:
        col2.metric("Portfolio Value", "₹0.00")
        col3.metric("Total P/L", "₹0.00")

    # Main Dashboard Area
    tab_dash, tab_trade, tab_history = st.tabs(["Dashboard", "Trade", "History"])

    with tab_dash:
        st.subheader("Market Real-time Prices")
        prices_df = get_latest_prices()
        if not prices_df.empty:
            st.dataframe(prices_df.style.format({"price": "₹{:.2f}"}))
        
        # Portfolio Value Graph
        st.subheader("Portfolio Value Over Time")
        history_df = get_portfolio_history()
        if not history_df.empty:
            fig = px.line(history_df, x='time', y='total_value', title="Total Wealth History")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No history available yet.")

        # Asset Allocation
        if not portfolio_df.empty:
            st.subheader("Asset Allocation")
            fig_pie = px.pie(portfolio_df, values='current_value', names='symbol', title="Allocation by Asset")
            st.plotly_chart(fig_pie, use_container_width=True)

    with tab_trade:
        st.subheader("Execute Trade")
        assets_df = get_assets()
        asset_options = {f"{r['symbol']} ({r['name']})": r['asset_id'] for _, r in assets_df.iterrows()}
        selected_asset_name = st.selectbox("Select Asset", options=list(asset_options.keys()))
        asset_id = asset_options[selected_asset_name]
        
        order_type = st.radio("Order Type", ["buy", "sell"], horizontal=True)
        quantity = st.number_input("Quantity", min_value=0.00001, format="%.5f")
        
        if st.button("Execute Trade"):
            place_order(asset_id, order_type, quantity)
            st.rerun()

    with tab_history:
        st.subheader("Current Portfolio")
        if not portfolio_df.empty:
            st.dataframe(portfolio_df.style.format({
                "quantity": "{:.5f}",
                "avg_price": "₹{:.2f}",
                "current_price": "₹{:.2f}",
                "current_value": "₹{:.2f}",
                "unrealized_pl": "₹{:.2f}"
            }))
        else:
            st.info("No holdings found.")

    # Periodic Rerun
    time.sleep(2)
    st.rerun()
