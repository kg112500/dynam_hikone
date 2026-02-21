import streamlit as st
import pandas as pd
import plotly.express as px
from st_aggrid import AgGrid, GridOptionsBuilder, JsCode
from datetime import datetime, timedelta

# --- ★設定: ユーザー指定のURL ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1SEDGQLHGRN0rnXgLvP7wNzUuch6oxs9W4AvsavTagKM/export?format=csv"
MAPPING_URL = "https://docs.google.com/spreadsheets/d/1SEDGQLHGRN0rnXgLvP7wNzUuch6oxs9W4AvsavTagKM/export?format=csv&gid=59321871"

# --- ページ設定 ---
st.set_page_config(page_title="ダイナム彦根分析ツール", layout="wide")
st.markdown(f"<div style='font-size: 16px; font-weight: bold; margin-top: 15px; margin-bottom: 10px;'>🎯 分析対象: {title_str}</div>", unsafe_allow_html=True)

# --- 1. データ読み込み ---
@st.cache_data(ttl=600)
def load_data():
    df = None
    if SHEET_URL:
        try:
            df = pd.read_csv(SHEET_URL)
        except Exception: pass
    
    if df is None:
        try:
            df = pd.read_csv("dynam_hikone_complete.csv")
        except FileNotFoundError: return None

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
    
    # ゾロ目判定 (11/1なども含む)
    def check_is_zorome(row):
        d = row["DayNum"]
        m = row["Month"]
        if d in [11, 22]: return True
        if m == d: return True
        s = str(m) + str(d)
        if len(set(s)) == 1: return True
        return False

    df["is_Zorome"] = df.apply(check_is_zorome, axis=1)
    
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
    except: pass

# --- テーブル表示関数 (幅指定: 機種100, 他60) ---
def display_filterable_table(df_in, key_id):
    if df_in.empty:
        st.info("データがありません")
        return

    # === ① フィルター操作エリア ===
    with st.expander("🔍 **絞り込み条件を開く**", expanded=False):
        c1, c2 = st.columns(2)
        df_filtered = df_in.copy()
        if "機種" in df_filtered.columns:
            all_machines = sorted(df_filtered["機種"].astype(str).unique())
            with c1:
                selected_machines = st.multiselect("機種", all_machines, key=f"filter_machine_{key_id}", placeholder="全機種")
            if selected_machines:
                df_filtered = df_filtered[df_filtered["機種"].isin(selected_machines)]

        if "平均差枚" in df_filtered.columns:
            with c2:
                min_diff = st.number_input("平均差枚以上", value=0, step=100, key=f"filter_diff_{key_id}")
            df_filtered = df_filtered[df_filtered["平均差枚"] >= min_diff]

        if "勝率" in df_filtered.columns:
            with c2:
                min_win = st.slider("勝率以上(%)", 0, 100, 0, key=f"filter_win_{key_id}")
            df_filtered = df_filtered[df_filtered["勝率"] >= min_win]

    # === ② 結果表示エリア ===
    st.markdown(f"<small>抽出件数: {len(df_filtered)} 件</small>", unsafe_allow_html=True)

    gb = GridOptionsBuilder.from_dataframe(df_filtered)
    
    # ★変更: 全ての列の基本幅を「60px」に設定
    gb.configure_default_column(resizable=True, filterable=True, sortable=True, width=60, minWidth=40)

    # --- Javascriptフォーマット定義 ---
    fmt_comma = JsCode("""function(p){ return (p.value !== null && p.value !== undefined) ? p.value.toLocaleString() : ''; }""")
    fmt_percent = JsCode("""function(p){ return (p.value !== null && p.value !== undefined) ? Number(p.value).toFixed(1) + '%' : ''; }""")
    style_machine_wari = JsCode("""function(p){if(p.value>=105){return{'color':'white','backgroundColor':'#006400'};}if(p.value>=100){return{'backgroundColor':'#90EE90'};}return null;}""")
    style_diff = JsCode("""function(p){if(p.value>0){return{'color':'blue','fontWeight':'bold'};}if(p.value<0){return{'color':'red'};}return null;}""")
    style_status = JsCode("""function(p){if(p.value==='💀撤去'){return{'color':'gray'};}return{'fontWeight':'bold'};}""")

    # --- 列ごとの設定 ---
    
    # 1. 機種名 -> 幅100px (ここだけ上書き)
    if "機種" in df_filtered.columns: 
        gb.configure_column("機種", width=100)

    # 2. パーセント系 (勝率, 機械割) -> 幅60px
    percent_cols = ["勝率", "機械割"]
    for col in percent_cols:
        if col in df_filtered.columns:
            c_style = style_machine_wari if col == "機械割" else None
            gb.configure_column(
                col, 
                valueFormatter=fmt_percent, 
                cellStyle=c_style, 
                type=["numericColumn"], 
                width=60 # 明示的に60
            )

    # 3. 数値系 (差枚, G数, 台番) -> 幅60px
    comma_cols = ["平均差枚", "総差枚", "平均G数", "総G数", "サンプル数", "前日差枚", "前日G数", "台番号", "台末尾"]
    for col in comma_cols:
        if col in df_filtered.columns:
            c_style = style_diff if "差枚" in col else None
            gb.configure_column(
                col, 
                valueFormatter=fmt_comma, 
                cellStyle=c_style, 
                type=["numericColumn"], 
                width=60 # 明示的に60
            )
            
    # 4. ゾロ目タイプ -> 幅60px
    if "台ゾロ目タイプ" in df_filtered.columns:
        gb.configure_column("台ゾロ目タイプ", width=60)

    # 5. 設置状態 -> 幅60px
    if "設置" in df_filtered.columns: 
        gb.configure_column("設置", width=60, cellStyle=style_status)

    grid_options = gb.build()
    
    AgGrid(
        df_filtered,
        gridOptions=grid_options,
        allow_unsafe_jscode=True,
        height=400,
        theme="ag-theme-alpine", 
        key=f"grid_{key_id}",
        # ★重要: Falseにして、指定した「100px / 60px」を厳密に守らせる
        fit_columns_on_grid_load=False 
    )

