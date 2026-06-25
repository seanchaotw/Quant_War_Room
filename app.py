import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PIL import Image
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 系統初始化與基本設定
# ==========================================
APP_NAME = "Alpha 戰術雷達 (單檔狙擊版)"

try:
    icon_image = Image.open("logo.png")
    st.set_page_config(page_title=APP_NAME, page_icon=icon_image, layout="wide")
except Exception as e:
    st.set_page_config(page_title=APP_NAME, page_icon="🎯", layout="wide")

# 全域 CSS 魔法
st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background-color: rgba(128,128,128,0.05);
        border: 1px solid rgba(128,128,128,0.2);
        padding: 10px;
        border-radius: 10px;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

US_GREEN = "#2E7D32"  
US_RED = "#C62828"    

# ==========================================
# 預設權重設定
# ==========================================
if 'weights' not in st.session_state:
    st.session_state.weights = {"TA": 15, "SCTR": 20, "Roland": 35, "ETF": 15, "Value": 15}

# ==========================================
# 核心戰術引擎
# ==========================================
@st.cache_data(ttl=300) 
def analyze_stock(symbol, w):
    try:
        # === 終極防護盾：重試機制 + 完整瀏覽器偽裝 ===
        session = requests.Session()
        retry = Retry(connect=3, backoff_factor=0.5) 
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive"
        })
        
        ticker = yf.Ticker(symbol, session=session)
        data = ticker.history(period="2y")
        
        if data.empty: return None, "Yahoo Finance 回傳空資料，可能是代號錯誤或遭到阻擋。"
        if data.index.tz is not None: data.index = data.index.tz_localize(None)

        info = ticker.info
        stock_name = info.get('shortName', symbol)
        prev_close = info.get('previousClose', data['Close'].iloc[-2] if len(data)>1 else data['Close'].iloc[-1])
        
        cap = info.get('marketCap', 0)
        if cap > 10000000000: cap_size = "🏢 大型股"
        elif cap > 2000000000: cap_size = "🏬 中型股"
        elif cap > 0: cap_size = "🏪 小型股"
        else: cap_size = "❓ 未知規模"

        # 技術指標計算
        data['MA3'] = ta.sma(data['Close'], length=3)
        data['MA20'] = ta.sma(data['Close'], length=20)
        data['RSI'] = ta.rsi(data['Close'], length=14)
        data['EMA200'] = ta.ema(data['Close'], length=200)
        data['EMA50'] = ta.ema(data['Close'], length=50)
        data['ROC125'] = ta.roc(data['Close'], length=125)
        data['ROC20'] = ta.roc(data['Close'], length=20)
        macd = ta.macd(data['Close'])
        data = pd.concat([data, macd], axis=1).dropna()
        if data.empty: return None, "技術指標計算後資料為空。"

        last = data.iloc[-1]
        prev = data.iloc[-2]
        curr_price = float(last['Close'])

        # 1. TA 分數
        ta_score = sum([2.5 for cond in [last['Close'] > last['MA20'], last['RSI'] > 50, last['MACD_12_26_9'] > last['MACDs_12_26_9'], last['Volume'] > data['Volume'].tail(5).mean()] if cond])

        # 2. Roland Index 分數
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

        # 3. SCTR 分數
        norm = lambda v, min_v, max_v: max(0, min(100, (v - min_v) / (max_v - min_v) * 100))
        lt = norm(((curr_price - last['EMA200']) / last['EMA200']) * 100, -10, 20) * 0.3 + norm(last['ROC125'], -15, 30) * 0.3
        mt = norm(((curr_price - last['EMA50']) / last['EMA50']) * 100, -5, 10) * 0.075 + norm(last['ROC20'], -10, 15) * 0.075
        st_sc = last['RSI'] * 0.10 + norm(last['MACDh_12_26_9'] - prev['MACDh_12_26_9'], -0.5, 0.5) * 0.15
        sctr_score = round((lt + mt + st_sc) / 10, 1)

        # 4. ETF 分數
        try: inst_pct = float(ticker.major_holders.iloc[1, 0]) * 100 if ticker.major_holders is not None else 50.0
        except: inst_pct = 50.0
        
        inst_list = []
        try:
            inst_df = ticker.institutional_holders
            if inst_df is not None and not inst_df.empty and 'Holder' in inst_df.columns:
                for _, r in inst_df.head(3).iterrows():
                    inst_list.append(f"{r['Holder']} ({r.get('pctHeld', 0) * 100:.2f}%)")
        except: pass 

        etf_score = 9 if inst_pct > 80 else (7 if inst_pct > 50 else (3 if inst_pct < 20 else 5))

        # 5. Value 分數
        tgt = info.get('targetMeanPrice', curr_price)
        tgt_high = info.get('targetHighPrice', 0)
        tgt_low = info.get('targetLowPrice', 0)
        peg = info.get('pegRatio') or info.get('trailingPegRatio') or 0
        pe = info.get('trailingPE') or info.get('forwardPE') or 0
        
        upside = ((tgt - curr_price) / curr_price) * 100 if tgt else 0
        tgt_score = 10 if upside > 15 else (7 if upside > 0 else (4 if upside > -10 else 1))
        peg_score = 10 if peg and 0 < peg <= 1.0 else (7 if peg and peg <= 1.5 else (4 if peg and peg <= 2.0 else 1))
        val_score = round((tgt_score * 0.5) + (peg_score * 0.5), 1) if peg and peg > 0 else tgt_score

        final_score = ta_score*(w["TA"]/100) + sctr_score*(w["SCTR"]/100) + roland_score*(w["Roland"]/100) + etf_score*(w["ETF"]/100) + val_score*(w["Value"]/100)

        metrics = {
            "name": stock_name, "price": curr_price, "change": curr_price - prev_close,
            "pct_change": ((curr_price - prev_close)/prev_close)*100,
            "open": last['Open'], "high": last['High'], "low": last['Low'], "volume": last['Volume'],
            "amplitude": ((last['High'] - last['Low'])/last['Low'])*100 if last['Low']>0 else 0,
            "cap_size": cap_size,
            "ma3": last['MA3'], "ma20": last['MA20'], "rsi": last['RSI'], 
            "macd": last['MACD_12_26_9'], "macd_sig": last['MACDs_12_26_9'],
            "ema200": last['EMA200'], "ema50": last['EMA50'],
            "ta": ta_score, "roland": roland_score, "sctr": sctr_score, 
            "etf": etf_score, "val": val_score, "final": final_score,
            "dg": dg, "gg": gg, "inst_pct": inst_pct, "inst_list": inst_list, 
            "upside": upside, "target": tgt, "tgt_high": tgt_high, "tgt_low": tgt_low, 
            "peg": peg, "pe": pe
        }
        return data, metrics
    except Exception as e:
        return None, f"系統錯誤或連線被阻擋: {str(e)}"

