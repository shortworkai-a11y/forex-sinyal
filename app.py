import subprocess
import sys

# Fungsi untuk memaksa instalasi jika library hilang
def install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import yfinance as yf
except ImportError:
    install('yfinance')
    import yfinance as yf

try:
    import pandas_ta as ta
except ImportError:
    install('pandas-ta')
    import pandas_ta as ta

import streamlit as st
import pandas as pd
from datetime import datetime
import time

# --- LANJUTKAN KODE SOVEREIGN V7.0 DISINI ---
import streamlit as st
import yfinance as yf
import pandas_ta as ta
import pandas as pd
from datetime import datetime
import time
import os
os.system('pip install yfinance pandas-ta')

import yfinance as yf
import pandas_ta as ta

# --- CONFIG DASHBOARD ---
st.set_page_config(page_title="VANMORT v7.0 SOVEREIGN", layout="wide", initial_sidebar_state="collapsed")

# Custom CSS untuk gaya Pro Sovereign
st.markdown("""
    <style>
    .main { background-color: #020305; color: #f0f0f0; }
    div[data-testid="stMetricValue"] { font-size: 72px; font-weight: 900; color: #00ff88 !important; }
    .stTable { background-color: rgba(13, 17, 23, 0.8); border-radius: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR SETTINGS ---
with st.sidebar:
    st.header("⚙️ Terminal Settings")
    symbol = st.selectbox("Market Pair", ["GC=F", "EURUSD=X", "GBPUSD=X", "JPY=X", "BTC-USD"])
    tf = st.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "1d"])
    risk_usd = st.number_input("Risk per Trade ($)", value=20.0)
    offset = st.number_input("Broker Offset", value=0.0)

# --- ENGINE LOGIC ---
def get_data():
    df = yf.download(tickers=symbol, period="2d", interval=tf, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    df['EMA50'] = ta.ema(df['Close'], length=50)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
    df['RSI'] = ta.rsi(df['Close'], length=14)
    return df.dropna()

# --- UI DISPLAY ---
st.title("🏛️ VANMORT SOVEREIGN v7.0")
st.caption(f"INSTITUTIONAL DATA FEED ACTIVE | {symbol} | {tf}")

placeholder = st.empty()

# Persistent state untuk signal (agar tidak hilang saat refresh)
if 'signals' not in st.session_state:
    st.session_state.signals = []

# --- LIVE LOOP ---
while True:
    try:
        df = get_data()
        curr = df.iloc[-1]
        prev2 = df.iloc[-3]
        price = curr['Close'] + offset
        
        # Signal Detection
        status = "NEUTRAL"
        if curr['Low'] > prev2['High'] and curr['Close'] > curr['EMA50']: status = "STRONG BUY"
        elif curr['High'] < prev2['Low'] and curr['Close'] < curr['EMA50']: status = "STRONG SELL"
        
        if status != "NEUTRAL":
            ts = datetime.now().strftime("%H:%M:%S")
            if not st.session_state.signals or st.session_state.signals[0]['Time'] != ts:
                sl_val = curr['ATR'] * 1.5
                tp_val = price + (sl_val * 2) if "BUY" in status else price - (sl_val * 2)
                sl_price = price - sl_val if "BUY" in status else price + sl_val
                lot = risk_usd / (sl_val * 100) if sl_val > 0 else 0.01
                
                new_sig = {
                    "Time": ts, "Signal": status, "Entry": round(price, 4),
                    "TP": round(tp_val, 4), "SL": round(sl_price, 4), "Lot": round(lot, 2)
                }
                st.session_state.signals.insert(0, new_sig)
                st.session_state.signals = st.session_state.signals[:10]

        with placeholder.container():
            col1, col2, col3 = st.columns([2, 1, 1])
            col1.metric("Live Price", f"{price:,.4f}")
            col2.write(f"**RSI:** {curr['RSI']:.2f}")
            col2.write(f"**ATR:** {curr['ATR']:.4f}")
            col3.write(f"**EMA 50:** {curr['EMA50']:.4f}")
            
            st.subheader("Live Execution Log")
            if st.session_state.signals:
                st.table(pd.DataFrame(st.session_state.signals))
            else:
                st.info("Waiting for market setup...")

        time.sleep(5)
        st.rerun() # Mengulang loop untuk live update

    except Exception as e:
        st.error(f"Connection Alert: {e}")
        time.sleep(10)
