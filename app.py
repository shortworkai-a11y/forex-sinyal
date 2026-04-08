import yfinance as yf
import pandas_ta as ta
import pandas as pd
from flask import Flask, render_template_string, jsonify, request
import threading
import time
from datetime import datetime

app = Flask(__name__)

# --- STATE MANAGEMENT ---
market_state = {
    "symbol": "GC=F",
    "tf": "1m",
    "price": 0.0,
    "display_price": "0.00",
    "offset_gap": 0.0,
    "risk_amount": 20.0,
    "h1_trend": "NEUTRAL",
    "rsi": 0.0,
    "atr": 0.0,
    "volume_status": "NORMAL",
    "news_alert": "MARKET CALM",
    "stats": {"wins": 0, "losses": 0},
    "indicators": {"micro": "GRAY", "mini": "GRAY", "macro": "GRAY"},
    "signals": [],
    "last_voice_msg": ""
}

PAIRS = {
    "GOLD (XAUUSD)": "GC=F", "EUR/USD": "EURUSD=X", 
    "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X", "BITCOIN": "BTC-USD"
}

TIMEFRAMES = { "1M": "1m", "5M": "5m", "15M": "15m", "1H": "1h", "1D": "1d" }

def run_engine():
    global market_state
    while True:
        try:
            symbol, tf = market_state["symbol"], market_state["tf"]
            df = yf.download(tickers=symbol, period="2d", interval=tf, progress=False)
            df_h1 = yf.download(tickers=symbol, period="5d", interval="1h", progress=False)
            
            if not df.empty and not df_h1.empty:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                if isinstance(df_h1.columns, pd.MultiIndex): df_h1.columns = df_h1.columns.get_level_values(0)

                # Indikator Teknikal
                df['EMA50'] = ta.ema(df['Close'], length=50)
                df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)
                df['RSI'] = ta.rsi(df['Close'], length=14)
                df_h1['EMA50_H1'] = ta.ema(df_h1['Close'], length=50)
                
                h1_trend = "BULLISH" if df_h1['Close'].iloc[-1] > df_h1['EMA50_H1'].iloc[-1] else "BEARISH"
                curr = df.dropna().iloc[-1]
                prev2 = df.dropna().iloc[-3]
                raw_price = float(curr['Close'])
                adj_price = raw_price + market_state["offset_gap"]
                prec = 5 if "USD=X" in symbol else 2

                # Update State
                market_state.update({
                    "price": adj_price,
                    "display_price": f"{adj_price:,.{prec}f}",
                    "h1_trend": h1_trend,
                    "rsi": round(float(curr['RSI']), 1),
                    "atr": round(float(curr['ATR']), prec),
                    "volume_status": "HIGH" if curr['Volume'] > (df['Volume'].tail(20).mean() * 1.5) else "LOW",
                    "indicators": {
                        "micro": "GREEN" if raw_price > ta.ema(df['Close'], 9).iloc[-1] else "RED",
                        "mini": "GREEN" if raw_price > ta.ema(df['Close'], 21).iloc[-1] else "RED",
                        "macro": "GREEN" if raw_price > curr['EMA50'] else "RED"
                    }
                })

                # Logika Tracker TP/SL
                for sig in market_state["signals"]:
                    if sig["status"] == "PENDING":
                        if (sig["type"] == "STRONG BUY" and adj_price >= sig["tp_raw"]) or (sig["type"] == "STRONG SELL" and adj_price <= sig["tp_raw"]):
                            sig["status"] = "PROFIT ✅"
                            market_state["stats"]["wins"] += 1
                            market_state["last_voice_msg"] = f"Profit Hit on {symbol}"
                        elif (sig["type"] == "STRONG BUY" and adj_price <= sig["sl_raw"]) or (sig["type"] == "STRONG SELL" and adj_price >= sig["sl_raw"]):
                            sig["status"] = "LOSS ❌"
                            market_state["stats"]["losses"] += 1
                            market_state["last_voice_msg"] = f"Loss Hit on {symbol}"

                # Deteksi Sinyal Baru (FVG + EMA Confluence)
                status = "NEUTRAL"
                if curr['Low'] > prev2['High'] and raw_price > curr['EMA50'] and h1_trend == "BULLISH": status = "STRONG BUY"
                elif curr['High'] < prev2['Low'] and raw_price < curr['EMA50'] and h1_trend == "BEARISH": status = "STRONG SELL"

                if status != "NEUTRAL":
                    ts = datetime.now().strftime("%H:%M:%S")
                    if not market_state["signals"] or (datetime.now() - market_state["signals"][0]["dt"]).total_seconds() > 60:
                        sl_d = float(curr['ATR']) * 1.5
                        tp_r = adj_price + (sl_d*2) if 'BUY' in status else adj_price - (sl_d*2)
                        sl_r = adj_price - sl_d if 'BUY' in status else adj_price + sl_d
                        lot = market_state["risk_amount"] / (sl_d * 100) if sl_d > 0 else 0.01
                        
                        market_state["signals"].insert(0, {
                            "time": ts, "type": status, "entry": f"{adj_price:,.{prec}f}",
                            "sl": f"{sl_r:.{prec}f}", "tp": f"{tp_r:.{prec}f}",
                            "sl_raw": sl_r, "tp_raw": tp_r, "lot": round(lot, 2), 
                            "status": "PENDING", "dt": datetime.now()
                        })
                        market_state["last_voice_msg"] = f"New {status} Signal Detected"
                        market_state["signals"] = market_state["signals"][:10]

        except Exception as e: print(f"Error: {e}")
        time.sleep(4)

