import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import plotly.graph_objects as go

# ==========================================
# 0. 設定區
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1b55B_GkbT4vDwG2T5-wDQXs5RMlN8tkrBEVXvpzmrt4/edit?usp=sharing"

st.set_page_config(page_title="天然氣管家 (雲端版)", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 1. 登入系統
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
            st.error(f"連線失敗: {e}")
            return False

        with st.form("login_form"):
            user_input = st.text_input("帳號")
            pwd_input = st.text_input("密碼", type="password")
            if st.form_submit_button("登入"):
                clean_user = str(user_input).strip()
                clean_pwd = str(pwd_input).strip()
                
                # 尋找帳號
                match = users_df[users_df['Username'].astype(str).str.strip() == clean_user]

                if not match.empty:
                    # 處理密碼 (去除 .0)
                    db_pass = str(match.iloc[0]['Password']).strip().replace(".0", "")
                    if db_pass == clean_pwd:
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
# 2. 主程式 (含圖表與日期修復)
# ==========================================
def main_app():
    user = st.session_state.username
    st.sidebar.write(f"👋 歡迎, {st.session_state.real_name}")
    
    if st.sidebar.button("登出"):
        st.session_state.logged_in = False
        st.rerun()

    # --- 新增紀錄區塊 ---
    with st.sidebar.form("add_data"):
        st.header("📝 新增紀錄")
        date_in = st.date_input("日期", datetime.now())
        time_in = st.time_input("時間", datetime.now())
        val = st.number_input("度數", min_value=0.0, format="%.3f")
        
        if st.form_submit_button("提交"):
            try:
                logs_df = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
            except:
                logs_df = pd.DataFrame(columns=['Timestamp', 'Username', 'Reading', 'Note'])
            
            ts_str = datetime.combine(date_in, time_in).strftime("%Y-%m-%d %H:%M:%S")
            
            new_row = pd.DataFrame({
                'Timestamp': [ts_str],
                'Username': [user],
                'Reading': [val],
                'Note': ["App"]
            })
            
            updated_df = pd.concat([logs_df, new_row], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="logs", data=updated_df)
            st.success("成功儲存！")
            st.rerun()

    # --- 儀表板區塊 ---
    st.title("🔥 天然氣用量儀表板")
    
    try:
        # 1. 讀取資料
        df = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
        
        # 2. 過濾該用戶資料
        user_df = df[df['Username'].astype(str).str.strip() == str(user).strip()].copy()
        
        if not user_df.empty:
            # ========================================================
            # 🔴 關鍵修復區：處理日期格式不一致的問題
            # ========================================================
            # format='mixed' 允許同時存在 "2025/11/29" 和 "2025-11-29 18:00"
            # errors='coerce' 如果遇到無法解析的亂碼，會變成 NaT (空值) 而不是報錯
            user_df['Timestamp'] = pd.to_datetime(user_df['Timestamp'], format='mixed', errors='coerce')
            
            # 刪除日期解析失敗的空行 (防止圖表報錯)
            user_df = user_df.dropna(subset=['Timestamp'])
            
            # 排序
            user_df = user_df.sort_values(by='Timestamp')
            # ========================================================

            # --- A. 顯示關鍵指標 (最新狀態) ---
            if not user_df.empty:
                last_record = user_df.iloc[-1]
                col1, col2 = st.columns(2)
                col1.metric("最新度數", f"{last_record['Reading']} 度")
                col2.metric("上次抄表時間", last_record['Timestamp'].strftime("%Y-%m-%d"))

                st.markdown("---")

                # --- B. 繪製圖表 (Plotly) ---
                st.subheader("📈 用量趨勢圖")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=user_df['Timestamp'], 
                    y=user_df['Reading'],
                    mode='lines+markers',
                    name='度數',
                    line=dict(color='#FF4B4B', width=3)
                ))
                fig.update_layout(
                    xaxis_title="日期",
                    yaxis_title="度數",
                    hovermode="x unified",
                    template="plotly_dark"
                )
                st.plotly_chart(fig, use_container_width=True)

                # --- C. 顯示詳細資料表 ---
                with st.expander("查看詳細數據表格"):
                    display_df = user_df.sort_values(by='Timestamp', ascending=False)
                    display_df['Timestamp'] = display_df['Timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
                    st.dataframe(display_df, use_container_width=True)
            else:
                st.warning("所有日期的格式都無法辨識，請檢查 Google Sheet 內容。")

        else:
            st.info("尚無抄表紀錄，請從左側新增第一筆資料。")
            
    except Exception as e:
        st.error(f"讀取資料失敗: {e}")

if __name__ == "__main__":
    if login_system():
        main_app()
