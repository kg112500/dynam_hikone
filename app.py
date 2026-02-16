import streamlit as st
import pandas as pd
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from datetime import timedelta

# --- ★設定: ユーザー指定のURL ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv"
MAPPING_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv&gid=1849745164"

# --- ページ設定 (スマホ対応: width設定など調整) ---
st.set_page_config(page_title="ダイナム彦根分析ツール", layout="wide", initial_sidebar_state="expanded")

# スマホで見やすくするためのCSS調整
st.markdown("""
    <style>
    /* スマホでの余白調整 */
    .block-container {
        padding-top: 1rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
    }
    /* タブの文字サイズを少し大きく */
    button[data-baseweb="tab"] {
        font-size: 14px !important; 
        padding: 0 10px !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎰 ダイナム彦根分析ツール (Pro版)")

# --- 1. データ読み込み ---
@st.cache_data(ttl=600)
def load_data(mapping_text_override=None):
    df = None
    if SHEET_URL:
        try:
            df = pd.read_csv(SHEET_URL)
        except Exception: pass
    
    if df is None:
        try:
            df = pd.read_csv("dynam_hikone_complete.csv")
        except FileNotFoundError: return None

    # 列名の正規化
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
                if found:
                    df.rename(columns={found: std}, inplace=True)
                    break

    # 機種名の書き換え処理 (優先順位: 手動入力 > URL)
    rename_dict = {}
    
    # 1. URLからのマッピング
    if MAPPING_URL and "機種" in df.columns:
        try:
            map_df = pd.read_csv(MAPPING_URL, header=None)
            if map_df.shape[1] >= 2:
                rename_dict.update(dict(zip(map_df.iloc[:, 0], map_df.iloc[:, 1])))
        except: pass
    
    # 2. 手動入力（サイドバー）からのマッピング上書き
    if mapping_text_override:
        try:
            for line in mapping_text_override.split('\n'):
                parts = line.split(',')
                if len(parts) >= 2:
                    k, v = parts[0].strip(), parts[1].strip()
                    if k and v:
                        rename_dict[k] = v
        except: pass

    if "機種" in df.columns and rename_dict:
        df["機種"] = df["機種"].replace(rename_dict)

    # 数値化処理
    numeric_cols = ["台番号", "総差枚", "G数"]
    for col in df.columns:
        if any(t in col for t in numeric_cols):
            try:
                df[col] = df[col].astype(str).str.replace(",", "").str.replace("+", "").str.replace(" ", "")
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            except: pass

    if "日付" not in df.columns or "総差枚" not in df.columns:
        return None

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

# --- サイドバー構成 ---
st.sidebar.header("🎯 設定 & フィルター")

# 【改修点2】機種名変換リストの簡易更新
with st.sidebar.expander("🛠️ 機種名の手動補正"):
    st.caption("変換したい名前を「元の名前,新しい名前」の形式で入力してください（改行で複数可）。URLのリストより優先されます。")
    mapping_override = st.text_area("変換リスト入力", height=100, placeholder="L北斗の拳,北斗\nSアイムジャグラー,アイム")

# データ読み込み実行
df = load_data(mapping_override)

if df is None:
    st.error(f"データを読み込めませんでした。")
    st.stop()

# --- 最新機種マスター作成 ---
latest_machine_map = {}
if "台番号" in df.columns and "機種" in df.columns:
    try:
        temp_df = df.copy()
        temp_df["台番号"] = temp_df["台番号"].astype(int)
        latest_indices = temp_df.groupby("台番号")["日付"].idxmax()
        latest_machine_map = temp_df.loc[latest_indices].set_index("台番号")["機種"].to_dict()
    except: pass

# --- サイドバー続き ---
if st.sidebar.button("🔄 データを最新に更新"):
    st.cache_data.clear()
    st.rerun()

min_d, max_d = df["日付"].min(), df["日付"].max()
dates = st.sidebar.date_input("分析期間", [min_d, max_d])
if len(dates) == 2:
    df = df[(df["日付"].dt.date >= dates[0]) & (df["日付"].dt.date <= dates[1])]

st.sidebar.markdown("---")
st.sidebar.subheader("📅 日付条件")

target_ends = st.sidebar.multiselect("末尾 (0-9)", options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], default=[])
use_zorome = st.sidebar.checkbox("ゾロ目の日", value=False)

mask = pd.Series([False] * len(df), index=df.index)
if target_ends: mask = mask | df["末尾"].isin(target_ends)
if use_zorome: mask = mask | df["is_Zorome"]

# フィルター適用 (未選択時は全データ)
if not target_ends and not use_zorome:
    target_df = df.copy()
    filter_mode = "ALL"
else:
    target_df = df[mask].copy()
    filter_mode = "FILTERED"

if target_df.empty:
    st.warning("条件に該当するデータがありません。")
    st.stop()

# --- 共通計算ロジック ---
def calculate_metrics(dataframe, group_cols):
    agg = dataframe.groupby(group_cols).agg(
        サンプル数=("総差枚", "count"),
        勝数=("総差枚", lambda x: (x > 0).sum()),
        総差枚=("総差枚", "sum"),
        総G数=("G数", "sum"),
        平均差枚=("総差枚", "mean"),
        平均G数=("G数", "mean")
    ).reset_index()
    
    agg["勝率"] = (agg["勝数"] / agg["サンプル数"] * 100).round(1)
    agg["機械割"] = agg.apply(
        lambda x: ((x["総G数"]*3 + x["総差枚"]) / (x["総G数"]*3) * 100) if x["総G数"] > 0 else 0, 
        axis=1
    ).round(1)
    
    agg["平均差枚"] = agg["平均差枚"].fillna(0).round(0).astype(int)
    agg["平均G数"] = agg["平均G数"].fillna(0).round(0).astype(int)
    return agg

# --- テーブル表示関数 (スマホ対応調整) ---
def display_filterable_table(df_in, key_id):
    if df_in.empty:
        st.info("データがありません")
        return

    gb = GridOptionsBuilder.from_dataframe(df_in)
    
    # スマホ向け: デフォルトで列幅を自動調整しすぎない
    gb.configure_default_column(
        resizable=True,
        filterable=True,
        sortable=True,
        minWidth=60, # スマホ用に最小幅を確保
    )

    style_diff = JsCode("""function(p){if(p.value>0){return{'color':'blue','fontWeight':'bold'};}if(p.value<0){return{'color':'red'};}return null;}""")
    style_wari = JsCode("""function(p){if(p.value>=105){return{'backgroundColor':'#d4edda','color':'#155724'};}if(p.value>=100){return{'backgroundColor':'#fff3cd'};}return null;}""")

    # 列定義
    if "機種" in df_in.columns: gb.configure_column("機種", minWidth=120, pinned="left") # 機種名は固定
    if "平均差枚" in df_in.columns: gb.configure_column("平均差枚", cellStyle=style_diff)
    if "機械割" in df_in.columns: gb.configure_column("機械割", cellStyle=style_wari)

    grid_options = gb.build()
    
    AgGrid(
        df_in,
        gridOptions=grid_options,
        allow_unsafe_jscode=True,
        height=400,
        theme="ag-theme-alpine", 
        key=f"grid_{key_id}",
        fit_columns_on_grid_load=False # スマホでは横スクロールさせる
    )

title_parts = []
if target_ends: title_parts.append(f"末尾{target_ends}")
if use_zorome: title_parts.append("ゾロ目")
title_str = " & ".join(title_parts) if title_parts else "全期間"

st.markdown(f"### 🎯 分析対象: {title_str}")

# === タブ構成 ===
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "① 末尾・ゾロ", 
    "② ランキング", 
    "③ 機種別", 
    "④ 機種×末尾",
    "⑤ 📈 上げ狙い"  # 【改修点3】新機能
])

# ==========================================
# 1. 末尾・ゾロ目
# ==========================================
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 🅰️ 末尾 (0-9)")
        if "台番号" in target_df.columns:
            matsubi_metrics = calculate_metrics(target_df, ["台末尾"])
            st.plotly_chart(px.bar(matsubi_metrics, x="台末尾", y="平均差枚", 
                             color="機械割", color_continuous_scale="RdYlGn",
                             text="機械割"), use_container_width=True)
            with st.expander("詳細データを見る"):
                display_filterable_table(matsubi_metrics, "tab1_norm")

    with col2:
        st.markdown("##### 🅱️ 台番ゾロ目")
        zorome_df = target_df[target_df["台ゾロ目タイプ"] != "通常"]
        if not zorome_df.empty:
            zorome_metrics = calculate_metrics(zorome_df, ["台ゾロ目タイプ"])
            st.plotly_chart(px.bar(zorome_metrics, x="台ゾロ目タイプ", y="平均差枚", 
                             color="機械割", color_continuous_scale="RdYlGn",
                             text="機械割"), use_container_width=True)
            with st.expander("詳細データを見る"):
                display_filterable_table(zorome_metrics, "tab1_zorome")
        else:
            st.info("該当なし")

# ==========================================
# 2. 鉄板台ランキング
# ==========================================
with tab2:
    st.subheader(f"② {title_str} の優秀台")
    if "台番号" in target_df.columns:
        # スマホ向けにスライダーをExpanderに格納
        with st.expander("⚙️ 絞り込み設定", expanded=False):
            min_sample = st.slider("最低稼働回数", 1, 10, 3, key="tab2_s1")
            min_diff_map = st.number_input("最低平均差枚", value=0, step=100, key="tab2_s2")
            only_active = st.checkbox("現役台のみ", value=True)

        daiban_metrics = calculate_metrics(target_df, ["台番号", "機種"])
        filtered = daiban_metrics[
            (daiban_metrics["サンプル数"] >= min_sample) & 
            (daiban_metrics["平均差枚"] >= min_diff_map)
        ].copy()
        
        if not filtered.empty:
            # 現役判定
            def check_status(row):
                try:
                    t_no = int(row["台番号"])
                    current = latest_machine_map.get(t_no)
                    if current and str(current).strip() == str(row["機種"]).strip(): return "🟢現役"
                    else: return "💀撤去"
                except: return "❓不明"
            
            filtered["設置"] = filtered.apply(check_status, axis=1)
            if only_active: filtered = filtered[filtered["設置"] == "🟢現役"]

            # 散布図
            fig = px.scatter(filtered, x="勝率", y="平均差枚", size="サンプル数", color="機械割", 
                             hover_name="機種", text="台番号", color_continuous_scale="RdYlGn",
                             title="勝率 vs 平均差枚")
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)
            
            # テーブル
            disp_df = filtered[["設置", "台番号", "機種", "機械割", "勝率", "平均差枚", "サンプル数"]]
            display_filterable_table(disp_df, "tab2_ranking")
        else:
            st.warning("条件に合う台がありません")

# ==========================================
# 3. 機種別
# ==========================================
with tab3:
    st.subheader("③ 機種別データ")
    model_metrics = calculate_metrics(target_df, ["機種"])
    model_metrics = model_metrics[model_metrics["サンプル数"] >= 10] # ノイズ除去
    
    if not model_metrics.empty:
        top20 = model_metrics.sort_values("平均差枚", ascending=False).head(20)
        st.plotly_chart(px.bar(top20, x="平均差枚", y="機種", orientation='h', color="勝率", 
                      color_continuous_scale="RdYlGn", text="平均差枚"), use_container_width=True)
        display_filterable_table(model_metrics, "tab3_model")

# ==========================================
# 4. 機種 × 末尾
# ==========================================
with tab4:
    st.subheader("④ 機種 × 末尾ヒートマップ")
    top_models = target_df["機種"].value_counts().head(5).index.tolist()
    sel_models = st.multiselect("機種", sorted(target_df["機種"].unique()), default=top_models)

    if sel_models:
        cross_norm = target_df.groupby(["機種", "台末尾"]).agg(総差枚=("総差枚", "sum"), 総G=("G数", "sum")).reset_index()
        cross_norm["機械割"] = cross_norm.apply(lambda x: ((x["総G"]*3 + x["総差枚"])/(x["総G"]*3)*100) if x["総G"]>0 else 0, axis=1).round(1)
        filt_norm = cross_norm[cross_norm["機種"].isin(sel_models)]
        
        if not filt_norm.empty:
            hm_norm = filt_norm.pivot(index="機種", columns="台末尾", values="機械割").fillna(0)
            st.plotly_chart(px.imshow(hm_norm, aspect="auto", text_auto=True, color_continuous_scale="RdYlGn", zmin=95, zmax=105), use_container_width=True)

# ==========================================
# 5. 上げ狙い分析 (凹み台の翌日) 【新機能】
# ==========================================
with tab5:
    st.header("📈 前日の凹み台 → 翌日の挙動分析")
    st.markdown("""
    <small>
    「前日に大きく負けた台（凹み台）」が、翌日にどうなったかを分析します。<br>
    設定変更（上げ）狙いの傾向を掴むのに役立ちます。
    </small>
    """, unsafe_allow_html=True)

    # パラメータ設定
    c1, c2 = st.columns(2)
    with c1:
        hekomi_threshold = st.number_input("前日の差枚数がこれ以下 (凹み基準)", value=-2000, step=500)
    with c2:
        min_rotation = st.number_input("前日の回転数がこれ以上 (稼働基準)", value=2000, step=500)

    # 分析ロジック
    if st.button("🚀 上げ狙い傾向を分析する"):
        # 全データを日付順、台番号順にソート
        full_df = df.sort_values(["台番号", "日付"])
        
        # 前日のデータをシフトして結合
        full_df["前日差枚"] = full_df.groupby("台番号")["総差枚"].shift(1)
        full_df["前日G数"] = full_df.groupby("台番号")["G数"].shift(1)
        
        # 条件抽出: 前日が凹んでいて、しっかり回されていた台の「翌日(当日)」のデータ
        target_rebound = full_df[
            (full_df["前日差枚"] <= hekomi_threshold) & 
            (full_df["前日G数"] >= min_rotation)
        ].copy()
        
        if target_rebound.empty:
            st.warning("条件に該当する「前日の凹み台」の翌日データが見つかりませんでした。")
        else:
            count = len(target_rebound)
            win_count = (target_rebound["総差枚"] > 0).sum()
            win_rate = round(win_count / count * 100, 1)
            avg_diff = int(target_rebound["総差枚"].mean())
            
            # 結果表示
            st.success(f"分析対象: {count} 件")
            
            m1, m2, m3 = st.columns(3)
            m1.metric("翌日の勝率", f"{win_rate}%")
            m2.metric("翌日の平均差枚", f"{avg_diff}枚", delta_color="normal")
            m3.metric("合計差枚", f"{int(target_rebound['総差枚'].sum())}枚")
            
            # 機種別内訳
            st.subheader("機種別の戻り（リバウンド）性能")
            rebound_ranking = calculate_metrics(target_rebound, ["機種"])
            # サンプル数が少ない機種は除外するか、そのまま出すか
            st.plotly_chart(px.bar(rebound_ranking, x="機種", y="平均差枚", color="勝率", 
                                   title="機種別: 凹み翌日の平均差枚", text="勝率",
                                   color_continuous_scale="RdYlGn"), use_container_width=True)
            
            display_filterable_table(rebound_ranking, "tab5_rebound")
            
            # 詳細リスト
            with st.expander("📝 対象データの明細を確認"):
                cols = ["日付", "台番号", "機種", "前日差枚", "総差枚", "G数"]
                display_filterable_table(target_rebound[cols], "tab5_detail")
