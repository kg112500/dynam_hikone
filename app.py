import streamlit as st
import pandas as pd
import plotly.express as px

# --- ★設定: ユーザー指定のURL ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv"

# --- ページ設定 ---
st.set_page_config(page_title="特定日攻略(現役判別)", layout="wide")
st.title("🎰 特定日攻略・狙い台分析ツール (設置状況判別版)")

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

    # 数値化
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

    # 日付処理
    df["日付"] = pd.to_datetime(df["日付"])
    df["日付str"] = df["日付"].dt.strftime("%Y-%m-%d")
    
    # イベント属性
    df["DayNum"] = df["日付"].dt.day
    df["Month"] = df["日付"].dt.month
    df["末尾"] = df["DayNum"] % 10 
    
    # ゾロ目判定
    df["is_Zorome"] = (df["DayNum"].isin([11, 22])) | (df["Month"] == df["DayNum"])
    
    # 台番号属性
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

# --- ★重要: 最新機種マスターの作成 ---
# フィルタリング前の「全データ」を使って、各台番号の最新日付の機種を特定する
if "台番号" in df.columns and "機種" in df.columns:
    # 台番号ごとに最新の日付を持つ行のインデックスを取得
    latest_indices = df.groupby("台番号")["日付"].idxmax()
    # その行から「台番号」と「機種」を抽出して辞書にする {555: "マイジャグV", 556: "ハナハナ"...}
    latest_machine_map = df.loc[latest_indices].set_index("台番号")["機種"].to_dict()
else:
    latest_machine_map = {}


# --- サイドバー ---
st.sidebar.header("🎯 戦略設定")

if st.sidebar.button("🔄 データを最新に更新"):
    st.cache_data.clear()
    st.rerun()

# 期間フィルタ
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
    st.sidebar.warning("末尾またはゾロ目を選択してください。全データを表示中。")
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
    "④ 機種×末尾"
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
            fig.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
            fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)

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
            fig2.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            st.plotly_chart(fig2, use_container_width=True)
            st.dataframe(zorome_metrics[["台ゾロ目タイプ", "勝率", "平均差枚", "機械割", "サンプル数"]].style.format({"勝率": "{:.1f}%", "平均差枚": "{:+,.0f}", "機械割": "{:.1f}%"}).background_gradient(subset=["機械割"], cmap="RdYlGn"), use_container_width=True)

# ==========================================
# 2. 鉄板台ランキング (★現役・撤去判別)
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
            # ★ここで判別ロジック適用
            # 行ごとの機種が、最新マスター(latest_machine_map)と一致するか？
            def check_status(row):
                current = latest_machine_map.get(row["台番号"])
                if current == row["機種"]:
                    return "🟢現役" # Current
                else:
                    return "💀撤去" # Removed
            
            filtered["設置"] = filtered.apply(check_status, axis=1)
            
            # グラフ用ラベル
            filtered["表示名"] = filtered["設置"] + " " + filtered["台番号"].astype(str) + " (" + filtered["機種"] + ")"
            
            # 散布図
            fig = px.scatter(filtered, x="勝率", y="平均差枚", size="サンプル数", color="機械割", 
                             hover_name="表示名", text="台番号", color_continuous_scale="RdYlGn",
                             symbol="設置", # 形を変える (丸=現役、ひし形=撤去など)
                             title="勝率 vs 平均差枚 (🟢=現役 / 💀=撤去)")
            fig.add_hline(y=0, line_dash="dash"); fig.add_vline(x=50, line_dash="dash")
            st.plotly_chart(fig, use_container_width=True)
            
            # リスト表示（設置カラムを先頭に）
            st.dataframe(
                filtered[["設置", "台番号", "機種", "機械割", "勝率", "平均差枚", "平均G数", "サンプル数"]]
                .sort_values(["設置", "機械割"], ascending=[True, False]) # 現役を上に、その中で機械割順
                .style.format({"勝率": "{:.1f}%", "平均差枚": "{:+,.0f}", "平均G数": "{:,.0f}", "機械割": "{:.1f}%"})
                .background_gradient(subset=["機械割", "平均差枚"], cmap="RdYlGn")
                .applymap(lambda v: 'color: transparent' if v == "💀撤去" else '', subset=["設置"]), # 撤去は目立たせない工夫など
                use_container_width=True
            )

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
        st.dataframe(model_metrics[["機種", "機械割", "勝率", "平均差枚", "平均G数", "サンプル数"]].style.format({"勝率": "{:.1f}%", "平均差枚": "{:+,.0f}", "平均G数": "{:,.0f}", "機械割": "{:.1f}%"}).background_gradient(subset=["機械割"], cmap="RdYlGn"), use_container_width=True)

# ==========================================
# 4. 機種 × 末尾
# ==========================================
with tab4:
    st.subheader("④ 機種 × 末尾 の法則")
    cross = target_df.groupby(["機種", "台末尾"]).agg(総差枚=("総差枚", "sum"), 総G=("G数", "sum")).reset_index()
    cross["機械割"] = cross.apply(lambda x: ((x["総G"]*3 + x["総差枚"])/(x["総G"]*3)*100) if x["総G"]>0 else 0, axis=1).round(1)
    
    sel_models = st.multiselect("機種選択", sorted(target_df["機種"].unique()), default=target_df["機種"].value_counts().head(10).index.tolist())
    if sel_models:
        filt = cross[cross["機種"].isin(sel_models)]
        hm = filt.pivot(index="機種", columns="台末尾", values="機械割").fillna(0)
        fig = px.imshow(hm, labels=dict(x="末尾", y="機種", color="機械割"), zmin=90, zmax=110, aspect="auto", text_auto=True, color_continuous_scale="RdYlGn")
        fig.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
        st.plotly_chart(fig, use_container_width=True)
