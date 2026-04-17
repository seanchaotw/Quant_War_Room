import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from PIL import Image
import os

# ==========================================
# 系統初始化與基本設定 (解決 Logo 快取問題)
# ==========================================
try:
    # 強制讀取圖片檔，繞過瀏覽器路徑快取
    icon_image = Image.open("logo.png")
    st.set_page_config(page_title="量化戰情室", page_icon=icon_image)
except Exception as e:
    # 如果找不到圖檔，退回預設靶心
    st.set_page_config(page_title="量化戰情室", page_icon="🎯")

# 全域 CSS 魔法 (包含跑馬燈與卡片美化)
st.markdown("""
<style>
    div[data-testid="metric-container"] {
        background-color: rgba(128,128,128,0.05);
        border: 1px solid rgba(128,128,128,0.2);
        padding: 10px;
        border-radius: 10px;
        box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
    }
    
    /* 華爾街跑馬燈特效 */
    .ticker-wrap {
        width: 100%;
        overflow: hidden;
        background-color: #1E1E1E;
        padding-left: 100%;
        box-sizing: content-box;
        border-top: 2px solid #333;
        border-bottom: 2px solid #333;
        margin-bottom: 15px;
    }
    .ticker {
        display: inline-block;
        white-space: nowrap;
        padding-right: 100%;
        box-sizing: content-box;
        animation-iteration-count: infinite;
        animation-timing-function: linear;
        animation-name: ticker;
        animation-duration: 30s;
    }
    .ticker__item {
        display: inline-block;
        padding: 0 2rem;
        font-size: 16px;
        color: white;
        font-weight: 600;
    }
    @keyframes ticker {
        0% { transform: translate3d(0, 0, 0); visibility: visible; }
        100% { transform: translate3d(-100%, 0, 0); }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 預設權重鎖定 (依照長官指令配置)
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
        if data.empty: return None, None
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
        if data.empty: return None, None

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
        etf_score = 9 if inst_pct > 80 else (7 if inst_pct > 50 else (3 if inst_pct < 20 else 5))

        tgt = info.get('targetMeanPrice', curr_price)
        peg = info.get('pegRatio', 0)
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
            "dg": dg, "gg": gg, "inst_pct": inst_pct, "upside": upside, "target": tgt, "peg": peg
        }
        return data, metrics
    except Exception as e:
        # 把原本的 return None, None 改成把錯誤訊息傳出來
        return None, f"系統底層錯誤: {str(e)}"

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
        symbol = st.sidebar.selectbox("選擇要掃描的個股 (下方戰情室)", current_symbols)

    manual = st.sidebar.text_input("或直接手動輸入單檔代號").upper()
    if manual: symbol = manual

# ==========================================
# 頁面 1: 戰情儀表板
# ==========================================
if page == "📈 戰情儀表板":
    
    # 掃描清單動能，並製作跑馬燈與 Top 5
    if current_symbols and not manual:
        top_list = []
        marquee_html = '<div class="ticker-wrap"><div class="ticker">'
        
        with st.spinner("掃描清單動能與即時報價中..."):
            for sym in current_symbols:
                _, m = analyze_stock(sym, st.session_state.weights)
                if m: 
                    top_list.append(m)
                    # 組合跑馬燈字串
                    m_color = "#26A69A" if m['change'] >= 0 else "#EF5350"
                    m_arrow = "▲" if m['change'] >= 0 else "▼"
                    marquee_html += f'<div class="ticker__item">{sym} <span style="color:{m_color};">${m["price"]:.2f} ({m_arrow}{abs(m["pct_change"]):.2f}%)</span></div>'
        
        marquee_html += '</div></div>'
        
        # 顯示超酷炫跑馬燈
        st.markdown(marquee_html, unsafe_allow_html=True)
        
        st.markdown(f"### 🏆 「{selected_list}」Top 5 強勢狙擊榜")
        
        top_list.sort(key=lambda x: x['final'], reverse=True)
        top_k = top_list[:5]
        
        if top_k:
            # 【手機版神級排版】：使用 CSS Grid 取代 st.columns
            # 確保在手機上呈現 2 欄的滿版方塊，上漲綠底、下跌紅底
            grid_html = '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 20px;">'
            for idx, t_m in enumerate(top_k):
                bg_color = "#26A69A" if t_m['pct_change'] >= 0 else "#EF5350"
                sign = "+" if t_m['pct_change'] >= 0 else ""
                grid_html += f"""
                <div style="background-color: {bg_color}; border-radius: 12px; padding: 15px; color: white; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
                    <div style="font-size: 14px; font-weight: 600; opacity: 0.9;">#{idx+1} {t_m['symbol']}</div>
                    <div style="font-size: 26px; font-weight: 900; margin: 8px 0;">{t_m['final']:.1f}</div>
                    <div style="font-size: 14px; font-weight: 600;">{sign}{t_m['pct_change']:.2f}%</div>
                </div>
                """
            grid_html += '</div>'
            st.markdown(grid_html, unsafe_allow_html=True)
        st.markdown("---")

   if symbol:
        with st.spinner("雷達掃描中..."):
            data, m = analyze_stock(symbol, st.session_state.weights)
        
        if data is None:
            st.error(f"無法取得 {symbol} 數據。")
            st.warning(f"⚠️ 除錯雷達攔截原因：{m}")  # <--- 新增這行，印出真正死因
        else:
            st.markdown(f"## 🎯 {symbol} | {m['name']}")
            
            color = "#26A69A" if m['change'] >= 0 else "#EF5350"
            arrow = "▲" if m['change'] >= 0 else "▼"
            html_metrics = f"""
            <div style="display:flex; flex-wrap: wrap; gap: 10px; justify-content:space-around; text-align:center; padding: 15px; background-color: rgba(128,128,128,0.05); border-radius: 8px; margin-bottom: 20px; box-shadow: 2px 2px 8px rgba(0,0,0,0.1);">
                <div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">💰 收盤價</div><b style="font-size:18px;">${m['price']:.2f}</b><br><span style="color:{color}; font-size:12px; font-weight:bold;">{arrow} {abs(m['change']):.2f} ({m['pct_change']:+.2f}%)</span></div>
                <div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">⏱️ 開盤</div><b style="font-size:16px;">${m['open']:.2f}</b></div>
                <div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">📈 最高</div><b style="font-size:16px;">${m['high']:.2f}</b></div>
                <div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">📉 最低</div><b style="font-size:16px;">${m['low']:.2f}</b></div>
                <div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">🌊 振幅</div><b style="font-size:16px;">{m['amplitude']:.2f}%</b></div>
                <div style="min-width: 80px;"><div style="color:gray; font-size:12px; margin-bottom:4px;">🏷️ 市值規模</div><b style="font-size:14px;">{m['cap_size']}</b></div>
            </div>
            """
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
                
                vol_colors = ['#EF5350' if row['Close'] < row['Open'] else '#26A69A' for index, row in plot_data.iterrows()]
                macd_colors = ['#26A69A' if val >= 0 else '#EF5350' for val in plot_data['MACDh_12_26_9']]
                
                fig.add_trace(go.Candlestick(x=x_dates, open=plot_data['Open'], high=plot_data['High'], low=plot_data['Low'], close=plot_data['Close'], name='股價', increasing_line_color='#26A69A', decreasing_line_color='#EF5350'), row=1, col=1)
                fig.add_trace(go.Scatter(x=x_dates, y=plot_data['EMA200'], line=dict(color='gray', width=2, dash='dot'), name='EMA200'), row=1, col=1)
                fig.add_trace(go.Scatter(x=x_dates, y=plot_data['MA3'], line=dict(color='#FFCA28', width=2), name='MA3'), row=1, col=1)
                
                fig.add_trace(go.Bar(x=x_dates, y=plot_data['Volume'], marker_color=vol_colors, name='成交量'), row=2, col=1)
                
                fig.add_trace(go.Bar(x=x_dates, y=plot_data['MACDh_12_26_9'], marker_color=macd_colors, name='MACD 柱狀圖'), row=3, col=1)
                fig.add_trace(go.Scatter(x=x_dates, y=plot_data['MACD_12_26_9'], line=dict(color='#FF9800', width=1.5), name='MACD 線'), row=3, col=1)
                fig.add_trace(go.Scatter(x=x_dates, y=plot_data['MACDs_12_26_9'], line=dict(color='#2196F3', width=1.5), name='訊號線'), row=3, col=1)
                fig.add_hline(y=0, line_dash="dash", line_color="rgba(255,255,255,0.3)", line_width=1, row=3, col=1) 
                
                fig.add_trace(go.Scatter(x=x_dates, y=plot_data['RSI'], line=dict(color='#E040FB', width=1.5), name='RSI(14)'), row=4, col=1)
                fig.add_hline(y=70, line_dash="dash", line_color="#EF5350", line_width=1.5, row=4, col=1) 
                fig.add_hline(y=50, line_dash="dot", line_color="rgba(255,255,255,0.3)", line_width=1, row=4, col=1)   
                fig.add_hline(y=30, line_dash="dash", line_color="#26A69A", line_width=1.5, row=4, col=1) 
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
                    st.caption(f"• 機構持股比例: {m['inst_pct']:.1f}%")

                with st.expander(f"5️⃣ 公允估值: {m['val']} / 10"):
                    st.caption(f"• 華爾街目標價: ${m['target']:.2f} ({m['upside']:+.1f}%)")
                    st.caption(f"• PEG 成長比: {m['peg']:.2f}" if m['peg'] else "• PEG 成長比: 無資料")

# ==========================================
# 頁面 2: 實戰持倉管理 
# ==========================================
elif page == "💼 實戰持倉管理":
    st.title("💼 實戰持倉管理")
    
    with st.expander("📝 編輯持倉部位 (點擊展開/收合)", expanded=True):
        st.caption("輸入成本與股數後，點擊下方按鈕進行全軍健檢。")
        edited_df = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True, key="portfolio_editor")
        st.session_state.portfolio = edited_df
        run_check = st.button("🚀 啟動部位健檢", type="primary", use_container_width=True)

    if run_check:
        results, total_profit, total_cost = [], 0, 0
        my_bar = st.progress(0, text="戰鬥數據結算中...")
        
        for idx, row in edited_df.iterrows():
            sym, cost, shares = row['代號'].upper(), float(row['持倉成本']), float(row['股數'])
            _, m = analyze_stock(sym, st.session_state.weights)
            if m:
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
                    color_continuous_scale=['#EF5350', '#FFCA28', '#26A69A'], color_continuous_midpoint=5.5, 
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
    st.title("📖 量化戰情室：指標戰術手冊")
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