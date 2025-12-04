import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import plotly.graph_objects as go

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
        
        # 讀取使用者清單 (users 工作表)
        # ttl=0 代表不快取，每次都抓最新資料
        try:
            users_df = conn.read(worksheet="users", ttl=0)
        except Exception:
            st.error("無法讀取使用者資料庫，請確認 Google Sheet 設定是否正確 (是否有名為 'users' 的工作表)。")
            return

        with st.form("login_form"):
            username_input = st.text_input("帳號")
            password_input = st.text_input("密碼", type="password")
            submit = st.form_submit_button("登入")

            if submit:
                # 尋找帳號
                user_match = users_df[users_df['Username'] == username_input]
                
                if not user_match.empty:
                    # 比對密碼 (這裡做簡易比對，真實產品建議加密)
                    stored_password = str(user_match.iloc[0]['Password'])
                    if str(password_input) == stored_password:
                        st.session_state.logged_in = True
                        st.session_state.username = username_input
                        st.session_state.real_name = user_match.iloc[0]['Name']
                        st.success("登入成功！")
                        st.rerun()
                    else:
                        st.error("密碼錯誤")
                else:
                    st.error("找不到此帳號")
        return False # 未登入
    else:
        return True # 已登入

# ==========================================
# 3. 數據處理邏輯 (針對單一用戶)
# ==========================================
def process_user_data(df, freq_hours):
    """處理數據並計算區間用量"""
    if df.empty: return pd.DataFrame()
    
    df = df.sort_values('Timestamp')
    df = df.drop_duplicates(subset=['Timestamp'], keep='last')
    df = df.set_index('Timestamp')
    
    # 時間重採樣與插值
    start_time = df.index[0]
    end_time = df.index[-1]
    
    if start_time == end_time:
        target_times = pd.Index([start_time])
    else:
        target_times = pd.date_range(start=start_time, end=end_time, freq=f'{freq_hours}h')
    
    all_times = df.index.union(target_times).sort_values()
    df_interpolated = df.reindex(all_times)
    df_interpolated['Reading'] = df_interpolated['Reading'].interpolate(method='time')
    
    df_result = df_interpolated.loc[target_times].copy()
    df_result['Usage'] = df_result['Reading'].diff()
    df_result = df_result.reset_index()
    df_result.columns = ['標準時間', '推估度數', '區間用量']
    
    # 產生標籤
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
# 4. 主程式 (Main App)
# ==========================================
def main_app():
    user = st.session_state.username
    real_name = st.session_state.real_name
    
    # 側邊欄：登出與輸入
    with st.sidebar:
        st.write(f"👋 哈囉，**{real_name}**")
        if st.button("登出", type="secondary"):
            st.session_state.logged_in = False
            st.rerun()
        
        st.markdown("---")
        st.header("📝 新增紀錄")
        
        with st.form("entry_form"):
            date_in = st.date_input("日期", datetime.now())
            time_in = st.time_input("時間", datetime.now())
            reading_in = st.number_input("瓦斯表度數", min_value=0.0, format="%.3f", step=0.1)
            
            submit_data = st.form_submit_button("提交紀錄", type="primary")
            
            if submit_data:
                # 1. 讀取目前所有數據
                try:
                    all_data = conn.read(worksheet="logs", ttl=0)
                except:
                    # 如果是空的或第一筆，建立 DataFrame
                    all_data = pd.DataFrame(columns=['Timestamp', 'Username', 'Reading', 'Note'])

                # 2. 準備新資料
                input_dt = datetime.combine(date_in, time_in)
                new_row = pd.DataFrame({
                    'Timestamp': [input_dt],
                    'Username': [user],
                    'Reading': [reading_in],
                    'Note': ["App輸入"]
                })
                
                # 3. 合併並寫回 Google Sheets
                # 為了避免格式問題，確保 Timestamp 是字串或標準格式
                updated_df = pd.concat([all_data, new_row], ignore_index=True)
                conn.update(worksheet="logs", data=updated_df)
                
                st.success("✅ 紀錄已儲存！")
                st.rerun()

    # 主畫面邏輯
    st.title(f"🔥 {real_name} 的天然氣儀表板")
    
    # 1. 讀取並篩選該用戶數據
    try:
        df_all = conn.read(worksheet="logs", ttl=0)
        # 轉換時間格式，避免出錯
        df_all['Timestamp'] = pd.to_datetime(df_all['Timestamp'])
        
        # 【關鍵步驟】只留下目前登入者的資料
        df_user = df_all[df_all['Username'] == user].copy()
        df_user = df_user.sort_values('Timestamp')
        
    except Exception:
        df_user = pd.DataFrame()

    if df_user.empty:
        st.info("目前還沒有您的紀錄，請從左側輸入第一筆數據。")
    else:
        # 顯示基本統計
        latest = df_user['Reading'].iloc[-1]
        total_used = df_user['Reading'].iloc[-1] - df_user['Reading'].iloc[0]
        days = (df_user['Timestamp'].iloc[-1] - df_user['Timestamp'].iloc[0]).days
        
        c1, c2, c3 = st.columns(3)
        c1.metric("目前讀數", f"{latest:.3f}")
        c2.metric("累積用量", f"{total_used:.3f} 度")
        c3.metric("監測天數", f"{days} 天")
        
        st.markdown("---")
        
        # 圖表分析
        tab1, tab2 = st.tabs(["12小時分析", "原始數據"])
        
        with tab1:
            df_12h = process_user_data(df_user, 12)
            if not df_12h.empty:
                avg = df_12h['區間用量'].mean()
                fig = plot_chart(df_12h, avg, "12小時用量趨勢")
                if fig: st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("數據點不足，請輸入至少兩筆不同時間的紀錄。")
                
        with tab2:
            st.dataframe(df_user[['Timestamp', 'Reading', 'Note']], use_container_width=True)

# ==========================================
# 程式進入點
# ==========================================
if __name__ == "__main__":
    if login_system():
        main_app()