# ==========================================
# 側邊欄：設定區
# ==========================================
st.sidebar.title("⚙️ 戰略權重配置")
st.sidebar.markdown("自訂五大核心戰術的評分佔比")
w = st.session_state.weights
w["TA"] = st.sidebar.slider("1. 技術軍師 (TA)", 0, 100, w["TA"])
w["SCTR"] = st.sidebar.slider("2. SCTR 動能排名", 0, 100, w["SCTR"])
w["Roland"] = st.sidebar.slider("3. Roland Index", 0, 100, w["Roland"])
w["ETF"] = st.sidebar.slider("4. ETF 籌碼比例", 0, 100, w["ETF"])
w["Value"] = st.sidebar.slider("5. 綜合公允估值", 0, 100, w["Value"])
st.session_state.weights = w

if sum(w.values()) != 100: 
    st.sidebar.warning("⚠️ 總權重需等於 100%")

st.sidebar.markdown("---")
st.sidebar.info(
    "**指標戰術手冊**\n\n"
    "• **TA**: MA20趨勢、RSI動能、MACD交叉\n"
    "• **Roland**: 專抓跌破MA3後的反轉拐點\n"
    "• **SCTR**: 結合長短天期的動能排名\n"
    "• **ETF**: 大型機構持股比例(安全墊)\n"
    "• **Value**: PEG與外資目標價折溢價空間"
)

# ==========================================
# 主畫面：單檔狙擊介面
# ==========================================
st.title("🎯 Alpha 戰術雷達")
st.markdown("輸入單一股票代碼，進行深度戰術掃描與公允價值評估。")