# --- サイドバー (日付ボタン改修版) ---
st.sidebar.header("🎯 戦略設定")

# データ内の最小日・最大日・今日
min_d_data = df["日付"].min().date()
max_d_data = df["日付"].max().date()
today = datetime.now().date()

# 日付入力用のセッション状態を初期化
if "range_input" not in st.session_state:
    st.session_state["range_input"] = [min_d_data, max_d_data]

# 期間セット用関数 (ボタンを押したらこれを呼ぶ)
def apply_range(days=None):
    if days is None: # 全期間
        new_range = [min_d_data, max_d_data]
    else:
        # 過去N日 (データ範囲内に収める)
        start = max(today - timedelta(days=days), min_d_data)
        end = min(today, max_d_data)
        new_range = [start, end]
    
    # 状態を更新して再実行(rerun)させることで確実に反映
    st.session_state["range_input"] = new_range
    st.rerun()

st.sidebar.markdown("📅 **期間ショートカット**")
# ボタンのレイアウト (2段構成)
col_b1, col_b2 = st.sidebar.columns(2)
if col_b1.button("全期間"): apply_range(None)
if col_b2.button("過去14日"): apply_range(14)

col_b3, col_b4, col_b5 = st.sidebar.columns(3)
if col_b3.button("過去30日"): apply_range(30)
if col_b4.button("過去60日"): apply_range(60)
if col_b5.button("過去90日"): apply_range(90)

# --- カレンダー入力 (スマホ対策の余白あり) ---
st.sidebar.markdown("<br>", unsafe_allow_html=True) 

dates = st.sidebar.date_input(
    "分析期間を指定",
    # value=st.session_state["range_input"], ← この行を丸ごと消すだけ
    min_value=min_d_data,
    max_value=max_d_data,
    format="YYYY/MM/DD",
    key="range_input" # ✅ keyがあるだけで自動で値が連動します
)

# 期間フィルター適用
if len(dates) == 2:
    start_date, end_date = dates
    df = df[(df["日付"].dt.date >= start_date) & (df["日付"].dt.date <= end_date)]
elif len(dates) == 1:
    start_date = dates[0]
    df = df[df["日付"].dt.date == start_date]

# --- その他のサイドバー設定 ---
st.sidebar.markdown("---")
if st.sidebar.checkbox("📋 元の機種名一覧を表示"):
    if "機種" in df.columns:
        raw_machines = sorted(df["機種"].unique())
        st.sidebar.text_area("全機種名リスト", "\n".join(map(str, raw_machines)), height=200)

