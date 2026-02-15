import streamlit as st
import pandas as pd
import plotly.express as px

# --- 設定 ---
# スプレッドシートURLがある場合はここに貼る
SHEET_URL = "https://docs.google.com/spreadsheets/d/1wIdronWDW8xK0jDepQfWbFPBbnIVrkTls2hBDqcduVI/export?format=csv" 

# --- ページ設定 ---
st.set_page_config(page_title="特定日攻略(ゾロ目対応)", layout="wide")
st.title("🎰 特定日攻略・狙い台分析ツール (ゾロ目対応版)")

# --- 1. データ読み込み ---
@st.cache_data(ttl=600)
def load_data():
    df = None
    # URLから読み込みトライ
    if SHEET_URL:
        try:
            df = pd.read_csv(SHEET_URL)
        except:
            pass
    
    # ダメならローカルファイル
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
    
    # ★ゾロ目判定ロジック (今回追加)
    # 1. 毎月11日と22日
    # 2. 月と日が同じ (1/1, 2/2 ... 11/11, 12/12)
    df["is_Zorome"] = (df["DayNum"].isin([11, 22])) | (df["Month"] == df["DayNum"])
    
    if "台番号" in df.columns:
        df["台末尾"] = df["台番号"] % 10
    else:
        df["台末尾"] = 0

    return df

df = load_data()

if df is None:
    st.error("データ読み込みエラー。CSVファイルまたはURLを確認してください。")
    st.stop()

# --- サイドバー ---
st.sidebar.header("🎯 戦略設定")

# データ更新ボタン
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

# 1. 末尾選択
target_ends = st.sidebar.multiselect(
    "① 日付の末尾 (0-9)", 
    options=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    default=[] 
)

# 2. ゾロ目選択 (追加)
use_zorome = st.sidebar.checkbox("② ゾロ目の日を含める", value=False, help="毎月11, 22日、および月日ゾロ目(1/1, 7/7等)")

# データ抽出ロジック
# 末尾選択 または ゾロ目選択 のいずれかに該当する行を抽出
mask = pd.Series([False] * len(df), index=df.index) # 初期値False

if target_ends:
    mask = mask | df["末尾"].isin(target_ends)

if use_zorome:
    mask = mask | df["is_Zorome"]

# 何も選んでいない場合は全データを表示するか、警告を出す
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
    
    return agg

# タイトル生成
title_parts = []
if target_ends:
    title_parts.append(f"末尾{target_ends}")
if use_zorome:
    title_parts.append("ゾロ目")
title_str = " & ".join(title_parts) if title_parts else "全期間"

st.markdown(f"### 🎯 分析対象: {title_str}")
st.caption(f"抽出データ: {len(target_df)} 件 / 対象日数: {target_df['日付'].nunique()} 日")

# === タブ構成 ===
tab1, tab2, tab3, tab4 = st.tabs([
    "① 特定日×台末尾", 
    "② 特定日×全台番(機種別)", 
    "③ 特定日×機種", 
    "④ 特定日×機種×末尾"
])

# ==========================================
# 1. 特定日 × 台の末尾
# ==========================================
with tab1:
    st.subheader(f"① {title_str} における「台番号末尾」の傾向")
    st.markdown("ゾロ目の日や特定日に、**どの台番末尾**に入れる癖があるか？")
    
    if "台番号" in target_df.columns:
        matsubi_metrics = calculate_metrics(target_df, ["台末尾"])
        
        fig = px.bar(matsubi_metrics, x="台末尾", y="平均差枚", 
                     color="機械割", color_continuous_scale="RdYlGn",
                     text="機械割", title="末尾ごとの平均差枚")
        fig.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
        fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(
            matsubi_metrics[["台末尾", "勝率", "平均差枚", "機械割", "サンプル数"]]
            .style.format({"勝率": "{:.1f}%", "平均差枚": "{:+,.0f}", "機械割": "{:.1f}%"})
            .background_gradient(subset=["平均差枚", "機械割"], cmap="RdYlGn"),
            use_container_width=True
        )

