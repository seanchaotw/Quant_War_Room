import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from PIL import Image
import os
import time
import base64
import streamlit.components.v1 as components

# ==========================================
# 系統初始化與基本設定
# ==========================================
APP_NAME = "Alpha 戰術雷達"

try:
    icon_image = Image.open("logo.png")
    st.set_page_config(page_title=APP_NAME, page_icon=icon_image)
except Exception as e:
    st.set_page_config(page_title=APP_NAME, page_icon="🎯")

# 【iOS PWA 終極駭客注入】
try:
    with open("logo.png", "rb") as f:
        b64_img = base64.b64encode(f.read()).decode("utf-8")
    
    components.html(f"""
        <script>
            const doc = window.parent.document;
            let metaTitle = doc.querySelector('meta[name="apple-mobile-web-app-title"]');
            if (!metaTitle) {{
                metaTitle = doc.createElement('meta');
                metaTitle.name = 'apple-mobile-web-app-title';
                doc.head.appendChild(metaTitle);
            }}
            metaTitle.content = "{APP_NAME}";
            
            let linkIcon = doc.querySelector('link[rel="apple-touch-icon"]');
            if (!linkIcon) {{
                linkIcon = doc.createElement('link');
                linkIcon.rel = 'apple-touch-icon';
                doc.head.appendChild(linkIcon);
            }}
            linkIcon.href = "data:image/png;base64,{b64_img}";
        </script>
    """, height=0, width=0)
except Exception as e:
    pass

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
    
    @keyframes flipInY {
        0% { transform: perspective(400px) rotateY(90deg); opacity: 0; }
        40% { transform: perspective(400px) rotateY(-10deg); }
        70% { transform: perspective(400px) rotateY(10deg); }
        100% { transform: perspective(400px) rotateY(0deg); opacity: 1; }
    }
    .flip-card {
        animation: flipInY 0.7s ease-out both; 
    }
