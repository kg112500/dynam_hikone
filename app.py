import streamlit as st
import pandas as pd
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

# --- ★設定: ユーザー指定のURL ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv"

# --- ページ設定 ---
st.set_page_config(page_title="ダイナム彦根分析ツール", layout="wide")
st.title("🎰 ダイナム彦根分析ツール (Excel機能版)")

# --- 1. データ読み込み ---
@st.cache_data(ttl=600)
def load_data():
    df = None
    if SHEET_URL:
        try:
            df = pd.read_csv(SHEET_URL)
        except Exception as e:
            pass
    
    if df is None:
        try:
            df = pd.read_csv("dynam_hikone_complete.csv")
        except FileNotFoundError:
            return None

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

    numeric_cols = ["台番号", "総差枚", "G数"]
    for col in df.columns:
        if any(t in col for t in numeric_cols):
            try:
                df[col] = df[col].astype(str).str.replace(",", "").str.replace("+", "").str.replace(" ", "")
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            except:
                pass

    if "日付" not in df.columns or "総差枚" not in df.columns:
        return None

    df["日付"] = pd.to_datetime(df["日付"])
    df["日付str"] = df["日付"].dt.strftime("%Y-%m-%d")
    df["DayNum"] = df["日付"].dt.day
    df["Month"] = df["日付"].dt.month
    df["末尾"] = df["DayNum"] % 10 
    df["is_Zorome"] = (df["DayNum"].isin([11, 22])) | (df["Month"] == df["DayNum"])
    
    if "台番号" in df.columns:
        df["台末尾"] = df["台番号"] % 10
        def get_machine_zorome(num):
            s = str(num)
            if len(s) >= 2 and s[-1] == s[-2]:
                return s[-2:]
            return "通常" 
        df["台ゾロ目タイプ"] = df["台番号"].apply(get_machine_zorome)
    else:
        df["台末尾"] = 0
        df["台ゾロ目タイプ"] = "通常"

    return df

df = load_data()

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
    except:
        pass

# --- Excel風テーブル表示関数 ---
def display_excel_table(df_in, key_id):
    if df_in.empty:
        st.info("データがありません")
        return

    df_show = df_in.copy()
    
    gb = GridOptionsBuilder.from_dataframe(df_show)
    
    # デフォルト設定
    gb.configure_default_column(
        resizable=True,
        filterable=True,
        sortable=True,
        minWidth=80,
    )
    
    # ★重要: フローティングフィルター（ヘッダー下の検索窓）をON
    gb.configure_grid_options(enableFloatingFilter=True)

    # --- 条件付き書式 (JSコード) ---
    style_machine_wari = JsCode("""
    function(params) {
        if (params.value >= 105) { return {'color': 'white', 'backgroundColor': '#006400'}; }
        if (params.value >= 100) { return {'backgroundColor': '#90EE90'}; }
        return null;
    }
    """)

    style_diff = JsCode("""
    function(params) {
        if (params.value > 0) { return {'color': 'blue', 'fontWeight': 'bold'}; }
        if (params.value < 0) { return {'color': 'red'}; }
        return null;
    }
    """)

    style_status = JsCode("""
    function(params) {
        if (params.value === '💀撤去') { return {'color': 'gray'}; }
        return {'fontWeight': 'bold'};
    }
    """)

    # --- 列ごとの個別設定 ---
    if "設置" in df_show.columns:
        gb.configure_column("設置", pinned="left", width=90, cellStyle=style_status)

    if "機種" in df_show.columns:
        gb.configure_column("機種", minWidth=150)

    if "勝率" in df_show.columns:
        gb.configure_column("勝率", type=["numericColumn"], precision=1, 
                            valueFormatter="x + '%'")

    if "機械割" in df_show.columns:
        gb.configure_column("機械割", type=["numericColumn"], precision=1, 
                            valueFormatter="x + '%'", cellStyle=style_machine_wari)

    if "平均差枚" in df_show.columns:
        gb.configure_column("平均差枚", type=["numericColumn"], 
                            valueFormatter="x.toLocaleString()", cellStyle=style_diff)

    for col in ["総差枚", "平均G数", "総G数", "サンプル数", "台番号"]:
        if col in df_show.columns:
            gb.configure_column(col, type=["numericColumn"], 
                                valueFormatter="x.toLocaleString()")

    grid_options = gb.build()

    # ★スマホ用CSS調整: メニューアイコン(≡)を常に強制表示させる
    custom_css = {
        ".ag-header-cell-menu-button": {
            "display": "block !important",
            "opacity": "1 !important"
        }
    }

    st.markdown("👇 **「≡」でメニュー、「下の枠」で直接検索できます**")
    AgGrid(
        df_show,
        gridOptions=grid_options,
        allow_unsafe_jscode=True,
        enable_enterprise_modules=False,
        height=400,
        fit_columns_on_grid_load=False,
        theme="ag-theme-alpine", # ★Excelっぽいテーマを明示的に指定
        custom_css=custom_css,   # ★CSSを注入
        key=key_id
    )


