import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import plotly.graph_objects as go
import plotly.express as px

# ==========================================
# 0. 設定區
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1b55B_GkbT4vDwG2T5-wDQXs5RMlN8tkrBEVXvpzmrt4/edit?usp=sharing"

st.set_page_config(page_title="天然氣管家 Pro", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 1. 強健的登入系統
# ==========================================
def login_system():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.real_name = ""

    if not st.session_state.logged_in:
        st.header("🔐 用戶登入")
        try:
            users_df = conn.read(spreadsheet=SHEET_URL, worksheet="users", ttl=0)
            users_df.columns = users_df.columns.str.strip()
        except Exception as e:
            st.error(f"無法讀取使用者資料庫，請檢查連線。錯誤: {e}")
            return False

        with st.form("login_form"):
            user_in = st.text_input("帳號")
            pwd_in = st.text_input("密碼", type="password")
            if st.form_submit_button("登入"):
                clean_user = str(user_in).strip()
                match = users_df[users_df['Username'].astype(str).str.strip() == clean_user]
                
                if not match.empty:
                    db_pass = str(match.iloc[0]['Password']).strip().replace(".0", "")
                    if str(pwd_in).strip() == db_pass:
                        st.session_state.logged_in = True
                        st.session_state.username = clean_user
                        st.session_state.real_name = match.iloc[0]['Name']
                        st.success("登入成功")
                        st.rerun()
                    else:
                        st.error("密碼錯誤")
                else:
                    st.error("找不到帳號")
        return False
    return True

# ==========================================
# 2. 核心數學邏輯：強制對齊內插法 (保護原始數據版)
# ==========================================
def calculate_interpolated_usage(df, interval_code):
    """
    df: 原始數據
    interval_code: '12h' 或 '1D' (24小時)
    """
    if df.empty or len(df) < 2:
        return pd.DataFrame()

    # 🟢 第一步：建立副本 (關鍵！)
    # 這行確保我們接下來的所有操作都在 'work_df' 上進行
    # 絕對不會去修改到原本傳進來的 'df' (Raw Data)
    work_df = df.copy()

    # 1. 整理索引，刪除重複時間點
    work_df = work_df.sort_values('Timestamp')
    work_df = work_df.set_index('Timestamp')
    work_df = work_df[~work_df.index.duplicated(keep='last')]

    # 2. 建立強制對齊的目標時間網格 (00:00, 12:00 等)
    # 確保範圍涵蓋整天，解決圖表缺漏問題
    start = work_df.index[0].floor('D') 
    end = work_df.index[-1].ceil('D')
    
    # 設定頻率：12h 或 1D
    freq = interval_code
    if freq == '1D': freq = 'D'
    
    target_range = pd.date_range(start=start, end=end, freq=freq)
    
    # 3. 合併「原始抄表時間」與「目標網格時間」
    # 讓我們能利用原始數據，推算出網格點上的數值
    combined_index = work_df.index.union(target_range).sort_values()
    
    # 4. 重建索引並進行「時間內插」
    # 這裡產生的 df_interpolated 是一個全新的 DataFrame
    df_interpolated = work_df[['Reading']].reindex(combined_index)
    df_interpolated['Reading'] = pd.to_numeric(df_interpolated['Reading'], errors='coerce')
    df_interpolated['Reading'] = df_interpolated['Reading'].interpolate(method='time')
    
    # 5. 只取出我們關心的目標網格點 (00:00, 12:00)
    df_final = df_interpolated.loc[target_range].copy()
    
    # 6. 計算區間用量 (本次讀數 - 上次讀數)
    df_final['Usage'] = df_final['Reading'].diff()
    
    # 7. 清理數據
    df_final = df_final.dropna(subset=['Usage'])
    df_final.loc[df_final['Usage'] < 0, 'Usage'] = 0 # 歸零微小負值
    
    # 8. 格式整理與標籤生成
    df_final['Timestamp'] = df_final.index
    df_final = df_final.reset_index(drop=True)
    df_final = df_final[['Timestamp', 'Reading', 'Usage']]
    df_final.columns = ['時間點', '推估讀數', '區間用量']
    
    # 產生直覺的圖表標籤
    labels = []
    for t in df_final['時間點']:
        # 邏輯：12/01 00:00 的讀數 - 11/30 12:00 的讀數 = 11/30 下午的用量
        # 所以標籤顯示要往前推
        if interval_code == '12h':
            label_time = t - pd.Timedelta(hours=12)
            period = "上午" if label_time.hour < 12 else "下午"
            labels.append(f"{label_time.strftime('%m/%d')} {period}")
        else:
            label_time = t - pd.Timedelta(days=1)
            labels.append(f"{label_time.strftime('%m/%d')}")
            
    df_final['標籤'] = labels
    
    return df_final

# ==========================================
# 3. 繪圖邏輯
# ==========================================
def draw_bar_chart(df, title, color_code):
    if df.empty:
        st.info("數據不足，無法繪製圖表")
        return

    avg_val = df['區間用量'].mean()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df['標籤'], y=df['區間用量'], name='用量',
        marker_color=color_code, text=df['區間用量'].round(2), textposition='auto'
    ))
    fig.add_trace(go.Scatter(
        x=df['標籤'], y=[avg_val] * len(df), name='平均值',
        line=dict(color='red', width=2, dash='dash')
    ))
    fig.update_layout(
        title=title, yaxis_title="度數 (m³)", hovermode="x unified",
        template="plotly_dark", margin=dict(l=20, r=20, t=50, b=20)
    )
    st.plotly_chart(fig, use_container_width=True)