</style>
""", unsafe_allow_html=True)

US_GREEN = "#2E7D32"  
US_RED = "#C62828"    

# ==========================================
# 預設權重鎖定
# ==========================================
if 'weights' not in st.session_state:
    st.session_state.weights = {"TA": 15, "SCTR": 20, "Roland": 35, "ETF": 15, "Value": 15}

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = pd.DataFrame([
        {"代號": "NVDA", "持倉成本": 80.0, "股數": 10},
        {"代號": "PL", "持倉成本": 4.5, "股數": 100},
        {"代號": "AAPL", "持倉成本": 170.0, "股數": 5}
    ])

if 'watchlists' not in st.session_state:
    st.session_state.watchlists = {
        "🚀 科技核心": ["NVDA", "AAPL", "MSFT", "META", "GOOGL"],
        "🛰️ 衛星持股": ["PL", "TSLA", "ASTS", "SOUN", "RKLB"],
        "🛡️ 防禦配置": ["JNJ", "PG", "WMT", "KO"]
    }

# ==========================================
# 核心戰術引擎
# ==========================================
@st.cache_data(ttl=300) 
def analyze_stock(symbol, w):
    try:
        ticker = yf.Ticker(symbol)
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

        ta_score = sum([2.5 for cond in [last['Close'] > last['MA20'], last['RSI'] > 50, last['MACD_12_26_9'] > last['MACDs_12_26_9'], last['Volume'] > data['Volume'].tail(5).mean()] if cond])

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

        norm = lambda v, min_v, max_v: max(0, min(100, (v - min_v) / (max_v - min_v) * 100))
        lt = norm(((curr_price - last['EMA200']) / last['EMA200']) * 100, -10, 20) * 0.3 + norm(last['ROC125'], -15, 30) * 0.3
        mt = norm(((curr_price - last['EMA50']) / last['EMA50']) * 100, -5, 10) * 0.075 + norm(last['ROC20'], -10, 15) * 0.075
        st_sc = last['RSI'] * 0.10 + norm(last['MACDh_12_26_9'] - prev['MACDh_12_26_9'], -0.5, 0.5) * 0.15
        sctr_score = round((lt + mt + st_sc) / 10, 1)

        try: inst_pct = float(ticker.major_holders.iloc[1, 0]) * 100 if ticker.major_holders is not None else 50.0
        except: inst_pct = 50.0
        
        inst_list = []
        try:
            inst_df = ticker.institutional_holders
            if inst_df is not None and not inst_df.empty and 'Holder' in inst_df.columns:
                for _, r in inst_df.head(3).iterrows():
                    h_name = r['Holder']
                    h_pct = r.get('pctHeld', 0) * 100
                    inst_list.append(f"{h_name} ({h_pct:.2f}%)")
        except Exception as e:
            pass 

        etf_score = 9 if inst_pct > 80 else (7 if inst_pct > 50 else (3 if inst_pct < 20 else 5))

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
            "symbol": symbol.upper(),
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
        return None, f"系統底層錯誤或連線被阻擋: {str(e)}"

# ==========================================
# 側邊欄
# ==========================================
page = st.sidebar.selectbox("📂 指揮中心切換", ["📈 戰情儀表板", "💼 實戰持倉管理", "📖 戰術手冊", "⚙️ 權重設定"])
st.sidebar.markdown("---")

if page == "📈 戰情儀表板":
    st.sidebar.header("📋 追蹤清單管理")
    lists = list(st.session_state.watchlists.keys())
    selected_list = st.sidebar.selectbox("當前顯示清單", lists)
    
    with st.sidebar.expander("🛠️ 編輯清單"):
        new_list_name = st.text_input("1. 建立新清單")
        if st.button("➕ 新增清單") and new_list_name:
            if new_list_name not in st.session_state.watchlists:
                st.session_state.watchlists[new_list_name] = []
                st.rerun()
        new_symbol = st.text_input(f"2. 加入代號至「{selected_list}」").upper()
        if st.button("➕ 加入個股") and new_symbol:
            if new_symbol not in st.session_state.watchlists[selected_list]:
                st.session_state.watchlists[selected_list].append(new_symbol)
                st.rerun()

    current_symbols = st.session_state.watchlists[selected_list]
    if not current_symbols:
        st.sidebar.warning("此清單目前為空，請加入股票。")
        symbol = ""
    else:
        symbol = st.sidebar.selectbox("選擇要掃描的個股", current_symbols)

    manual = st.sidebar.text_input("或直接手動輸入單檔代號").upper()
    if manual: symbol = manual

# ==========================================
# 頁面 1: 戰情儀表板
# ==========================================
if page == "📈 戰情儀表板":
    
    if current_symbols and not manual:
        st.markdown(f"### 🏆 「{selected_list}」Top 5 強勢狙擊榜")
        top_list = []
        
        with st.spinner("掃描清單動能中 (啟動防封鎖降速掃描)..."):
            for sym in current_symbols:
                _, m = analyze_stock(sym, st.session_state.weights)
                if isinstance(m, dict): 
                    top_list.append(m)
                time.sleep(0.8) 
        
        top_list.sort(key=lambda x: x['final'], reverse=True)
        top_k = top_list[:5]
        
        if top_k:
            grid_html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; margin-bottom: 15px;">'
            medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
            
            for idx, t_m in enumerate(top_k):
                bg_color = US_GREEN if t_m['pct_change'] >= 0 else US_RED
                sign = "+" if t_m['pct_change'] >= 0 else ""
                medal = medals[idx] if idx < 5 else "🏅"
                fire_icon = "🔥" if t_m['final'] >= 8 else ""
                
                if t_m['final'] >= 8: action_text = "🚀 強烈買入"
                elif t_m['final'] >= 6: action_text = "🟢 偏多操作"
                elif t_m['final'] <= 4: action_text = "💀 弱勢撤退"
                else: action_text = "👀 續抱觀望"
                
                delay = idx * 0.15
                box_html = f'<div class="flip-card" style="animation-delay: {delay}s; background-color: {bg_color}; border-radius: 10px; padding: 10px; color: white; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid rgba(255,255,255,0.1);"><div style="font-size: 13px; font-weight: 600; opacity: 0.9;">{medal} {t_m["symbol"]}</div><div style="font-size: 22px; font-weight: 900; margin: 4px 0;">{t_m["final"]:.1f} {fire_icon}</div><div style="font-size: 11px; font-weight: bold; background: rgba(0,0,0,0.25); padding: 3px; border-radius: 4px; margin-bottom: 6px;">{action_text}</div><div style="font-size: 13px; font-weight: 600;">{sign}{t_m["pct_change"]:.2f}%</div></div>'
                
                grid_html += box_html
            
            grid_html += '</div>'
            st.markdown(grid_html, unsafe_allow_html=True)
            
            st.caption("💡 **戰術總分指南**：`8分以上` 🚀強烈買入 ｜ `6~8分` 🟢偏多操作 ｜ `4~6分` 👀續抱觀望 ｜ `4分以下` 💀弱勢撤退")
            
        st.markdown("---")

    if symbol:
        with st.spinner(f"雷達鎖定 {symbol} 中..."):
            data, m = analyze_stock(symbol, st.session_state.weights)
        
        if data is None:
            st.error(f"無法取得 {symbol} 數據。")
            st.warning(f"⚠️ 除錯雷達攔截原因：{m}")
        else:
            st.markdown(f"## 🎯 {symbol} | {m['name']}")
            
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
                time_range = st.radio("⏳ 選擇圖表顯示區間 (動態 Y 軸彈性貼齊)", ["1個月", "3個月", "半年", "1年", "全部(2年)"], horizontal=True)
                
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
                
                st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})

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
                    st.caption("*(💡 備註：依 SEC 法規，華爾街機構籌碼 (13F) 僅有「季報」，無法取得即時週變動。)*")

                with st.expander(f"5️⃣ 公允估值: {m['val']} / 10"):
                    st.caption(f"• 華爾街平均目標價: ${m['target']:.2f} ({m['upside']:+.1f}%)")
                    if m['tgt_high'] > 0 and m['tgt_low'] > 0:
                        st.caption(f"  - 📈 最高看至: ${m['tgt_high']:.2f} ｜ 📉 最低看至: ${m['tgt_low']:.2f}")
                    
                    if m['peg'] > 0:
                        st.caption(f"• PEG 成長比: {m['peg']:.2f}")
                    else:
                        st.caption(f"• PEG 成長比: 無資料 (備用估值 P/E 本益比: {m['pe']:.2f})")

# ==========================================
# 頁面 2: 實戰持倉管理 
# ==========================================
elif page == "💼 實戰持倉管理":
    st.title("💼 實戰持倉管理")
    
    with st.expander("📝 編輯持倉部位 (點擊展開/收合)", expanded=True):
        st.caption("💡 **操作提示**：在手機上輸入完畢後，請先**點擊表格外的空白處**（或按下確認/Enter）讓系統儲存您的輸入，然後再點擊下方按鈕，即可避免需連按兩次的情況。")
        edited_df = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True, key="portfolio_editor")
        st.session_state.portfolio = edited_df
        run_check = st.button("🚀 啟動部位健檢", type="primary", use_container_width=True)

    if run_check:
        results, total_profit, total_cost = [], 0, 0
        my_bar = st.progress(0, text="戰鬥數據結算中...")
        
        for idx, row in edited_df.iterrows():
            
            # 【防呆裝甲】：自動跳過空行、未填寫或無效代號的列
            val = row.get('代號')
            if pd.isna(val) or not val or str(val).strip() == "" or str(val).lower() == "none":
                continue
                
            try:
                sym = str(row['代號']).upper().strip()
                cost = float(row.get('持倉成本', 0))
                shares = float(row.get('股數', 0))
            except (ValueError, TypeError):
                continue # 若成本或股數欄位非數字，跳過保護系統

            _, m = analyze_stock(sym, st.session_state.weights)
            if isinstance(m, dict):
                current_val, cost_val = m['price'] * shares, cost * shares
                pnl = current_val - cost_val
                pnl_pct = (pnl / cost_val) * 100 if cost_val > 0 else 0
                total_cost += cost_val; total_profit += pnl
                action = "🟢 持有加碼" if m['final'] >= 7.5 else ("🔴 弱勢撤退" if m['final'] <= 4 else "🟡 續抱觀望")
                
                results.append({
                    "股票代號": sym, 
                    "當前總值": current_val, 
                    "損益數值": pnl_pct,
                    "未實現損益顯示": f"{pnl_pct:+.2f}%", 
                    "戰術得分": round(m['final'], 1), 
                    "系統建議": action
                })
            time.sleep(0.8)
            my_bar.progress((idx + 1) / len(edited_df))
        my_bar.empty()

        if results:
            res_df = pd.DataFrame(results)
            res_df['得分顯示'] = res_df['戰術得分'].astype(str)
            
            st.markdown("### 艦隊總體檢")
            c1, c2, c3 = st.columns(3)
            c1.metric("總投入成本", f"${total_cost:,.2f}")
            c2.metric("當前總市值", f"${(total_cost + total_profit):,.2f}")
            c3.metric("未實現損益", f"${total_profit:+,.2f}", f"{(total_profit/total_cost)*100:+.2f}%" if total_cost>0 else "0%")
            st.markdown("---")

            tab_heat, tab_list = st.tabs(["🗺️ 戰鬥熱力圖", "📋 詳細健檢清單 (手機推薦)"])
            
            with tab_heat:
                st.caption("💡 點擊方塊可查看詳細數據。太小的方塊會自動隱藏文字以保持整潔。")
                fig_tree = px.treemap(
                    res_df, path=['系統建議', '股票代號'], values='當前總值', color='戰術得分', 
                    color_continuous_scale=[US_RED, '#FFCA28', US_GREEN], color_continuous_midpoint=5.5, 
                    custom_data=['得分顯示', '未實現損益顯示']
                )
                fig_tree.update_layout(
                    uniformtext=dict(minsize=14, mode='hide'),
                    margin=dict(t=20, l=0, r=0, b=0), height=500, 
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
                )
                fig_tree.update_traces(
                    texttemplate="<b>%{label}</b><br>得分: %{customdata[0]}<br>損益: %{customdata[1]}", 
                    textfont=dict(color="white"), 
                    hovertemplate="<b>%{label}</b><br>總值: $%<th>{value:,.2f}<extra></extra>", 
                    marker=dict(line=dict(color='black', width=1))
                )
                st.plotly_chart(fig_tree, use_container_width=True)

            with tab_list:
                st.caption("💡 點擊欄位名稱可以進行排序。")
                st.dataframe(
                    res_df[['股票代號', '系統建議', '戰術得分', '未實現損益顯示', '當前總值']],
                    column_config={
                        "股票代號": st.column_config.TextColumn("代號", width="small"),
                        "系統建議": st.column_config.TextColumn("系統判定"),
                        "戰術得分": st.column_config.ProgressColumn("戰鬥力", help="滿分 10 分", format="%.1f", min_value=0, max_value=10),
                        "當前總值": st.column_config.NumberColumn("持倉總值", format="$ %.2f")
                    },
                    use_container_width=True,
                    hide_index=True
                )

# ==========================================
# 頁面 3 & 4: 手冊與設定
# ==========================================
elif page == "📖 戰術手冊":
    st.title(f"📖 {APP_NAME}：指標戰術手冊")
    st.markdown("### 1. 技術軍師 (TA)")
    st.info("**評分邏輯：** 綜合 MA20 均線趨勢、RSI 動能、MACD 交叉與成交量放大。四項條件各佔 2.5 分。\n\n**實戰意義：** 確認目前市場是處於多頭發動還是空頭深淵。")
    st.markdown("### 2. Roland Index (反轉拐點)")
    st.info("**評分邏輯：** 監測股價跌破 3 日均線 (MA3) 的深淵期。一旦站回 MA3 且距反轉點 (DG) 小於 5 天，即觸發 9 分滿分買訊。\n\n**實戰意義：** 專抓左側跌深反彈與右側剛起漲的黃金拐點。")
    st.markdown("### 3. SCTR 動能排名")
    st.info("**評分邏輯：** 結合 200日/50日均線乖離率、125日/20日 ROC 價格變動率。將多週期動能轉化為絕對強度分數。\n\n**實戰意義：** 汰弱留強，過濾掉資金不在其中的死魚股。")
    st.markdown("### 4. 大型 ETF 籌碼庇護")
    st.info("**評分邏輯：** 掃描華爾街大型機構 (Institutions) 的持股比例。>80% 為優，<20% 為劣。\n\n**實戰意義：** 確認下方是否有被動型基金買盤當作安全墊背。")
    st.markdown("### 5. 綜合公允估值")
    st.info("**評分邏輯：** 雙重防線。第一防線看 PEG (本益成長比)，第二防線看華爾街分析師平均目標價的折溢價空間。\n\n**實戰意義：** 確保買進的價格具有足夠的安全邊際，避免買在泡沫高點。")

elif page == "⚙️ 權重設定":
    st.title("⚙️ 戰略權重配置")
    w = st.session_state.weights
    w["TA"] = st.slider("1. 技術軍師", 0, 100, w["TA"])
    w["SCTR"] = st.slider("2. SCTR 動能排名", 0, 100, w["SCTR"])
    w["Roland"] = st.slider("3. Roland Index", 0, 100, w["Roland"])
    w["ETF"] = st.slider("4. ETF 籌碼比例", 0, 100, w["ETF"])
    w["Value"] = st.slider("5. 綜合公允估值", 0, 100, w["Value"])
    st.session_state.weights = w
    if sum(w.values()) != 100: st.warning("⚠️ 總權重需等於 100%")