# --- サイドバー ---
st.sidebar.header("🎯 戦略設定")

if st.sidebar.button("🔄 データを最新に更新"):
    st.cache_data.clear()
    st.rerun()

min_d, max_d = df["日付"].min(), df["日付"].max()
dates = st.sidebar.date_input("分析期間", [min_d, max_d])
if len(dates) == 2:
    df = df[(df["日付"].dt.date >= dates[0]) & (df["日付"].dt.date <= dates[1])]

st.sidebar.markdown("---")
st.sidebar.subheader("📅 分析対象の日付を選択")

target_ends = st.sidebar.multiselect("① 日付の末尾 (0-9)", options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], default=[])
use_zorome = st.sidebar.checkbox("② ゾロ目の日を含める", value=False)

mask = pd.Series([False] * len(df), index=df.index)
if target_ends: mask = mask | df["末尾"].isin(target_ends)
if use_zorome: mask = mask | df["is_Zorome"]

if not target_ends and not use_zorome:
    st.sidebar.warning("末尾またはゾロ目を選択してください。現在は全データを表示中。")
    target_df = df.copy()
else:
    target_df = df[mask].copy()

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
    
    # ★平均値を整数化 (小数点なし)
    agg["平均差枚"] = agg["平均差枚"].fillna(0).round(0).astype(int)
    agg["平均G数"] = agg["平均G数"].fillna(0).round(0).astype(int)
    
    return agg

title_parts = []
if target_ends: title_parts.append(f"末尾{target_ends}")
if use_zorome: title_parts.append("ゾロ目")
title_str = " & ".join(title_parts) if title_parts else "全期間"

st.markdown(f"### 🎯 分析対象: {title_str}")
st.caption(f"抽出データ: {len(target_df)} 件")

# === タブ構成 ===
tab1, tab2, tab3, tab4 = st.tabs([
    "① 末尾・台番ゾロ目", 
    "② 鉄板台ランキング", 
    "③ 機種別", 
    "④ 機種×末尾・ゾロ目"
])

# ==========================================
# 1. 特定日 × 台の末尾 & 台番ゾロ目
# ==========================================
with tab1:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🅰️ 通常の「台末尾 (0-9)」")
        if "台番号" in target_df.columns:
            matsubi_metrics = calculate_metrics(target_df, ["台末尾"])
            fig = px.bar(matsubi_metrics, x="台末尾", y="平均差枚", 
                         color="機械割", color_continuous_scale="RdYlGn",
                         text="機械割", title="末尾 (0-9) の平均差枚")
            st.plotly_chart(fig, use_container_width=True)
            
            display_excel_table(
                matsubi_metrics[["台末尾", "勝率", "平均差枚", "平均G数", "機械割", "サンプル数"]],
                key_id="tab1_norm"
            )

    with col2:
        st.subheader("🅱️ 「台番ゾロ目 (11, 22...)」")
        zorome_df = target_df[target_df["台ゾロ目タイプ"] != "通常"]
        if zorome_df.empty:
            st.info("データなし")
        else:
            zorome_metrics = calculate_metrics(zorome_df, ["台ゾロ目タイプ"])
            fig2 = px.bar(zorome_metrics, x="台ゾロ目タイプ", y="平均差枚", 
                         color="機械割", color_continuous_scale="RdYlGn",
                         text="機械割", title="台番ゾロ目 (11〜00) の平均差枚")
            st.plotly_chart(fig2, use_container_width=True)
            
            display_excel_table(
                zorome_metrics[["台ゾロ目タイプ", "勝率", "平均差枚", "平均G数", "機械割", "サンプル数"]],
                key_id="tab1_zorome"
            )

