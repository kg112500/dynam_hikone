import streamlit as st
import pandas as pd
import numpy as np
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# --- ★設定: ユーザー指定のURL ---
# 1. ホールデータのURL
SHEET_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv"

# 2. 機種名変換リストのURL
MAPPING_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv&gid=1849745164"

# 3. 店舗図面(座標)データのURL
# ★ここに、前回作成してもらった「座標」シートのURLを貼ってください
MAP_COORD_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv&gid=1743237199" 

# --- ページ設定 ---
st.set_page_config(page_title="ダイナム彦根分析ツール", layout="wide")

# CSS設定 (印刷プレビューのような見た目にする)
hide_st_style = """
    <style>
    [data-testid="stDecoration"] {display: none;}
    [data-testid="stToolbar"] {visibility: hidden;}
    footer {visibility: hidden;}
    div[class*="viewerBadge"] {display: none !important;}
    a[href*="streamlit.app"] {display: none !important;}
    [data-testid="collapsedControl"] {visibility: visible !important; display: block !important; z-index: 999999 !important;}
    header[data-testid="stHeader"] {visibility: visible !important; background-color: rgba(255, 255, 255, 1) !important;}
    .block-container {padding-top: 2rem !important; padding-left: 1rem !important; padding-right: 1rem !important;}
    
    /* マップ用のスタイル */
    .map-container {
        display: grid;
        /* 列数と幅はPython側で動的に生成しますが、基本のギャップを設定 */
        gap: 2px; 
        background-color: #f0f2f6;
        padding: 10px;
        overflow-x: auto; /* 横スクロール対応 */
        width: 100%;
    }
    
    .map-cell {
        position: relative;
        border: 1px solid #ccc;
        height: 40px; /* セルの高さ */
        font-size: 10px;
        display: flex;
        align-items: center;
        padding: 0 4px;
        line-height: 1.1;
        overflow: hidden;
    }

    /* 左側の列（Xが奇数）: 右寄せ（島の内側に文字） */
    .cell-odd {
        justify-content: flex-end;
        text-align: right;
        flex-direction: row;
    }
    
    /* 右側の列（Xが偶数）: 左寄せ（島の内側に文字） */
    .cell-even {
        justify-content: flex-start;
        text-align: left;
        flex-direction: row-reverse; /* 番号を端に、名前を内側に */
    }

    .machine-no {
        font-weight: bold;
        font-size: 12px;
        margin: 0 4px;
    }
    
    .machine-name {
        font-size: 9px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        color: #333;
    }

    .map-aisle {
        /* 通路は透明 */
        border: none;
        background: transparent;
    }
    </style>
"""
st.markdown(hide_st_style, unsafe_allow_html=True)

st.title("🎰 ダイナム彦根分析ツール (Pro版)")

# --- データ読み込み関数 ---
@st.cache_data(ttl=600)
def load_data():
    df = None
    if SHEET_URL:
        try: df = pd.read_csv(SHEET_URL)
        except: pass
    if df is None:
        try: df = pd.read_csv("dynam_hikone_complete.csv")
        except: return None

    df.columns = df.columns.str.strip()
    rename_map = {
        "台番号": ["台番", "No.", "No"],
        "機種": ["機種名", "Machine"],
        "総差枚": ["差枚", "差枚数", "Diff"],
        "G数": ["総回転数", "回転数", "Games"],
    }
    for std, aliases in rename_map.items():
        if std not in df.columns:
            for alias in aliases:
                found = next((c for c in df.columns if alias in c), None)
                if found: df.rename(columns={found: std}, inplace=True); break

    if MAPPING_URL and "機種" in df.columns:
        try:
            map_df = pd.read_csv(MAPPING_URL, header=None)
            if map_df.shape[1] >= 2:
                rename_dict = dict(zip(map_df.iloc[:, 0], map_df.iloc[:, 1]))
                df["機種"] = df["機種"].replace(rename_dict)
        except: pass

    numeric_cols = ["台番号", "総差枚", "G数"]
    for col in df.columns:
        if any(t in col for t in numeric_cols):
            try:
                df[col] = df[col].astype(str).str.replace(",", "").str.replace("+", "").str.replace(" ", "")
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            except: pass

    if "日付" not in df.columns or "総差枚" not in df.columns: return None

    df["日付"] = pd.to_datetime(df["日付"])
    df["DayNum"] = df["日付"].dt.day
    df["Month"] = df["日付"].dt.month
    df["末尾"] = df["DayNum"] % 10 
    df["is_Zorome"] = (df["DayNum"].isin([11, 22])) | (df["Month"] == df["DayNum"])
    
    if "台番号" in df.columns:
        df["台末尾"] = df["台番号"] % 10
        def get_machine_zorome(num):
            s = str(num)
            if len(s) >= 2 and s[-1] == s[-2]: return s[-2:]
            return "通常" 
        df["台ゾロ目タイプ"] = df["台番号"].apply(get_machine_zorome)
    else:
        df["台末尾"] = 0
        df["台ゾロ目タイプ"] = "通常"
    return df

