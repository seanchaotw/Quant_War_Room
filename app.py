import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 系統初始化
# ==========================================
st.set_page_config(page_title="Alpha 戰術雷達 (極簡自選版)", page_icon="🎯", layout="centered")

st.markdown("""
<style>
    .signal-buy { color: #00C853; font-weight: bold; }
    .signal-hold { color: #FFD600; font-weight: bold; }
    .signal-sell { color: #D50000; font-weight: bold; }
    .stock-card { background-color: rgba(255,255,255,0.05); padding: 15px; border-radius: 10px; margin-bottom: 10px; border: 1px solid rgba(255,255,255,0.1); }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 狀態與預設值初始化
# ==========================================
if 'weights' not in st.session_state:
    st.session_state.weights = {"TA": 15, "SCTR": 20, "Roland": 35, "ETF": 15, "Value": 15}

# 預設自選股清單
if 'my_watchlist' not in st.session_state:
    st.session_state.my_watchlist = ["NVDA", "AAPL", "AVGO", "SIDU", "2603.TW"]

# ==========================================
# 核心戰術引擎 (捨棄圖表，純數值運算)
# ==========================================
def analyze_stock(symbol, w):
    try:
        session = requests.Session()
        retry = Retry(connect=3, backoff_factor=1.0) 
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        })
        
        ticker = yf.Ticker(symbol, session=session)
        data = ticker.history(period="2y")
        
        if data.empty: return None, "無歷史資料"
        if data.index.tz is not None: data.index = data.index.tz_localize(None)

        info = ticker.info if ticker.info else {}
        stock_name = info.get('shortName', symbol)
        
        data['MA3'] = ta.sma(data['Close'], length=3)
        data['MA20'] = ta.sma(data['Close'], length=20)
        data['RSI'] = ta.rsi(data['Close'], length=14)
        data['EMA200'] = ta.ema(data['Close'], length=200)
        data['EMA50'] = ta.ema(data['Close'], length=50)
        data['ROC125'] = ta.roc(data['Close'], length=125)
        data['ROC20'] = ta.roc(data['Close'], length=20)
        macd = ta.macd(data['Close'])
        data = pd.concat([data, macd], axis=1).dropna()
        if data.empty: return None, "指標計算失敗"

        last = data.iloc[-1]
        prev = data.iloc[-2]
        curr_price = float(last['Close'])
        prev_close = float(prev['Close'])
        pct_change = ((curr_price - prev_close)/prev_close)*100

        # 1. TA 分數
        ta_score = sum([2.5 for cond in [last['Close'] > last['MA20'], last['RSI'] > 50, last['MACD_12_26_9'] > last['MACDs_12_26_9'], last['Volume'] > data['Volume'].tail(5).mean()] if cond])

        # 2. Roland Index
        data['Below_MA3'] = data['Close'] < data['MA3']
        segments = []
        in_seg, start_idx = False, 0
        for i in range(len(data)):
            if data['Below_MA3'].iloc[i] and not in_seg: in_seg, start_idx = True, i
            elif not data['Below_MA3'].iloc[i] and in_seg: in_seg = False; segments.append((start_idx, i - 1))
        if in_seg: segments.append((start_idx, len(data) - 1))
        
        roland_score, dg, gg = 5, 0, 0.0
        if segments:
            rev_date = data.iloc[segments[-1][0]:segments[-1][1]+1]['Close'].idxmin()
            rev_price = float(data.loc[rev_date, 'Close'])
            dg = (data.index[-1] - rev_date).days
            gg = ((curr_price - rev_price) / rev_price) * 100
            if last['Close'] < last['MA3']: roland_score = 3
            else: roland_score = 9 if dg <= 5 and gg > 0 else (7 if 5 < dg <= 15 and gg > 0 else (2 if gg < 0 else 5))

        # 3. SCTR
        norm = lambda v, min_v, max_v: max(0, min(100, (v - min_v) / (max_v - min_v) * 100))
        lt = norm(((curr_price - last['EMA200']) / last['EMA200']) * 100, -10, 20) * 0.3 + norm(last['ROC125'], -15, 30) * 0.3
        mt = norm(((curr_price - last['EMA50']) / last['EMA50']) * 100, -5, 10) * 0.075 + norm(last['ROC20'], -10, 15) * 0.075
        st_sc = last['RSI'] * 0.10 + norm(last['MACDh_12_26_9'] - prev['MACDh_12_26_9'], -0.5, 0.5) * 0.15
        sctr_score = round((lt + mt + st_sc) / 10, 1)

        # 4. ETF
        try: inst_pct = float(ticker.major_holders.iloc[1, 0]) * 100 if ticker.major_holders is not None else 50.0
        except: inst_pct = 50.0
        etf_score = 9 if inst_pct > 80 else (7 if inst_pct > 50 else (3 if inst_pct < 20 else 5))

        # 5. Value
        tgt = info.get('targetMeanPrice', curr_price)
        peg = info.get('pegRatio') or 0
        upside = ((tgt - curr_price) / curr_price) * 100 if tgt else 0
        tgt_score = 10 if upside > 15 else (7 if upside > 0 else (4 if upside > -10 else 1))
        peg_score = 10 if peg and 0 < peg <= 1.0 else (7 if peg and peg <= 1.5 else (4 if peg and peg <= 2.0 else 1))
        val_score = round((tgt_score * 0.5) + (peg_score * 0.5), 1) if peg and peg > 0 else tgt_score

        final_score = ta_score*(w["TA"]/100) + sctr_score*(w["SCTR"]/100) + roland_score*(w["Roland"]/100) + etf_score*(w["ETF"]/100) + val_score*(w["Value"]/100)

        # 判定訊號
        if final_score >= 8: signal, sig_class = "🚀 強烈買入", "signal-buy"
        elif final_score >= 6: signal, sig_class = "🟢 偏多操作", "signal-buy"
        elif final_score <= 4: signal, sig_class = "💀 弱勢撤退", "signal-sell"
        else: signal, sig_class = "👀 續抱觀望", "signal-hold"

        return {
            "symbol": symbol, "name": stock_name, "price": curr_price, "pct_change": pct_change,
            "ta": ta_score, "roland": roland_score, "sctr": sctr_score, "etf": etf_score, "val": val_score,
            "final": final_score, "signal": signal, "sig_class": sig_class
        }
    except Exception as e:
        return None

# ==========================================
# 側邊欄：自選股管理
# ==========================================
st.sidebar.title("📋 自選股管理")
new_symbol = st.sidebar.text_input("新增股票代號 (例: TSLA)").upper()
if st.sidebar.button("➕ 加入清單") and new_symbol:
    if new_symbol not in st.session_state.my_watchlist:
        st.session_state.my_watchlist.append(new_symbol)
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("**目前清單：**")
for sym in st.session_state.my_watchlist:
    cols = st.sidebar.columns([3, 1])
    cols[0].write(f"• {sym}")
    if cols[1].button("❌", key=f"del_{sym}"):
        st.session_state.my_watchlist.remove(sym)
        st.rerun()

# ==========================================
# 主畫面：雷達掃描
# ==========================================
st.title("🎯 Alpha 戰術雷達 (極簡自選版)")
st.markdown("一鍵掃描自選股，顯示最新評分與戰術訊號。")

if st.button("🚀 啟動自選股掃描 (啟動防封鎖延遲)", use_container_width=True, type="primary"):
    if not st.session_state.my_watchlist:
        st.warning("自選股清單目前為空！請從左側加入。")
    else:
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for idx, sym in enumerate(st.session_state.my_watchlist):
            status_text.text(f"正在掃描 {sym}... (為了繞過防火牆，每檔會停頓 1.5 秒)")
            res = analyze_stock(sym, st.session_state.weights)
            if res:
                results.append(res)
            
            # 強制冷卻，避免 Too Many Requests 大魔王
            time.sleep(1.5)
            progress_bar.progress((idx + 1) / len(st.session_state.my_watchlist))
            
        status_text.empty()
        progress_bar.empty()
        
        # 顯示結果列表
        if results:
            results.sort(key=lambda x: x['final'], reverse=True) # 依分數排序
            st.markdown("### 📊 掃描結果")
            
            for m in results:
                with st.expander(f"{m['symbol']} - {m['name']} | 總分: {m['final']:.1f} | {m['signal']}"):
                    st.markdown(f"**最新收盤價:** ${m['price']:.2f} ({m['pct_change']:+.2f}%)")
                    st.markdown(f"**戰術訊號:** <span class='{m['sig_class']}'>{m['signal']}</span>", unsafe_allow_html=True)
                    st.markdown("---")
                    
                    # 核心五模組分數
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("技術軍師", f"{m['ta']} / 10")
                    c2.metric("Roland", f"{m['roland']} / 10")
                    c3.metric("SCTR", f"{m['sctr']} / 10")
                    c4.metric("ETF籌碼", f"{m['etf']} / 10")
                    c5.metric("公允估值", f"{m['val']} / 10")
        else:
            st.error("所有股票都掃描失敗，可能目前伺服器 IP 已遭到徹底封鎖。")