# ==========================================
# 2. 鉄板台ランキング
# ==========================================
with tab2:
    st.subheader(f"② {title_str} の鉄板台ランキング")
    if "台番号" not in target_df.columns:
        st.error("台番号なし")
    else:
        min_sample = st.slider("最低稼働回数", 1, 10, 1, key="tab2_slider")
        daiban_metrics = calculate_metrics(target_df, ["台番号", "機種"])
        filtered = daiban_metrics[daiban_metrics["サンプル数"] >= min_sample].copy()
        
        if filtered.empty:
            st.warning("データなし")
        else:
            def check_status(row):
                try:
                    t_no = int(row["台番号"])
                    current = latest_machine_map.get(t_no)
                    if current and str(current).strip() == str(row["機種"]).strip():
                        return "🟢現役"
                    else:
                        return "💀撤去"
                except:
                    return "❓不明"
            
            filtered["設置"] = filtered.apply(check_status, axis=1)
            filtered["表示名"] = filtered["設置"] + " " + filtered["台番号"].astype(str) + " (" + filtered["機種"] + ")"
            
            fig = px.scatter(filtered, x="勝率", y="平均差枚", size="サンプル数", color="機械割", 
                             hover_name="表示名", text="台番号", color_continuous_scale="RdYlGn",
                             symbol="設置",
                             title="勝率 vs 平均差枚 (🟢=現役 / 💀=撤去)")
            fig.add_hline(y=0, line_dash="dash"); fig.add_vline(x=50, line_dash="dash")
            st.plotly_chart(fig, use_container_width=True)
            
            disp_df = filtered[["設置", "台番号", "機種", "機械割", "勝率", "平均差枚", "平均G数", "サンプル数"]].sort_values(["設置", "機械割"], ascending=[True, False])
            
            display_excel_table(disp_df, key_id="tab2_ranking")

# ==========================================
# 3. 機種別
# ==========================================
with tab3:
    st.subheader("③ 機種別ランキング")
    model_metrics = calculate_metrics(target_df, ["機種"])
    min_model = st.slider("最低稼働台数", 1, 10, 1, key="tab3_slider")
    model_metrics = model_metrics[model_metrics["サンプル数"] >= min_model]
    
    if not model_metrics.empty:
        model_metrics = model_metrics.sort_values("総差枚", ascending=False).head(20)
        fig = px.bar(model_metrics, x="機械割", y="機種", orientation='h', color="総差枚", 
                     color_continuous_scale="RdYlGn", text="機械割")
        fig.add_vline(x=100, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)
        
        display_excel_table(
            model_metrics[["機種", "機械割", "勝率", "平均差枚", "平均G数", "サンプル数"]],
            key_id="tab3_model"
        )

# ==========================================
# 4. 機種 × 末尾
# ==========================================
with tab4:
    st.subheader("④ 機種 × 末尾・ゾロ目 の法則")
    
    top_models = target_df["機種"].value_counts().head(10).index.tolist()
    sel_models = st.multiselect("機種選択", sorted(target_df["機種"].unique()), default=top_models)

    if sel_models:
        c1, c2 = st.columns(2)
        
        with c1:
            st.markdown("##### 🅰️ 機種 × 通常末尾 (0-9)")
            cross_norm = target_df.groupby(["機種", "台末尾"]).agg(総差枚=("総差枚", "sum"), 総G=("G数", "sum")).reset_index()
            cross_norm["機械割"] = cross_norm.apply(lambda x: ((x["総G"]*3 + x["総差枚"])/(x["総G"]*3)*100) if x["総G"]>0 else 0, axis=1).round(1)
            filt_norm = cross_norm[cross_norm["機種"].isin(sel_models)]
            
            if not filt_norm.empty:
                hm_norm = filt_norm.pivot(index="機種", columns="台末尾", values="機械割").fillna(0)
                fig_norm = px.imshow(hm_norm, labels=dict(x="末尾", y="機種", color="機械割"), 
                                     zmin=90, zmax=110, aspect="auto", text_auto=True, color_continuous_scale="RdYlGn")
                st.plotly_chart(fig_norm, use_container_width=True)
            else:
                st.info("データなし")

        with c2:
            st.markdown("##### 🅱️ 機種 × 台番ゾロ目 (11, 22...)")
            zorome_df_only = target_df[target_df["台ゾロ目タイプ"] != "通常"]
            cross_zorome = zorome_df_only.groupby(["機種", "台ゾロ目タイプ"]).agg(総差枚=("総差枚", "sum"), 総G=("G数", "sum")).reset_index()
            cross_zorome["機械割"] = cross_zorome.apply(lambda x: ((x["総G"]*3 + x["総差枚"])/(x["総G"]*3)*100) if x["総G"]>0 else 0, axis=1).round(1)
            filt_zorome = cross_zorome[cross_zorome["機種"].isin(sel_models)]

            if not filt_zorome.empty:
                hm_zorome = filt_zorome.pivot(index="機種", columns="台ゾロ目タイプ", values="機械割").fillna(0)
                fig_zorome = px.imshow(hm_zorome, labels=dict(x="ゾロ目", y="機種", color="機械割"), 
                                       zmin=90, zmax=110, aspect="auto", text_auto=True, color_continuous_scale="RdYlGn")
                st.plotly_chart(fig_zorome, use_container_width=True)
            else:
                st.info("ゾロ目データなし")