# ==========================================
# 2. 特定日 × 全ての台番 (機種別分離)
# ==========================================
with tab2:
    st.subheader(f"② {title_str} の鉄板台ランキング")
    st.markdown("ゾロ目や特定日に**毎回強い台番号**を探します。")
    
    if "台番号" not in target_df.columns:
        st.error("台番号のデータがありません。")
    else:
        min_sample = st.slider("最低稼働回数", 1, 10, 1, key="tab2_slider")
        
        daiban_metrics = calculate_metrics(target_df, ["台番号", "機種"])
        filtered_metrics = daiban_metrics[daiban_metrics["サンプル数"] >= min_sample]
        
        if filtered_metrics.empty:
            st.warning(f"条件に合うデータがありません。")
        else:
            filtered_metrics["表示名"] = filtered_metrics["台番号"].astype(str) + " (" + filtered_metrics["機種"] + ")"

            fig = px.scatter(filtered_metrics, x="勝率", y="平均差枚", 
                             size="サンプル数", color="機械割", 
                             hover_name="表示名",
                             hover_data=["台番号", "機種"],
                             text="台番号", 
                             color_continuous_scale="RdYlGn",
                             title="勝率 vs 平均差枚 (台番×機種ごと)")
            
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.add_vline(x=50, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(
                filtered_metrics[["台番号", "機種", "機械割", "勝率", "平均差枚", "平均G数", "サンプル数"]]
                .sort_values("機械割", ascending=False)
                .style.format({"勝率": "{:.1f}%", "平均差枚": "{:+,.0f}", "平均G数": "{:,.0f}", "機械割": "{:.1f}%"})
                .background_gradient(subset=["機械割", "平均差枚"], cmap="RdYlGn"),
                use_container_width=True
            )

# ==========================================
# 3. 特定日 × 機種
# ==========================================
with tab3:
    st.subheader(f"③ {title_str} の機種別ランキング")
    st.markdown("この特定日に**扱いが良い機種**は？")
    
    model_metrics = calculate_metrics(target_df, ["機種"])
    
    min_model_sample = st.slider("最低稼働台数", 1, 10, 1, key="tab3_slider")
    model_metrics = model_metrics[model_metrics["サンプル数"] >= min_model_sample]
    
    if model_metrics.empty:
        st.warning("データなし")
    else:
        model_metrics = model_metrics.sort_values("総差枚", ascending=False).head(20)
        
        fig = px.bar(model_metrics, x="機械割", y="機種", orientation='h',
                     color="総差枚", color_continuous_scale="RdYlGn",
                     text="機械割", title="機種別 機械割ランキング")
        fig.add_vline(x=100, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)
        
        st.dataframe(
            model_metrics[["機種", "機械割", "勝率", "平均差枚", "サンプル数"]]
            .style.format({"勝率": "{:.1f}%", "平均差枚": "{:+,.0f}", "機械割": "{:.1f}%"})
            .background_gradient(subset=["機械割"], cmap="RdYlGn"),
            use_container_width=True
        )

# ==========================================
# 4. 特定日 × 機種 × 末尾
# ==========================================
with tab4:
    st.subheader(f"④ {title_str} の 機種×末尾 法則")
    
    cross_metrics = target_df.groupby(["機種", "台末尾"]).agg(
        総差枚=("総差枚", "sum"),
        総G数=("G数", "sum")
    ).reset_index()
    
    cross_metrics["機械割"] = cross_metrics.apply(
        lambda x: ((x["総G数"]*3 + x["総差枚"]) / (x["総G数"]*3) * 100) if x["総G数"] > 0 else 0, 
        axis=1
    ).round(1)
    
    top_models = target_df["機種"].value_counts().head(10).index.tolist()
    selected_models = st.multiselect("機種選択", sorted(target_df["機種"].unique()), default=top_models)
    
    if selected_models:
        filtered_cross = cross_metrics[cross_metrics["機種"].isin(selected_models)]
        
        heatmap_data = filtered_cross.pivot(index="機種", columns="台末尾", values="機械割").fillna(0)
        
        fig = px.imshow(heatmap_data, 
                        labels=dict(x="台末尾", y="機種", color="機械割(%)"),
                        x=heatmap_data.columns, y=heatmap_data.index,
                        color_continuous_scale="RdYlGn",
                        zmin=90, zmax=110, aspect="auto", text_auto=True)
        
        fig.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1), height=600)
        st.plotly_chart(fig, use_container_width=True)