if st.sidebar.button("🔄 データを最新に更新"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("📅 日付・条件フィルター")

target_ends = st.sidebar.multiselect("① 日付の末尾 (0-9)", options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], default=[])
use_zorome = st.sidebar.checkbox("② ゾロ目の日を含める (11/1等も含む)", value=False)

mask = pd.Series([False] * len(df), index=df.index)
if target_ends: mask = mask | df["末尾"].isin(target_ends)
if use_zorome: mask = mask | df["is_Zorome"]

if not target_ends and not use_zorome:
    target_df = df.copy()
else:
    target_df = df[mask].copy()

if target_df.empty:
    st.warning("条件に該当するデータがありません。")
    st.stop()

# --- 共通計算ロジック (G数0除外) ---
def calculate_metrics(dataframe, group_cols):
    dataframe = dataframe[dataframe["G数"] > 0] # 稼働なしを除外

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

title_parts = []
if target_ends: title_parts.append(f"末尾{target_ends}")
if use_zorome: title_parts.append("ゾロ目")
title_str = " & ".join(title_parts) if title_parts else "全期間"

st.markdown(f"### 🎯 分析対象: {title_str}")

# === タブ構成 ===
tab1, tab2, tab3, tab4 = st.tabs([
    "① 末尾・台番ゾロ目", 
    "② 鉄板台ランキング", 
    "③ 機種別", 
    "④ 機種×末尾・ゾロ目"
])

