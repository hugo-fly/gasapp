import streamlit as st
import pandas as pd
import os
from datetime import datetime, time
import plotly.graph_objects as go
import io

# ==========================================
# 設定
# ==========================================
CSV_FILE = 'gas_raw_data.csv'

st.set_page_config(page_title="天然氣數據儀表板", layout="wide")

# ==========================================
# 核心邏輯函數 (從原本程式碼改編)
# ==========================================
def load_data():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=['Timestamp', 'Reading'])
    df = pd.read_csv(CSV_FILE)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    return df.sort_values('Timestamp')

def save_data(df):
    df.to_csv(CSV_FILE, index=False)

def process_data(df, freq_hours):
    """處理指定時間間隔的數據"""
    if df.empty: return pd.DataFrame()
    
    df = df.drop_duplicates(subset=['Timestamp'], keep='last')
    df = df.sort_values('Timestamp').set_index('Timestamp')
    
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
        if freq_hours == 12:
            period = "上午" if dt_start.hour < 12 else "下午"
            labels.append(f"{dt_start.strftime('%m/%d')} {period}")
        else:
            labels.append(f"{dt_start.strftime('%m/%d')}")
    df_result['圖表標籤'] = labels
    
    return df_result

def generate_excel_bytes(df_raw, df_12h, df_24h, avg_12h, avg_24h):
    """生成 Excel 檔案並寫入記憶體 (供網頁下載用)"""
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    # 內部函數：建立工作表
    def create_sheet(df, sheet_name, freq, avg_val):
        wb = writer.book
        ws = wb.add_worksheet(sheet_name)
        
        # 格式
        fmt_header = wb.add_format({'bold': True, 'align': 'center', 'bg_color': '#4472C4', 'font_color': 'white', 'border': 1})
        fmt_date = wb.add_format({'num_format': 'mm/dd hh:mm', 'align': 'left'})
        fmt_num = wb.add_format({'num_format': '0.000', 'align': 'right'})
        fmt_usage = wb.add_format({'num_format': '0.00', 'align': 'right', 'bg_color': '#D9E1F2', 'bold': True})
        fmt_label = wb.add_format({'align': 'center', 'font_color': '#555555'})
        fmt_avg = wb.add_format({'num_format': '0.00', 'align': 'right', 'font_color': 'red'})

        headers = [f'標準時間 (每{freq}H)', '推估瓦斯表度數', f'{freq}H 區間用量', '圖表標籤', f'{freq}h平均用量']
        ws.write_row(0, 0, headers, fmt_header)

        for i, row in df.iterrows():
            r = i + 1
            ws.write_datetime(r, 0, row['標準時間'], fmt_date)
            ws.write_number(r, 1, row['推估度數'], fmt_num)
            if pd.notna(row['區間用量']):
                ws.write_number(r, 2, row['區間用量'], fmt_usage)
            else:
                ws.write_number(r, 2, 0, fmt_usage)
            ws.write_string(r, 3, row['圖表標籤'], fmt_label)
            ws.write_number(r, 4, avg_val, fmt_avg)

        ws.set_column('A:A', 20)
        ws.set_column('B:E', 15)

        # 圖表邏輯 (完全保留您原本的設計)
        num_rows = len(df)
        start_row = 2 if num_rows > 1 else 1 # 跳過第一筆0值

        column_chart = wb.add_chart({'type': 'column'})
        column_chart.add_series({
            'name': [sheet_name, 0, 2],
            'categories': [sheet_name, start_row, 3, num_rows, 3],
            'values': [sheet_name, start_row, 2, num_rows, 2],
            'data_labels': {'value': True, 'num_format': '0.00'},
            'fill': {'color': '#5B9BD5'},
        })

        line_chart = wb.add_chart({'type': 'line'})
        # 自訂標籤：只顯示最後一個
        display_len = num_rows - start_row + 1
        custom_labels = [{'delete': True}] * (display_len - 1)
        custom_labels.append({'value': True, 'position': 'right', 'font': {'color': 'red', 'bold': True}, 'num_format': '0.00'})

        line_chart.add_series({
            'name': [sheet_name, 0, 4],
            'categories': [sheet_name, start_row, 3, num_rows, 3],
            'values': [sheet_name, start_row, 4, num_rows, 4],
            'line': {'color': 'red', 'width': 1.5, 'dash_type': 'dash'},
            'data_labels': {'custom': custom_labels},
        })

        column_chart.combine(line_chart)
        column_chart.set_title({'name': f'{freq}小時區間瓦斯用量 (含平均線)'})
        column_chart.set_legend({'position': 'bottom'})
        ws.insert_chart('G2', column_chart)
        
        # 趨勢圖
        chart2 = wb.add_chart({'type': 'line'})
        chart2.add_series({
            'name': [sheet_name, 0, 1],
            'categories': [sheet_name, 1, 3, num_rows, 3],
            'values': [sheet_name, 1, 1, num_rows, 1],
            'line': {'color': '#ED7D31'},
            'marker': {'type': 'circle'}
        })
        chart2.set_title({'name': '瓦斯表推估度數趨勢'})
        ws.insert_chart('G18', chart2)

    create_sheet(df_12h, '12小時用量表', 12, avg_12h)
    create_sheet(df_24h, '24小時用量表', 24, avg_24h)
    
    writer.close()
    processed_data = output.getvalue()
    return processed_data