def draw_trend_chart(raw_df):
    if raw_df.empty: return
    fig = px.line(raw_df, x='Timestamp', y='Reading', markers=True, title="📈 瓦斯表讀數累積趨勢 (原始數據)")
    fig.update_traces(line_color='#00CC96', line_width=3)
    fig.update_layout(template="plotly_dark", yaxis_title="累積度數")
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 4. 主程式
# ==========================================
def main_app():
    user = st.session_state.username
    real_name = st.session_state.real_name
    
    with st.sidebar:
        st.write(f"👋 嗨，**{real_name}**")
        if st.button("登出", type="secondary"):
            st.session_state.logged_in = False
            st.rerun()
        
        st.divider()
        st.header("📝 新增抄表")
        
        with st.form("entry"):
            date_in = st.date_input("日期", datetime.now())
            time_in = st.time_input("時間", datetime.now())
            val_in = st.number_input("目前度數", min_value=0.0, format="%.3f", step=0.1)
            
            if st.form_submit_button("提交"):
                try:
                    logs = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
                except:
                    logs = pd.DataFrame(columns=['Timestamp', 'Username', 'Reading', 'Note'])
                
                ts_str = datetime.combine(date_in, time_in).strftime("%Y-%m-%d %H:%M:%S")
                new_data = pd.DataFrame({
                    'Timestamp': [ts_str],
                    'Username': [user],
                    'Reading': [val_in],
                    'Note': ["App"]
                })
                
                updated = pd.concat([logs, new_data], ignore_index=True)
                conn.update(spreadsheet=SHEET_URL, worksheet="logs", data=updated)
                st.toast("✅ 紀錄已儲存！")
                st.rerun()

    st.title("🔥 天然氣用量儀表板")

    # 1. 讀取與清洗數據
    try:
        df_all = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
        
        # 加上 format='mixed' 解決日期格式報錯
        df_all['Timestamp'] = pd.to_datetime(df_all['Timestamp'], format='mixed', errors='coerce')
        df_all = df_all.dropna(subset=['Timestamp'])
        
        # 這裡的 df 是原始數據，後續傳入 calculate_interpolated_usage 時會被複製，不會被修改
        df = df_all[df_all['Username'].astype(str).str.strip() == str(user).strip()].copy()
        df['Reading'] = pd.to_numeric(df['Reading'], errors='coerce')
        df