# ==========================================
# 1. 末尾・台番ゾロ目
# ==========================================
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🅰️ 通常の「台末尾 (0-9)」")
        if "台番号" in target_df.columns:
            matsubi_metrics = calculate_metrics(target_df, ["台末尾"])
            fig1 = px.bar(matsubi_metrics, x="台末尾", y="平均差枚", 
                          color="機械割", color_continuous_scale="RdYlGn",
                          text="機械割", title="末尾 (0-9) の平均差枚")
            fig1.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig1.update_yaxes(tickformat=",")
            fig1.update_layout(xaxis=dict(tickmode='linear', dtick=1))
            st.plotly_chart(fig1, use_container_width=True)
            display_filterable_table(
                matsubi_metrics[["台末尾", "勝率", "平均差枚", "平均G数", "機械割", "サンプル数"]],
                key_id="tab1_norm"
            )

    with col2:
        st.subheader("🅱️ 「台番ゾロ目」")
        zorome_df = target_df[target_df["台ゾロ目タイプ"] != "通常"]
        if zorome_df.empty:
            st.info("データなし")
        else:
            zorome_metrics = calculate_metrics(zorome_df, ["台ゾロ目タイプ"])
            fig2 = px.bar(zorome_metrics, x="台ゾロ目タイプ", y="平均差枚", 
                          color="機械割", color_continuous_scale="RdYlGn",
                          text="機械割", title="台番ゾロ目 (11〜00) の平均差枚")
            fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig2.update_yaxes(tickformat=",")
            st.plotly_chart(fig2, use_container_width=True)
            display_filterable_table(
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
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1: min_sample = st.slider("最低稼働回数", 1, 10, 1, key="tab2_s1")
        with c2: min_diff_map = st.slider("最低平均差枚", -1000, 2000, 0, step=100, key="tab2_s2")
        with c3:
            st.write(""); st.write("")
            only_active = st.checkbox("🟢 現役台のみ表示", value=True)

        daiban_metrics = calculate_metrics(target_df, ["台番号", "機種"])
        filtered = daiban_metrics[
            (daiban_metrics["サンプル数"] >= min_sample) & 
            (daiban_metrics["平均差枚"] >= min_diff_map)
        ].copy()
        
        if filtered.empty:
            st.warning("条件に合うデータがありません。")
        else:
            def check_status(row):
                try:
                    t_no = int(row["台番号"])
                    current = latest_machine_map.get(t_no)
                    if current and str(current).strip() == str(row["機種"]).strip(): return "🟢現役"
                    else: return "💀撤去"
                except: return "❓不明"
            
            filtered["設置"] = filtered.apply(check_status, axis=1)
            if only_active: filtered = filtered[filtered["設置"] == "🟢現役"]

            if filtered.empty:
                 st.warning("条件に合う現役台がありません。")
            else:
                filtered["表示名"] = filtered["設置"] + " " + filtered["台番号"].astype(str) + " (" + filtered["機種"] + ")"
                fig = px.scatter(filtered, x="勝率", y="平均差枚", size="サンプル数", color="機械割", 
                                 hover_name="表示名", text="台番号", color_continuous_scale="RdYlGn",
                                 symbol="設置", title="勝率 vs 平均差枚")
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                fig.add_vline(x=50, line_dash="dash", line_color="gray")
                fig.update_xaxes(tickformat=".1f", title_text="勝率 (%)")
                fig.update_yaxes(tickformat=",", title_text="平均差枚 (枚)")
                fig.update_traces(hovertemplate="<b>%{hovertext}</b><br>勝率: %{x:.1f}%<br>平均差枚: %{y:,}枚<br>機械割: %{marker.color:.1f}%<br>サンプル: %{marker.size}")
                st.plotly_chart(fig, use_container_width=True)
                
                disp_df = filtered[["設置", "台番号", "機種", "機械割", "勝率", "平均差枚", "平均G数", "サンプル数"]].sort_values(["設置", "機械割"], ascending=[True, False])
                # --- ★追加: CSVダウンロードボタン ---
                csv = disp_df.to_csv(index=False, encoding='utf-8-sig') # Excelで文字化けしないよう utf-8-sig を指定
                
                st.download_button(
                    label="📥 ランキングをCSVでダウンロード",
                    data=csv,
                    file_name='teppan_ranking.csv',
                    mime='text/csv',
                    key='download_tab2'
                )
                # -----------------------------------
                display_filterable_table(disp_df, key_id="tab2_ranking")

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
        fig3 = px.bar(model_metrics, x="機械割", y="機種", orientation='h', color="総差枚", 
                      color_continuous_scale="RdYlGn", text="機械割")
        fig3.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        fig3.update_xaxes(tickformat=".1f", title_text="機械割 (%)")
        st.plotly_chart(fig3, use_container_width=True)
        display_filterable_table(
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
            st.markdown("##### 🅰️ 機種 × 通常末尾")
            df_heat = target_df[target_df["G数"] > 0]
            cross_norm = df_heat.groupby(["機種", "台末尾"]).agg(総差枚=("総差枚", "sum"), 総G=("G数", "sum")).reset_index()
            cross_norm["機械割"] = cross_norm.apply(lambda x: ((x["総G"]*3 + x["総差枚"])/(x["総G"]*3)*100) if x["総G"]>0 else 0, axis=1).round(1)
            filt_norm = cross_norm[cross_norm["機種"].isin(sel_models)]
            if not filt_norm.empty:
                hm_norm = filt_norm.pivot(index="機種", columns="台末尾", values="機械割").fillna(0)
                fig4 = px.imshow(hm_norm, labels=dict(x="末尾", y="機種", color="機械割"), 
                                     zmin=90, zmax=110, aspect="auto", text_auto=True, color_continuous_scale="RdYlGn")
                fig4.update_traces(texttemplate="%{z:.1f}%", hovertemplate="機種: %{y}<br>末尾: %{x}<br>機械割: %{z:.1f}%")
                st.plotly_chart(fig4, use_container_width=True)
            else: st.info("データなし")

        with c2:
            st.markdown("##### 🅱️ 機種 × 台番ゾロ目")
            zorome_df_only = df_heat[df_heat["台ゾロ目タイプ"] != "通常"]
            cross_zorome = zorome_df_only.groupby(["機種", "台ゾロ目タイプ"]).agg(総差枚=("総差枚", "sum"), 総G=("G数", "sum")).reset_index()
            cross_zorome["機械割"] = cross_zorome.apply(lambda x: ((x["総G"]*3 + x["総差枚"])/(x["総G"]*3)*100) if x["総G"]>0 else 0, axis=1).round(1)
            filt_zorome = cross_zorome[cross_zorome["機種"].isin(sel_models)]
            if not filt_zorome.empty:
                hm_zorome = filt_zorome.pivot(index="機種", columns="台ゾロ目タイプ", values="機械割").fillna(0)
                fig5 = px.imshow(hm_zorome, labels=dict(x="ゾロ目", y="機種", color="機械割"), 
                                     zmin=90, zmax=110, aspect="auto", text_auto=True, color_continuous_scale="RdYlGn")
                fig5.update_traces(texttemplate="%{z:.1f}%", hovertemplate="機種: %{y}<br>ゾロ目: %{x}<br>機械割: %{z:.1f}%")
                st.plotly_chart(fig5, use_container_width=True)
            else: st.info("ゾロ目データなし")

















