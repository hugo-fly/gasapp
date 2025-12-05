import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import plotly.graph_objects as go

# ==========================================
# 0. 設定區 (這裡一定要填入您的 Google Sheet 網址)
# ==========================================
# 請確認這個網址是您目前使用的表格
SHEET_URL = "https://docs.google.com/spreadsheets/d/1b55B_GkbT4vDwG2T5-wDQXs5RMlN8tkrBEVXvpzmrt4/edit?usp=sharing"

# ==========================================
# 1. 頁面設定與連接資料庫
# ==========================================
st.set_page_config(page_title="天然氣管家 (雲端版)", layout="wide")

# 建立 Google Sheets 連線
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 2. 登入系統邏輯
# ==========================================
def login_system():
    """處理登入介面與驗證"""
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.real_name = ""

    if not st.session_state.logged_in:
        st.header("🔐 用戶登入")
        
        try:
            # 修正點 1: 加入 spreadsheet=SHEET_URL 參數
            users_df = conn.read(spreadsheet=SHEET_URL, worksheet="users", ttl=0)
            users_df.columns = users_df.columns.str.strip()
        except Exception as e:
            st.error(f"無法讀取使用者資料庫: {e}")
            return False

        with st.form("login_form"):
            username_input = st.text_input("帳號")
            password_input = st.text_input("密碼", type="password")
            submit = st.form_submit_button("登入")

            if submit:
                clean_user = str(username_input).strip()
                clean_pwd = str(password_input).strip()

                user_match = users_df[users_df['Username'].astype(str).str.strip() == clean_user]
                
                if not user_match.empty:
                    stored_password = str(user_match.iloc[0]['Password']).strip().replace(".0", "")
                    
                    if clean_pwd == stored_password:
                        st.session_state.logged_in = True
                        st.session_state.username = clean_user
                        st.session_state.real_name = user_match.iloc[0]['Name']
                        st.success("登入成功！")
                        st.rerun()
                    else:
                        st.error("密碼錯誤")
                else:
                    st.error("找不到此帳號")
        return False
    else:
        return True

# ==========================================
# 3. 數據處理邏輯
# ==========================================
def process_user_data(df, freq_hours):
    """處理數據並計算區間用量"""
    if df.empty: return pd.DataFrame()
    
    df = df.sort_values('Timestamp')
    df = df.drop_duplicates(subset=['Timestamp'], keep='last')
    df = df.set_index('Timestamp')
    
    start_time = df.index[0]
    end_time = df.index[-1]
    
    if start_time == end_time:
        target_times = pd.Index([start_time])
    else:
        target_times = pd.date_range(start=start_time, end=end_time, freq=f'{freq_hours}h')
    
    all_times = df.index.union(target_times).sort_values().unique()
    
    df_interpolated = df.reindex(all_times)
    df_interpolated['Reading'] = pd.to_numeric(df_interpolated['Reading'], errors='coerce')
    df_interpolated['Reading'] = df_interpolated['Reading'].interpolate(method='time')
    
    valid_targets = target_times.intersection(df_interpolated.index)
    df_result = df_interpolated.loc[valid_targets].copy()
    
    df_result['Usage'] = df_result['Reading'].diff()
    df_result = df_result.reset_index()
    df_result.columns = ['標準時間', '推估度數', '區間用量']
    
    labels = []
    for dt in df_result['標準時間']:
        dt_start = dt - pd.Timedelta(hours=freq_hours)
        period = "上午" if dt_start.hour < 12 else "下午"
        if freq_hours == 12:
            labels.append(f"{dt_start.strftime('%m/%d')} {period}")
        else:
            labels.append(f"{dt_start.strftime('%m/%d')}")
    df_result['圖表標籤'] = labels
    
    return df_result

def plot_chart(df, avg_val, title):
    """繪製圖表"""
    plot_df = df.iloc[1:].copy()
    if plot_df.empty: return None

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot_df['圖表標籤'], y=plot_df['區間用量'],
        name='區間用量', marker_color='#5B9BD5',
        text=plot_df['區間用量'].round(2), textposition='auto'
    ))
    fig.add_trace(go.Scatter(
        x=plot_df['圖表標籤'], y=[avg_val] * len(plot_df),
        name='平均用量', line=dict(color='red', width=2, dash='dash')
    ))
    fig.update_layout(title=title, hovermode="x unified")
    return fig

# ==========================================
# 4. 主程式
# ==========================================
def main
