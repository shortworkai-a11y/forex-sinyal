from flask import Flask, render_template, jsonify
import yfinance as yf
import pandas as pd

app = Flask(__name__)

watchlist = [
    'BBCA.JK', 'BBRI.JK', 'BMRI.JK', 'BBNI.JK', 'ASII.JK', 'TLKM.JK', 'GOTO.JK', 
    'ANTM.JK', 'BRMS.JK', 'ADRO.JK', 'PTBA.JK', 'AMMN.JK', 'MEDC.JK', 'MDKA.JK', 
    'BRIS.JK', 'MBMA.JK', 'ACES.JK', 'RAJA.JK', 'DOID.JK', 'NCKL.JK', 'TPIA.JK'
]

def get_market_intelligence():
    # Ambil data harga live
    data = yf.download(watchlist, period="20d", interval="1d", group_by='ticker', progress=False)
    
    processed_data = []
    for t in watchlist:
        try:
            df = data[t].dropna()
            ticker_obj = yf.Ticker(t)
            info = ticker_obj.info
            
            # Data Harga & Volume
            c, p_c, h, l, o, v = df['Close'].iloc[-1], df['Close'].iloc[-2], df['High'].iloc[-1], df['Low'].iloc[-1], df['Open'].iloc[-1], df['Volume'].iloc[-1]
            v_avg = df['Volume'].tail(15).mean()
            
            # Indikator Teknikal
            chg = ((c - p_c) / p_c) * 100
            vr = v / (v_avg + 1)
            dist_h = (1 - (c / h)) * 100
            gap = ((o - p_c) / p_c) * 100
            
            # Indikator Fundamental (7 Pillars)
            pe = info.get('trailingPE', 0)
            pbv = info.get('priceToBook', 0)
            roe = info.get('returnOnEquity', 0) * 100
            der = info.get('debtToEquity', 0) / 100
            ocf = info.get('operatingCashflow', 0)
            
            # Scoring Fundamental
            f_score = 0
            if 0 < pe < 12: f_score += 1
            if 0 < pbv < 1.5: f_score += 1
            if roe > 12: f_score += 1
            if der < 1: f_score += 1
            if ocf > 0: f_score += 1

            # Logika Signal (BSJP & BPJS)
            sig, rank = "-", 0
            if chg > 1.8 and dist_h < 0.003 and vr > 1.5:
                sig, rank = "🔥 BSJP", 5
            elif gap > 0.5 and c > o:
                sig, rank = "⚡ BPJS", 4
            elif vr > 2.5:
                sig, rank = "🐋 WHALE", 3

            processed_data.append({
                'ticker': t.replace('.JK',''),
                'last': int(c),
                'chg': round(chg, 2),
                'vr': round(vr, 1),
                'pe': round(pe, 1),
                'pbv': round(pbv, 1),
                'roe': round(roe, 1),
                'f_score': f_score,
                'signal': sig,
                'rank': rank,
                'segment': "SMALL" if c < 300 else "MID" if c < 2000 else "BIG"
            })
        except: continue
        
    return sorted(processed_data, key=lambda x: x['rank'], reverse=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update')
def update():
    return jsonify(get_market_intelligence())

if __name__ == '__main__':
    app.run(debug=True)