@st.cache_data(ttl=3600)
def load_map_coordinates():
    if not MAP_COORD_URL: return None
    try:
        coord_df = pd.read_csv(MAP_COORD_URL)
        coord_df.columns = coord_df.columns.str.strip()
        no_col = next((c for c in coord_df.columns if "台" in c or "No" in c), None)
        x_col = next((c for c in coord_df.columns if "X" in c.upper()), None)
        y_col = next((c for c in coord_df.columns if "Y" in c.upper()), None)
        if no_col and x_col and y_col:
            coord_df = coord_df[[no_col, x_col, y_col]].rename(columns={no_col: "台番号", x_col: "Map_X", y_col: "Map_Y"})
            coord_df["台番号"] = pd.to_numeric(coord_df["台番号"], errors='coerce')
            return coord_df.dropna()
    except: pass
    return None

df = load_data()
map_coords = load_map_coordinates()

if df is None: st.error("データを読み込めませんでした。"); st.stop()

# --- 共通計算ロジック ---
def calculate_metrics(dataframe, group_cols):
    agg = dataframe.groupby(group_cols).agg(
        サンプル数=("総差枚", "count"),
        勝数=("総差枚", lambda x: (x > 0).sum()),
        総差枚=("総差枚", "sum"),
        総G数=("G数", "sum"),
        平均差枚=("総差枚", "mean")
    ).reset_index()
    agg["勝率"] = (agg["勝数"] / agg["サンプル数"] * 100).round(1)
    agg["機械割"] = agg.apply(lambda x: ((x["総G数"]*3 + x["総差枚"]) / (x["総G数"]*3) * 100) if x["総G数"] > 0 else 0, axis=1).round(1)
    agg["平均差枚"] = agg["平均差枚"].fillna(0).round(0).astype(int)
    return agg

# --- サイドバー・フィルター ---
st.sidebar.header("🎯 戦略設定")
if st.sidebar.button("🔄 データを最新に更新"): st.cache_data.clear(); st.rerun()

min_d, max_d = df["日付"].min(), df["日付"].max()
dates = st.sidebar.date_input("分析期間", [min_d, max_d])
if len(dates) == 2: df = df[(df["日付"].dt.date >= dates[0]) & (df["日付"].dt.date <= dates[1])]

st.sidebar.markdown("---")
target_ends = st.sidebar.multiselect("日付の末尾 (0-9)", options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], default=[])
use_zorome = st.sidebar.checkbox("ゾロ目の日を含める", value=False)

mask = pd.Series([False] * len(df), index=df.index)
if target_ends: mask = mask | df["末尾"].isin(target_ends)
if use_zorome: mask = mask | df["is_Zorome"]
target_df = df[mask].copy() if (target_ends or use_zorome) else df.copy()

if target_df.empty: st.warning("データなし"); st.stop()

# タイトル作成
title_str = " & ".join(([f"末尾{target_ends}"] if target_ends else []) + (["ゾロ目"] if use_zorome else [])) or "全期間"
st.markdown(f"### 🎯 分析対象: {title_str}")

# --- テーブル表示関数 ---
def display_filterable_table(df_in, key_id):
    gb = GridOptionsBuilder.from_dataframe(df_in)
    gb.configure_default_column(resizable=True, filterable=True, sortable=True, minWidth=40)
    style_machine_wari = JsCode("""function(p){if(p.value>=105){return{'color':'white','backgroundColor':'#006400'};}if(p.value>=100){return{'backgroundColor':'#90EE90'};}return null;}""")
    style_diff = JsCode("""function(p){if(p.value>0){return{'color':'blue','fontWeight':'bold'};}if(p.value<0){return{'color':'red'};}return null;}""")
    gb.configure_column("機械割", cellStyle=style_machine_wari)
    gb.configure_column("平均差枚", cellStyle=style_diff)
    AgGrid(df_in, gridOptions=gb.build(), allow_unsafe_jscode=True, height=300, theme="ag-theme-alpine", key=f"grid_{key_id}")

