import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection

# ==========================================
# 0. 設定區
# ==========================================
# 您的 Google Sheet 網址
SHEET_URL = "https://docs.google.com/spreadsheets/d/1b55B_GkbT4vDwG2T5-wDQXs5RMlN8tkrBEVXvpzmrt4/edit?usp=sharing"

st.set_page_config(page_title="天然氣管家 (雲端版)", layout="wide")
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# 1. 登入系統 (已增強容錯能力)
# ==========================================
def login_system():
    # 初始化 Session State
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.real_name = ""

    # 如果尚未登入，顯示登入畫面
    if not st.session_state.logged_in:
        st.header("🔐 用戶登入")
        
        try:
            # 讀取 users 分頁，ttl=0 確保讀到最新數據
            users_df = conn.read(spreadsheet=SHEET_URL, worksheet="users", ttl=0)
            
            # 確保欄位名稱沒有奇怪的空格 (防呆)
            users_df.columns = users_df.columns.str.strip()
            
        except Exception as e:
            st.error(f"連線失敗，請檢查 secrets.toml 設定或網路連線。\n錯誤訊息: {e}")
            return False

        with st.form("login_form"):
            user_input = st.text_input("帳號")
            pwd_input = st.text_input("密碼", type="password")
            submit_btn = st.form_submit_button("登入")

            if submit_btn:
                # --- 核心修正邏輯 ---
                
                # 1. 清理使用者輸入 (轉字串 + 去除前後空白)
                clean_user_input = str(user_input).strip()
                clean_pwd_input = str(pwd_input).strip()

                # 2. 在資料庫中尋找帳號 (將資料庫欄位也轉字串 + 去空白)
                # 使用 .astype(str) 避免數字帳號報錯
                match = users_df[users_df['Username'].astype(str).str.strip() == clean_user_input]

                if not match.empty:
                    # 3. 取得資料庫密碼，並進行深度清理
                    db_pass_raw = match.iloc[0]['Password']
                    
                    # 轉字串 -> 去空白 -> 去掉可能出現的浮點數 .0 (例如 123.0 變成 123)
                    db_pass_clean = str(db_pass_raw).strip().replace(".0", "")

                    # 4. 最終比對
                    if db_pass_clean == clean_pwd_input:
                        st.session_state.logged_in = True
                        st.session_state.username = clean_user_input
                        st.session_state.real_name = match.iloc[0]['Name']
                        st.success("登入成功！")
                        st.rerun()
                    else:
                        st.error("密碼錯誤")
                        # 除錯用 (如果還是失敗，可以把下面這行註解打開看原因)
                        # st.write(f"系統讀到的密碼: {db_pass_clean}, 您輸入的: {clean_pwd_input}")
                else:
                    st.error("找不到此帳號")
        return False
    
    return True

# ==========================================
# 2. 主程式 (登入後才會執行)
# ==========================================
def main_app():
    user = st.session_state.username
    real_name = st.session_state.real_name
    
    st.sidebar.write(f"👋 歡迎, {real_name}")
    
    if st.sidebar.button("登出"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

    # --- 新增紀錄區塊 ---
    with st.sidebar.form("add_data"):
        st.header("📝 新增抄表紀錄")
        date_in = st.date_input("日期", datetime.now())
        time_in = st.time_input("時間", datetime.now())
        val = st.number_input("度數", min_value=0.0, format="%.3f")
        
        if st.form_submit_button("提交"):
            try:
                # 讀取 logs
                logs_df = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
            except:
                # 如果 logs 表是空的，初始化一個
                logs_df = pd.DataFrame(columns=['Timestamp', 'Username', 'Reading', 'Note'])
            
            # 準備新資料
            new_row = pd.DataFrame({
                'Timestamp': [datetime.combine(date_in, time_in).strftime("%Y-%m-%d %H:%M:%S")],
                'Username': [user],
                'Reading': [val],
                'Note': ["App"]
            })
            
            # 寫入 Google Sheet
            updated_df = pd.concat([logs_df, new_row], ignore_index=True)
            conn.update(spreadsheet=SHEET_URL, worksheet="logs", data=updated_df)
            
            st.success("紀錄已儲存！")
            st.rerun()

    # --- 儀表板區塊 ---
    st.title("🔥 天然氣用量儀表板")
    
    try:
        # 讀取數據顯示
        df = conn.read(spreadsheet=SHEET_URL, worksheet="logs", ttl=0)
        
        # 過濾出當前用戶的資料
        user_df = df[df['Username'].astype(str).str.strip() == str(user).strip()]
        
        if not user_df.empty:
            # 簡單整理一下顯示格式
            st.dataframe(user_df.sort_values(by='Timestamp', ascending=False), use_container_width=True)
        else:
            st.info("目前尚無抄表紀錄")
            
    except Exception as e:
        st.error(f"讀取紀錄失敗: {e}")

# ==========================================
# 3. 程式入口
# ==========================================
if __name__ == "__main__":
    if login_system():
        main_app()
