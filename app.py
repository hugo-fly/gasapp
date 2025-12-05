import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
import plotly.graph_objects as go

# ==========================================
# 0. 設定：請在此填入你的 Google Sheet 網址
# ==========================================
# 請確認這是不是你最新的那個試算表網址
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
            # 這裡直接指定網址，避開錯誤
            users_df = conn.read(spreadsheet=SHEET_URL, worksheet="users", ttl=0)
        except Exception as e:
            st.error(f"連線失敗，請檢查 Secrets 或 API 設定。錯誤訊息: {e}")
            return False

        with st.form("login_form"):
            user = st.text_input("帳號")
            pwd = st.text_input("密碼", type="password")
            if st.form_submit_button("登入"):
                # 強制轉字串比對
                match = users_df[users_df['Username'].astype(str) == str(user)]
                if not match.empty and str(match.iloc[0]['Password']) == str(pwd):
                    st.session_state.logged_in = True
                    st.session_state.username = user
                    st.session_state.real_name = match.iloc[0]['Name']
                    st.success("登入成功")
                    st.rerun()
                else:
                    st.error("帳號或密碼錯誤")
        return False
    return True

# ==========================================
# 2. 主程式
# ==========================================
def main_app():
    user = st.session_state.username
    st.sidebar.write(f"👋 {st.session_state.real_name}")
    if st.sidebar.button("登出"):
        st.session_state.logged_in = False
        st.rerun()

    with st.sidebar.form("add_data"):
        st.header("📝 新增紀錄")
        date_in = st.date_input("日期", datetime.now())
        time_in = st.time_input("時間", datetime.now())
        val = st.number_input("度數", min_value=0.0, format="%.3f")
        if st.form_submit_button("提交"):
            try:
                # 讀取 logs
                df = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
            except:
                df = pd.DataFrame(columns=['Timestamp', 'Username', 'Reading', 'Note'])
            
            new_row = pd.DataFrame({
                'Timestamp': [datetime.combine(date_in, time_in)],
                'Username': [user],
                'Reading': [val],
                'Note': ["App"]
            })
            # 寫入 logs
            conn.update(spreadsheet=SHEET_URL, worksheet="logs", data=pd.concat([df, new_row], ignore_index=True))
            st.success("成功！")
            st.rerun()

    st.title("🔥 天然氣儀表板")
    try:
        # 讀取並顯示數據
        df = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
        user_df = df[df['Username'] == user]
        if not user_df.empty:
            st.dataframe(user_df)
        else:
            st.info("尚無資料")
    except Exception as e:
        st.error(f"讀取資料失敗: {e}")

if __name__ == "__main__":
    if login_system():
        main_app()

if __name__ == "__main__":
    if login_system():
        main_app()