# === タブ構成 ===
tab1, tab2, tab5 = st.tabs(["① データ分析", "② 鉄板台ランキング", "③ 🗺️ 店舗マップ(図面)"])

# ----------------------------------------
# 3. 店舗マップ分析 (HTMLグリッド版)
# ----------------------------------------
with tab5:
    if map_coords is None:
        st.warning("⚠️ 座標データURLが設定されていません。コード内の `MAP_COORD_URL` を確認してください。")
    else:
        # 1. データの準備
        metrics_df = calculate_metrics(target_df, ["台番号", "機種"])
        # 座標と結合 (Left Joinして、データがない台も座標があれば表示できるようにする)
        merged_map = pd.merge(map_coords, metrics_df, on="台番号", how="left")
        
        # 2. マップ描画設定
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            color_mode = st.radio("色分け", ["平均差枚", "勝率", "機械割"], horizontal=True)
        with c2:
            show_machine_name = st.checkbox("機種名を表示", value=True)
        
        # 3. グリッドのサイズ計算
        max_x = int(merged_map["Map_X"].max())
        max_y = int(merged_map["Map_Y"].max())
        
        # 4. ヒートマップ色の計算関数
        def get_color(row, mode):
            if pd.isna(row["サンプル数"]): return "#ffffff" # データなしは白
            
            val = row[mode]
            if mode == "平均差枚":
                if val >= 1000: return "#ff9999" # 大勝 (赤)
                if val >= 200: return "#ffcccc"  # 勝 (薄赤)
                if val <= -500: return "#9999ff" # 負 (青)
                if val < 0: return "#ccccff"     # 微負 (薄青)
                return "#ffffff"
            elif mode == "勝率":
                if val >= 50: return "#ff9999"
                if val >= 40: return "#ffcccc"
                return "#ccccff"
            elif mode == "機械割":
                if val >= 105: return "#ff9999"
                if val >= 100: return "#ffcccc"
                return "#ccccff"
            return "#ffffff"

        # 5. HTML生成
        # グリッドの定義
        html = f'<div class="map-container" style="grid-template-columns: repeat({max_x}, 1fr);">'
        
        # マトリックスを作成して高速アクセス
        grid_data = {}
        for _, row in merged_map.iterrows():
            grid_data[(int(row["Map_X"]), int(row["Map_Y"]))] = row

        # Y行 X列 でループ
        for y in range(1, max_y + 1):
            for x in range(1, max_x + 1):
                cell_data = grid_data.get((x, y))
                
                if cell_data is None:
                    # データがない場所 = 通路
                    html += '<div class="map-cell map-aisle"></div>'
                else:
                    # データがある場所 = 台
                    bg_color = get_color(cell_data, color_mode)
                    
                    # 機種名の処理 (ご要望: 内側に表示)
                    # 奇数列(1,4...)は右寄せ(内側)、偶数列(2,5...)は左寄せ(内側)
                    # CSSクラスで cell-odd / cell-even を切り替え
                    css_class = "cell-odd" if x % 2 != 0 else "cell-even"
                    
                    m_no = int(cell_data["台番号"])
                    m_name = str(cell_data["機種"]) if pd.notna(cell_data["機種"]) and show_machine_name else ""
                    m_val = ""
                    if pd.notna(cell_data["平均差枚"]):
                        if color_mode == "平均差枚": m_val = f"{int(cell_data['平均差枚'])}"
                        elif color_mode == "勝率": m_val = f"{cell_data['勝率']}%"
                    
                    # 表示内容: 番号は常に、名前と数値はオプション
                    # 名前を短縮 (長すぎると崩れるため)
                    short_name = m_name[:5] 
                    
                    # ツールチップ用テキスト
                    tooltip = f"No.{m_no} {m_name}\n差枚:{cell_data.get('平均差枚',0)} 勝率:{cell_data.get('勝率',0)}%"

                    html += f"""
                    <div class="map-cell {css_class}" style="background-color: {bg_color};" title="{tooltip}">
                        <div class="machine-name">{short_name}<br>{m_val}</div>
                        <div class="machine-no">{m_no}</div>
                    </div>
                    """
        
        html += '</div>'
        
        # 6. Streamlitに表示
        st.markdown(html, unsafe_allow_html=True)
        
        # 凡例
        st.caption("🟥 赤: プラス差枚 / 🟦 青: マイナス差枚 / ⬜ 白: 稼働なし or プラマイゼロ")