def plot_web_chart(df, avg_val, title):
    """在網頁上繪製 Plotly 圖表"""
    # 過濾掉第一筆 (通常是 NaN 或 0)
    plot_df = df.iloc[1:].copy()
    
    fig = go.Figure()
    
    # 1. 柱狀圖 (用量)
    fig.add_trace(go.Bar(
        x=plot_df['圖表標籤'],
        y=plot_df['區間用量'],
        name='區間用量',
        marker_color='#5B9BD5',
        text=plot_df['區間用量'].round(2),
        textposition='auto'
    ))
    
    # 2. 平均線 (虛線)
    fig.add_trace(go.Scatter(
        x=plot_df['圖表標籤'],
        y=[avg_val] * len(plot_df),
        name='平均用量',
        line=dict(color='red', width=2, dash='dash'),
        mode='lines+text',
    ))
    
    # 在最後一個點標註平均值
    if not plot_df.empty:
        fig.add_annotation(
            x=plot_df['圖表標籤'].iloc[-1],
            y=avg_val,
            text=f"{avg_val:.2f}",
            showarrow=False,
            yshift=10,
            font=dict(color="red", size=12, weight="bold")
        )

    fig.update_layout(
        title=title,
        yaxis_title="度數",
        xaxis_title="時間區間",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified"
    )
    
    return fig

# ==========================================
# 網頁介面 (UI)
# ==========================================
st.title("🔥 天然氣數據輸入助手")

# --- 側邊欄：數據輸入 ---
with st.sidebar:
    st.header("📝 新增抄表紀錄")
    
    # 日期與時間選擇器
    col1, col2 = st.columns(2)
    with col1:
        input_date = st.date_input("日期", datetime.now())
    with col2:
        input_time = st.time_input("時間", datetime.now())
        
    input_reading = st.number_input("瓦斯表度數", min_value=0.0, format="%.3f", step=0.1)
    
    if st.button("提交紀錄", type="primary"):
        df = load_data()
        input_dt = datetime.combine(input_date, input_time)
        
        # 簡易重複檢查
        if not df.empty and input_dt in df['Timestamp'].values:
            st.error(f"錯誤：{input_dt} 的紀錄已存在！")
        else:
            new_row = pd.DataFrame({'Timestamp': [input_dt], 'Reading': [input_reading]})
            df = pd.concat([df, new_row], ignore_index=True)
            save_data(df)
            st.success(f"已儲存：{input_dt} | {input_reading}")
            st.rerun() # 重新整理頁面

    st.markdown("---")
    st.markdown("### 💾 資料管理")
    
    # 下載原始 CSV
    df_raw = load_data()
    if not df_raw.empty:
        csv = df_raw.to_csv(index=False).encode('utf-8')
        st.download_button("下載原始 CSV", csv, "gas_raw_data.csv", "text/csv")
        
        # 刪除最後一筆功能
        if st.button("刪除最後一筆紀錄"):
            df_raw = df_raw[:-1]
            save_data(df_raw)
            st.warning("已刪除最後一筆紀錄")
            st.rerun()

# --- 主畫面：報表與圖表 ---
df = load_data()

if df.empty:
    st.info("尚無數據，請從左側側邊欄輸入第一筆紀錄。")
else:
    # 計算邏輯
    total_usage = df['Reading'].iloc[-1] - df['Reading'].iloc[0]
    total_hours = (df['Timestamp'].iloc[-1] - df['Timestamp'].iloc[0]).total_seconds() / 3600
    
    avg_usage_12h = total_usage / (total_hours / 12) if total_hours > 0 else 0
    avg_usage_24h = total_usage / (total_hours / 24) if total_hours > 0 else 0
    
    # 顯示統計摘要
    col1, col2, col3 = st.columns(3)
    col1.metric("總監測時數", f"{total_hours:.1f} hr")
    col2.metric("總用量", f"{total_usage:.3f} 度")
    col3.metric("最新讀數", f"{df['Reading'].iloc[-1]:.3f}")

    st.markdown("---")

    # 頁籤切換
    tab1, tab2, tab3 = st.tabs(["📊 12小時分析", "📅 24小時分析", "📋 原始數據"])

    with tab1:
        df_12h = process_data(df, 12)
        if not df_12h.empty:
            st.plotly_chart(plot_web_chart(df_12h, avg_usage_12h, "12小時區間瓦斯用量"), use_container_width=True)
            with st.expander("查看詳細數據表"):
                st.dataframe(df_12h.style.format({"推估度數": "{:.3f}", "區間用量": "{:.2f}"}))
        else:
            st.warning("數據不足以計算 12小時區間。")

    with tab2:
        df_24h = process_data(df, 24)
        if not df_24h.empty:
            st.plotly_chart(plot_web_chart(df_24h, avg_usage_24h, "24小時區間瓦斯用量"), use_container_width=True)
            with st.expander("查看詳細數據表"):
                st.dataframe(df_24h.style.format({"推估度數": "{:.3f}", "區間用量": "{:.2f}"}))
        else:
            st.warning("數據不足以計算 24小時區間。")

    with tab3:
        st.dataframe(df.style.format({"Timestamp": "{:%Y-%m-%d %H:%M}", "Reading": "{:.3f}"}))

    # --- Excel 報表下載 ---
    st.markdown("---")
    st.header("📥 下載 Excel 報表")
    if st.button("生成並下載報表"):
        try:
            excel_data = generate_excel_bytes(df, df_12h, df_24h, avg_usage_12h, avg_usage_24h)
            st.download_button(
                label="點擊下載 Excel 檔案",
                data=excel_data,
                file_name="gas_report_web.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"生成失敗: {e}")