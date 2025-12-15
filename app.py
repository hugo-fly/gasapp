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
# 2. 核心數學邏輯：強制對齊內插法 (修復圖表缺漏)
# ==========================================
def calculate_interpolated_usage(df, interval_code):
    """
    df: 原始數據
    interval_code: '12h' 或 '1D' (24小時)
    """
    if df.empty or len(df) < 2:
        return pd.DataFrame()

    # 🟢 關鍵：建立副本，保護原始數據不被修改
    work_df = df.copy()

    # 1. 整理索引
    work_df = work_df.sort_values('Timestamp')
    work_df = work_df.set_index('Timestamp')
    work_df = work_df[~work_df.index.duplicated(keep='last')]

    # 2. 建立強制對齊的目標網格 (例如 00:00, 12:00)
    start = work_df.index[0].floor('D') 
    end = work_df.index[-1].ceil('D')
    
    freq = interval_code
    if freq == '1D': freq = 'D'
    
    target_range = pd.date_range(start=start, end=end, freq=freq)
    
    # 3. 合併並內插
    combined_index = work_df.index.union(target_range).sort_values()
    df_interpolated = work_df[['Reading']].reindex(combined_index)
    df_interpolated['Reading'] = pd.to_numeric(df_interpolated['Reading'], errors='coerce')
    df_interpolated['Reading'] = df_interpolated['Reading'].interpolate(method='time')
    
    # 4. 取出目標網格點
    df_final = df_interpolated.loc[target_range].copy()
    
    # 5. 計算區間用量
    df_final['Usage'] = df_final['Reading'].diff()
    
    # 6. 處理負值 (防止資料異常導致圖表消失)
    # 如果用量為負，我們將其設為 0，但在圖表中這會顯示為無柱狀
    # 建議使用者檢查該時段的原始讀數是否合理 (後面的數字不能比前面小)
    df_final.loc[df_final['Usage'] < 0, 'Usage'] = 0 
    
    df_final = df_final.dropna(subset=['Usage'])
    
    # 7. 格式整理
    df_final['Timestamp'] = df_final.index
    df_final = df_final.reset_index(drop=True)
    df_final = df_final[['Timestamp', 'Reading', 'Usage']]
    df_final.columns = ['時間點', '推估讀數', '區間用量']
    
    # 產生標籤
    labels = []
    for t in df_final['時間點']:
        if interval_code == '12h':
            # 標籤顯示為該時段的開始時間
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

    # 🟢 這裡加上數據表，讓使用者檢查為什麼某個柱子是 0
    with st.expander("查看詳細計算數據"):
        st.dataframe(df)

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
        df_all['Timestamp'] = pd.to_datetime(df_all['Timestamp'], format='mixed', errors='coerce')
        df_all = df_all.dropna(subset=['Timestamp'])
        
        df = df_all[df_all['Username'].astype(str).str.strip() == str(user).strip()].copy()
        df['Reading'] = pd.to_numeric(df['Reading'], errors='coerce')
        df = df.sort_values('Timestamp')
        
    except Exception as e:
        st.error(f"數據讀取失敗: {e}")
        df = pd.DataFrame()

    if df.empty:
        st.info("尚無數據，請從左側新增第一筆紀錄。")
    else:
        latest_read = df.iloc[-1]['Reading']
        first_read = df.iloc[0]['Reading']
        total_days = (df.iloc[-1]['Timestamp'] - df.iloc[0]['Timestamp']).days
        
        if total_days > 0:
            est_monthly = ((latest_read - first_read) / total_days * 30)
        else:
            est_monthly = 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("目前讀數", f"{latest_read:.2f}")
        c2.metric("總累積用量", f"{(latest_read - first_read):.2f}")
        c3.metric("監測天數", f"{total_days} 天")
        c4.metric("預估月用量", f"{est_monthly:.1f}")

        st.divider()

        tab1, tab2, tab3, tab4 = st.tabs(["📊 12H 分析", "📅 24H 分析", "📈 累積趨勢", "📋 資料管理"])

        with tab1:
            df_12h = calculate_interpolated_usage(df, '12h')
            draw_bar_chart(df_12h, "每12小時用量 (早/晚)", "#636EFA")

        with tab2:
            df_24h = calculate_interpolated_usage(df, '1D')
            draw_bar_chart(df_24h, "每日總用量 (24H)", "#EF553B")

        with tab3:
            draw_trend_chart(df)

        with tab4:
            st.subheader("📋 原始數據管理")
            
            record_options = df.sort_values('Timestamp', ascending=False)['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist()
            
            if not record_options:
                st.warning("沒有可供管理的數據。")
            else:
                col1, col2 = st.columns(2)
                
                with col1:
                    with st.expander("✏️ 修改數據", expanded=True):
                        edit_target_str = st.selectbox("選擇紀錄", record_options, key="edit_sel")
                        current_row_mask = df['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S') == edit_target_str
                        if current_row_mask.any():
                            current_row = df[current_row_mask].iloc[0]
                            new_date = st.date_input("修正日期", current_row['Timestamp'])
                            new_time = st.time_input("修正時間", current_row['Timestamp'])
                            new_val = st.number_input("修正度數", value=float(current_row['Reading']), step=0.1, format="%.3f")
                            
                            if st.button("確認修改", type="primary"):
                                try:
                                    fresh = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
                                    fresh['Timestamp'] = pd.to_datetime(fresh['Timestamp'], format='mixed', errors='coerce')
                                    db_ts_str = fresh['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
                                    mask = (fresh['Username'].astype(str).str.strip() == str(user).strip()) & (db_ts_str == edit_target_str)
                                    
                                    if mask.any():
                                        new_ts = datetime.combine(new_date, new_time)
                                        fresh.loc[mask, 'Timestamp'] = new_ts
                                        fresh.loc[mask, 'Reading'] = new_val
                                        fresh.loc[mask, 'Note'] = "App修改"
                                        conn.update(spreadsheet=SHEET_URL, worksheet="logs", data=fresh)
                                        st.success("修改成功！")
                                        st.rerun()
                                    else:
                                        st.error(f"找不到原始資料。")
                                except Exception as e:
                                    st.error(f"錯誤: {e}")

                with col2:
                    with st.expander("🗑️ 刪除數據", expanded=True):
                        del_target_str = st.selectbox("選擇紀錄", record_options, key="del_sel")
                        if st.button("確認刪除", type="primary"):
                            try:
                                fresh = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
                                fresh['Timestamp'] = pd.to_datetime(fresh['Timestamp'], format='mixed', errors='coerce')
                                db_ts_str = fresh['Timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')
                                mask = (fresh['Username'].astype(str).str.strip() == str(user).strip()) & (db_ts_str == del_target_str)
                                
                                if mask.any