# --- PRO UI DESIGN ---
HTML_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8"><title>VANMORT v7.0 SOVEREIGN</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@300;400;700;900&display=swap" rel="stylesheet">
    <style>
        body { background: #020305; color: #f0f0f0; font-family: 'Inter', sans-serif; overflow-x: hidden; }
        .glass-panel { background: rgba(13, 17, 23, 0.8); border: 1px solid rgba(255,255,255,0.05); backdrop-filter: blur(20px); border-radius: 1.5rem; }
        .neon-glow { text-shadow: 0 0 20px rgba(0,255,136,0.4); }
        .dot { height: 6px; width: 6px; border-radius: 50%; }
        .mono { font-family: 'JetBrains Mono', monospace; }
        .btn-pro { background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); border: 1px solid rgba(255,255,255,0.1); }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: #334155; border-radius: 10px; }
    </style>
</head>
<body class="p-4 md:p-8">
    <div class="max-w-7xl mx-auto">
        <header class="flex flex-wrap justify-between items-center mb-10 gap-6 glass-panel p-5">
            <div>
                <h1 class="font-black italic text-2xl tracking-tighter uppercase">VANMORT <span class="text-blue-500">v7.0</span></h1>
                <p id="news-label" class="text-[9px] font-black tracking-[0.3em] text-orange-500 uppercase mt-1">Institutional Data Stream Active</p>
            </div>
            <div class="flex flex-wrap items-center gap-6">
                <div class="flex items-center gap-2 bg-black/40 px-4 py-2 rounded-xl">
                    <select id="pair" onchange="updateCfg()" class="bg-transparent text-xs font-bold outline-none uppercase cursor-pointer">
                        {% for n, s in pairs.items() %}<option value="{{s}}">{{n}}</option>{% endfor %}
                    </select>
                    <select id="tf" onchange="updateCfg()" class="bg-transparent text-xs font-bold border-l border-gray-800 pl-4 outline-none cursor-pointer">
                        {% for n, s in tfs.items() %}<option value="{{s}}">{{n}}</option>{% endfor %}
                    </select>
                </div>
                <div class="hidden md:flex items-center gap-4 text-[10px] font-bold">
                    <div class="flex flex-col">
                        <span class="text-gray-500 uppercase">Risk per trade</span>
                        <input id="risk" type="number" value="20" onchange="updateCfg()" class="bg-transparent text-white border-b border-gray-700 outline-none w-12 text-center">
                    </div>
                    <div class="flex flex-col">
                        <span class="text-gray-500 uppercase">Broker Offset</span>
                        <input id="gap" type="number" step="0.01" value="0.00" onchange="updateCfg()" class="bg-transparent text-white border-b border-gray-700 outline-none w-16 text-center">
                    </div>
                </div>
                <button id="vBtn" onclick="enableAudio()" class="btn-pro px-6 py-2 rounded-full text-[10px] font-black hover:scale-105 transition-all">ENABLE AUDIO AI</button>
            </div>
        </header>

        <div class="grid grid-cols-1 lg:grid-cols-4 gap-8">
            <div class="lg:col-span-3 space-y-8">
                <div class="glass-panel p-10 relative overflow-hidden group">
                    <div class="absolute top-0 right-0 p-6 flex gap-4">
                        <div class="text-right">
                            <p class="text-[8px] text-gray-500 font-black uppercase">Vol/Momentum</p>
                            <p id="vol-label" class="text-xs font-black text-white">NORMAL</p>
                        </div>
                    </div>
                    <div class="text-center">
                        <p class="text-[10px] text-gray-500 font-bold tracking-[0.5em] uppercase mb-6">Real-Time Price Feed</p>
                        <h2 id="price" class="text-9xl font-black neon-glow tracking-tighter text-green-400">0.00</h2>
                        <div class="flex justify-center items-center gap-8 mt-10">
                            <div class="flex items-center gap-2">
                                <span class="text-[9px] text-gray-500 font-black uppercase">H1 Trend</span>
                                <span id="h1-label" class="text-xs font-black text-blue-500">NEUTRAL</span>
                            </div>
                            <div class="h-4 w-[1px] bg-gray-800"></div>
                            <div class="flex gap-4">
                                <div id="d-micro" class="dot bg-gray-800"></div>
                                <div id="d-mini" class="dot bg-gray-800"></div>
                                <div id="d-macro" class="dot bg-gray-800"></div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="glass-panel overflow-hidden">
                    <div class="p-6 border-b border-white/5 flex justify-between items-center">
                        <h3 class="text-[10px] font-black uppercase tracking-widest text-gray-500">Live Execution Log</h3>
                        <div id="status-tag" class="text-[8px] bg-green-500/10 text-green-500 px-3 py-1 rounded-full font-black">SYSTEM STABLE</div>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-xs text-left">
                            <thead class="bg-white/[0.02] text-[9px] uppercase font-black text-gray-500">
                                <tr>
                                    <th class="p-5">Time</th><th class="p-5">Signal Type</th><th class="p-5">Entry</th>
                                    <th class="p-5 text-green-500">Take Profit</th><th class="p-5 text-red-500">Stop Loss</th>
                                    <th class="p-5">Lot Size</th><th class="p-5">Execution Status</th>
                                </tr>
                            </thead>
                            <tbody id="s-table" class="divide-y divide-white/5"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="space-y-8">
                <div class="glass-panel p-8 text-center">
                    <p class="text-[10px] text-gray-500 font-black uppercase mb-4">Performance Win-Rate</p>
                    <div class="relative inline-block">
                        <h3 id="wr-stat" class="text-6xl font-black text-white relative z-10">0%</h3>
                        <div class="absolute -inset-2 bg-blue-600/20 blur-xl rounded-full"></div>
                    </div>
                    <div class="flex justify-between mt-8 text-[10px] font-black uppercase tracking-widest px-4">
                        <div class="flex flex-col"><span id="win-stat" class="text-green-500 text-xl">0</span><span>WINS</span></div>
                        <div class="flex flex-col"><span id="loss-stat" class="text-red-500 text-xl">0</span><span>LOSS</span></div>
                    </div>
                </div>
                <div class="glass-panel p-6 space-y-4 mono">
                    <div class="flex justify-between text-[11px]"><span class="text-gray-500 uppercase font-bold">RSI (14)</span><span id="rsi-val" class="text-blue-400">0</span></div>
                    <div class="flex justify-between text-[11px]"><span class="text-gray-500 uppercase font-bold">ATR Range</span><span id="atr-val" class="text-orange-400">0</span></div>
                    <div class="h-[1px] bg-white/5"></div>
                    <p id="clock" class="text-center text-[10px] text-gray-600 font-bold tracking-widest">00:00:00</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let aEnabled = false; let lastV = "";
        function enableAudio() { aEnabled = true; document.getElementById('vBtn').innerText = "AUDIO SYSTEM ACTIVE"; speak("System initialized."); }
        function speak(t) { if(aEnabled && t !== "") { const s = new SpeechSynthesisUtterance(t); s.rate = 1.1; window.speechSynthesis.speak(s); } }

        async function updateCfg() {
            const s = document.getElementById('pair').value, t = document.getElementById('tf').value;
            const r = document.getElementById('risk').value, g = document.getElementById('gap').value;
            await fetch(`/api/cfg?s=${s}&t=${t}&r=${r}&g=${g}`);
            document.getElementById('s-table').innerHTML = ""; 
        }

        async function poll() {
            try {
                const r = await fetch('/api/data'), d = await r.json();
                document.getElementById('price').innerText = d.display_price;
                document.getElementById('h1-label').innerText = d.h1_trend;
                document.getElementById('vol-label').innerText = d.volume_status;
                document.getElementById('win-stat').innerText = d.stats.wins;
                document.getElementById('loss-stat').innerText = d.stats.losses;
                document.getElementById('rsi-val').innerText = d.rsi;
                document.getElementById('atr-val').innerText = d.atr;
                document.getElementById('clock').innerText = new Date().toLocaleTimeString();

                const total = d.stats.wins + d.stats.losses;
                document.getElementById('wr-stat').innerText = total > 0 ? ((d.stats.wins/total)*100).toFixed(0) + "%" : "0%";

                document.getElementById('d-micro').className = `dot bg-${d.indicators.micro.toLowerCase()}-500 shadow-[0_0_8px] shadow-${d.indicators.micro.toLowerCase()}-500`;
                document.getElementById('d-mini').className = `dot bg-${d.indicators.mini.toLowerCase()}-500 shadow-[0_0_8px] shadow-${d.indicators.mini.toLowerCase()}-500`;
                document.getElementById('d-macro').className = `dot bg-${d.indicators.macro.toLowerCase()}-500 shadow-[0_0_8px] shadow-${d.indicators.macro.toLowerCase()}-500`;

                if(d.last_voice_msg !== lastV) { speak(d.last_voice_msg); lastV = d.last_voice_msg; }

                const table = document.getElementById('s-table');
                let rows = "";
                d.signals.forEach(s => {
                    const stCls = s.status.includes('PROFIT') ? 'text-green-400 font-black' : s.status.includes('LOSS') ? 'text-red-400 font-black' : 'text-gray-500';
                    rows += `<tr class="hover:bg-white/[0.01] transition-all">
                        <td class="p-5 text-gray-500 mono">${s.time}</td>
                        <td class="p-5 font-black uppercase ${s.type.includes('BUY') ? 'text-green-400' : 'text-red-400'}">${s.type}</td>
                        <td class="p-5 mono font-bold">${s.entry}</td>
                        <td class="p-5 mono font-bold text-green-500/80">${s.tp}</td>
                        <td class="p-5 mono font-bold text-red-500/80">${s.sl}</td>
                        <td class="p-5 font-black text-blue-400">${s.lot}</td>
                        <td class="p-5"><span class="${stCls}">${s.status}</span></td>
                    </tr>`;
                });
                table.innerHTML = rows;
            } catch(e) {}
        }
        setInterval(poll, 3000);
    </script>
</body>
</html>
"""

@app.route('/')
def home(): return render_template_string(HTML_UI, pairs=PAIRS, tfs=TIMEFRAMES)

@app.route('/api/data')
def get_data(): return jsonify(market_state)

@app.route('/api/cfg')
def set_cfg():
    market_state.update({
        "symbol": request.args.get('s', "GC=F"), "tf": request.args.get('t', "1m"),
        "risk_amount": float(request.args.get('r', 20.0)), "offset_gap": float(request.args.get('g', 0.0)),
        "signals": [], "stats": {"wins": 0, "losses": 0}, "last_voice_msg": ""
    })
    return jsonify({"status": "synced"})

if __name__ == '__main__':
    threading.Thread(target=run_engine, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)