col1, col2 = st.columns([3, 1])
with col1:
    symbol_input = st.text_input("🔍 輸入美股/台股代號 (例如: NVDA, AAPL, 2330.TW)", placeholder="請輸入代號...").upper()
with col2:
    st.write("")
    st.write("")
    analyze_btn = st.button("🚀 啟動掃描", use_container_width=True, type="primary")

if analyze_btn and symbol_input:
    with st.spinner(f"雷達鎖定 {symbol_input} 掃描中..."):
        data, m = analyze_stock(symbol_input, st.session_state.weights)
    
    if data is None:
        st.error(f"無法取得 {symbol_input} 數據。")
        st.warning(f"⚠️ 錯誤訊息：{m}")
    else:
        st.markdown("---")
        st.markdown(f"## {symbol_input} | {m['name']}")
        
        color = US_GREEN if m['change'] >= 0 else US_RED
        arrow = "▲" if m['change'] >= 0 else "▼"
        
        html_metrics = (
            f'<div style="display:flex; flex-wrap: wrap; gap: 10px; justify-content:space-around; text-align:center; padding: 12px; background-color: rgba(128,128,128,0.05); border-radius: 8px; margin-bottom: 20px; box-shadow: 2px 2px 8px rgba(0,0,0,0.1);">'
            f'<div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">💰 收盤價</div><b style="font-size:18px;">${m["price"]:.2f}</b><br><span style="color:{color}; font-size:12px; font-weight:bold;">{arrow} {abs(m["change"]):.2f} ({m["pct_change"]:+.2f}%)</span></div>'
            f'<div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">⏱️ 開盤</div><b style="font-size:16px;">${m["open"]:.2f}</b></div>'
            f'<div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">📈 最高</div><b style="font-size:16px;">${m["high"]:.2f}</b></div>'
            f'<div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">📉 最低</div><b style="font-size:16px;">${m["low"]:.2f}</b></div>'
            f'<div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">🌊 振幅</div><b style="font-size:16px;">{m["amplitude"]:.2f}%</b></div>'
            f'<div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">🏷️ 市值規模</div><b style="font-size:14px;">{m["cap_size"]}</b></div>'
            f'</div>'
        )
        st.markdown(html_metrics, unsafe_allow_html=True)

        tab_chart, tab_info = st.tabs(["📊 專業走勢圖", "🌟 戰鬥雷達與診斷"])
        
        with tab_chart:
            time_range = st.radio("⏳ 選擇圖表顯示區間", ["1個月", "3個月", "半年", "1年", "全部(2年)"], horizontal=True, index=2)
            
            if time_range == "1個月": plot_days = 21
            elif time_range == "3個月": plot_days = 63
            elif time_range == "半年": plot_days = 126
            elif time_range == "1年": plot_days = 252
            else: plot_days = len(data)
            
            plot_data = data.tail(plot_days)
            x_dates = plot_data.index
            
            all_dates = pd.date_range(start=x_dates.min(), end=x_dates.max(), freq='D')
            missing_dates = all_dates.difference(x_dates).strftime("%Y-%m-%d").tolist()
            
            fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.15, 0.15, 0.2])
            
            vol_colors = [US_RED if row['Close'] < row['Open'] else US_GREEN for index, row in plot_data.iterrows()]
            macd_colors = [US_GREEN if val >= 0 else US_RED for val in plot_data['MACDh_12_26_9']]
            
            fig.add_trace(go.Candlestick(x=x_dates, open=plot_data['Open'], high=plot_data['High'], low=plot_data['Low'], close=plot_data['Close'], name='股價', increasing_line_color=US_GREEN, decreasing_line_color=US_RED), row=1, col=1)
            fig.add_trace(go.Scatter(x=x_dates, y=plot_data['EMA200'], line=dict(color='gray', width=2, dash='dot'), name='EMA200'), row=1, col=1)
            fig.add_trace(go.Scatter(x=x_dates, y=plot_data['MA3'], line=dict(color='#FFCA28', width=2), name='MA3'), row=1, col=1)
            fig.add_trace(go.Bar(x=x_dates, y=plot_data['Volume'], marker_color=vol_colors, name='成交量'), row=2, col=1)
            fig.add_trace(go.Bar(x=x_dates, y=plot_data['MACDh_12_26_9'], marker_color=macd_colors, name='MACD 柱狀圖'), row=3, col=1)
            fig.add_trace(go.Scatter(x=x_dates, y=plot_data['MACD_12_26_9'], line=dict(color='#FF9800', width=1.5), name='MACD 線'), row=3, col=1)
            fig.add_trace(go.Scatter(x=x_dates, y=plot_data['MACDs_12_26_9'], line=dict(color='#2196F3', width=1.5), name='訊號線'), row=3, col=1)
            fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1, row=3, col=1) 
            fig.add_trace(go.Scatter(x=x_dates, y=plot_data['RSI'], line=dict(color='#E040FB', width=1.5), name='RSI(14)'), row=4, col=1)
            fig.add_hline(y=70, line_dash="dash", line_color=US_RED, line_width=1.5, row=4, col=1) 
            fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.3)", line_width=1, row=4, col=1)   
            fig.add_hline(y=30, line_dash="dash", line_color=US_GREEN, line_width=1.5, row=4, col=1) 
            fig.add_hrect(y0=30, y1=70, fillcolor="purple", opacity=0.1, line_width=0, row=4, col=1)  
            
            fig.update_xaxes(rangebreaks=[dict(values=missing_dates)])
            fig.update_layout(height=650, xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, hovermode='x unified', hoverlabel=dict(bgcolor="rgba(0,0,0,0.8)", font_size=12))
            st.plotly_chart(fig, use_container_width=True)

        with tab_info:
            st.metric(label="綜合得分 (滿分10)", value=f"{m['final']:.2f}")
            if m['final'] >= 8: st.success("🚨 【強烈買入】共振訊號發動！")
            elif m['final'] <= 4: st.error("💀 【建議撤退】風險大於利潤。")
            else: st.info("👀 【觀望狀態】等待明確訊號。")
            
            with st.expander(f"1️⃣ 技術軍師: {m['ta']} / 10", expanded=True):
                st.caption(f"• 股價 vs MA20: {'🟢 站上' if m['price'] > m['ma20'] else '🔴 跌破'} (${m['ma20']:.2f})")
                st.caption(f"• RSI (14): {'🟢 強勢' if m['rsi'] > 50 else '🔴 弱勢'} ({m['rsi']:.1f})")
                st.caption(f"• MACD: {'🟢 黃金交叉' if m['macd'] > m['macd_sig'] else '🔴 死亡交叉'}")

            with st.expander(f"2️⃣ Roland Index: {m['roland']} / 10"):
                st.caption(f"• 狀態: {'🔴 處於 MA3 深淵之下' if m['price'] < m['ma3'] else '🟢 已站上 MA3 防線'}")
                st.caption(f"• 距反轉點 (DG): {m['dg']} 天")
                st.caption(f"• 底部漲幅 (GG): {m['gg']:+.2f}%")

            with st.expander(f"3️⃣ SCTR 動能: {m['sctr']} / 10"):
                st.caption(f"• 長線 (EMA200): ${m['ema200']:.2f}")
                st.caption(f"• 中線 (EMA50): ${m['ema50']:.2f}")

            with st.expander(f"4️⃣ ETF 籌碼: {m['etf']} / 10"):
                st.caption(f"• 總機構持股比例: {m['inst_pct']:.1f}%")
                if m['inst_list']:
                    st.markdown("**🏦 前三大持股機構 (最新一季)：**")
                    for inst in m['inst_list']:
                        st.caption(f"  - {inst}")

            with st.expander(f"5️⃣ 公允估值: {m['val']} / 10"):
                st.caption(f"• 華爾街平均目標價: ${m['target']:.2f} ({m['upside']:+.1f}%)")
                if m['tgt_high'] > 0 and m['tgt_low'] > 0:
                    st.caption(f"  - 📈 最高看至: ${m['tgt_high']:.2f} ｜ 📉 最低看至: ${m['tgt_low']:.2f}")
                if m['peg'] > 0:
                    st.caption(f"• PEG 成長比: {m['peg']:.2f}")
                else:
                    st.caption(f"• PEG 成長比: 無資料 (備用估值 P/E 本益比: {m['pe']:.2f})")