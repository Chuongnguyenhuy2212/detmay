"""
MSH & TNG Investment Monitor Dashboard v2
Thêm: Vòng Quay Tồn Kho (Inventory Turnover / DIO) từ 2020
Run: streamlit run dashboard.py
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

# ─── PAGE CONFIG ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MSH / TNG Monitor v2",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="stSidebar"] { background: #0d1117; }
    [data-testid="metric-container"] {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 10px; padding: 12px 16px;
    }
    hr { border-color: #30363d !important; }
    .badge-green  { display:inline-block; padding:3px 10px; border-radius:12px;
                    background:#0d3321; color:#3fb950; font-weight:600; font-size:.85em; }
    .badge-red    { display:inline-block; padding:3px 10px; border-radius:12px;
                    background:#3d0d0d; color:#f85149; font-weight:600; font-size:.85em; }
    .badge-yellow { display:inline-block; padding:3px 10px; border-radius:12px;
                    background:#2d2400; color:#e3b341; font-weight:600; font-size:.85em; }
    .badge-grey   { display:inline-block; padding:3px 10px; border-radius:12px;
                    background:#21262d; color:#8b949e; font-weight:600; font-size:.85em; }
    .section-title { font-size:1.05em; font-weight:700; color:#e6edf3;
                     border-left:3px solid #1f6feb; padding-left:10px; margin-bottom:4px; }
    .sub-note { color:#8b949e; font-size:.82em; margin-top:-2px; margin-bottom:10px; }
</style>
""", unsafe_allow_html=True)

# ─── LOAD FRED KEY (từ file hoặc sidebar) ───────────────────────────────────────
import os

def _load_key_from_file():
    """Đọc FRED key từ fred_key.txt nếu tồn tại."""
    for path in [
        os.path.join(os.path.dirname(__file__), "fred_key.txt"),
        r"D:\data\fred_key.txt",
    ]:
        if os.path.exists(path):
            key = open(path).read().strip()
            if key:
                return key
    return ""

_key_from_file = _load_key_from_file() or "987e91eeeb35bf3af1614395e5c8bade"

# ─── SIDEBAR ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Cài đặt")

    fred_key = st.text_input(
        "🔑 FRED API Key",
        value=_key_from_file,
        type="password",
        placeholder="abcdef1234...",
        help="Đăng ký miễn phí: fred.stlouisfed.org/api/key.php",
    )

    if fred_key:
        st.success("✅ Key đã được nhận")
    else:
        st.warning("👆 Nhập key hoặc lưu vào fred_key.txt")
        st.caption("Tạo file `D:\\data\\fred_key.txt`, dán key vào đó → restart app")

    macro_period = st.select_slider("📅 Macro Period", ["2Y", "3Y", "5Y"], value="5Y")
    st.divider()
    if st.button("🔄 Refresh tất cả dữ liệu", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()
    st.markdown("**📡 Nguồn dữ liệu**\n- FRED – Retail Sales, PMI\n- Yahoo Finance – Giá CP, Tài chính")
    st.caption(f"⏱ {datetime.now().strftime('%d/%m/%Y %H:%M')}")

# ─── CONSTANTS ──────────────────────────────────────────────────────────────────
MACRO_DAYS = {"2Y": 730, "3Y": 1095, "5Y": 1825}
START_MACRO = (datetime.now() - timedelta(days=MACRO_DAYS[macro_period])).strftime("%Y-%m-%d")

CHART_BASE = dict(
    template="plotly_dark",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=8, r=8, t=32, b=8),
    legend=dict(orientation="h", y=-0.28, font_size=11),
    hovermode="x unified",
)

MSH_CUSTOMERS = [
    ("COLM", "Columbia Sportswear", "Đối tác chiến lược lâu đời",   "Outdoor / Sportswear"),
    ("GIII", "G-III Apparel Group", "May gia công CK, Tommy, DKNY", "Fashion Branded"),
    ("WMT",  "Walmart",             "Kênh phân phối hàng cơ bản",   "Mass Retail"),
    ("TGT",  "Target",              "Kênh phân phối hàng cơ bản",   "Mass Retail"),
]
TNG_CUSTOMERS = [
    ("NKE",   "Nike",                "Đồ thể thao cao cấp",  "Sportswear – NYSE"),
    ("ADDYY", "Adidas ADR",          "Đồ thể thao & lifestyle","Sportswear – OTC"),
    ("PLCE",  "The Children's Place","Đồ trẻ em Mỹ",          "Kids Apparel – Nasdaq"),
    ("HNNMY", "H&M Group ADR",       "Thời trang nhanh",      "Fast Fashion – OTC"),
]
ALL_CUSTOMERS = MSH_CUSTOMERS + TNG_CUSTOMERS

PALETTE = ["#58a6ff","#3fb950","#e3b341","#f85149",
           "#e040fb","#ff9800","#00bcd4","#8bc34a"]


# ─── DATA HELPERS ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fred_series(series_id, api_key, start):
    if not api_key:
        return None, "API_KEY_MISSING"
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={api_key}&file_type=json"
           f"&observation_start={start}&sort_order=asc")
    try:
        r = requests.get(url, timeout=12)
        d = r.json()
        if "observations" not in d:
            return None, d.get("error_message", "Unknown FRED error")
        df = pd.DataFrame(d["observations"])
        df["date"]  = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df.dropna(subset=["value"]).set_index("date")["value"], None
    except Exception as e:
        return None, str(e)


@st.cache_data(ttl=3600, show_spinner=False)
def stock_price(ticker, period="5y"):
    try:
        h = yf.Ticker(ticker).history(period=period)
        return h["Close"].dropna() if not h.empty else None
    except Exception:
        return None


def _find_row(df, keywords, exclude=None):
    """Find first matching row in a DataFrame by keyword."""
    if df is None or df.empty:
        return None
    for kw in keywords:
        matches = [k for k in df.index if kw.lower() in k.lower()]
        if exclude:
            matches = [m for m in matches if exclude.lower() not in m.lower()]
        if matches:
            return df.loc[matches[0]].dropna()
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_annual_financials(ticker):
    """
    Annual data from 2020: COGS, Inventory, Revenue → Turnover & DIO.
    yfinance annual statements typically cover the last 4 fiscal years.
    """
    try:
        t   = yf.Ticker(ticker)
        inc = t.income_stmt
        bs  = t.balance_sheet

        cogs = _find_row(inc, ["Cost Of Revenue", "Cost of Goods", "Reconciled Cost"],
                         exclude="Gross")
        inv  = _find_row(bs,  ["Inventory"])
        rev  = _find_row(inc, ["Total Revenue", "Revenue"])

        if cogs is None or inv is None:
            return None

        common = cogs.index.intersection(inv.index)
        if len(common) == 0:
            return None

        df = pd.DataFrame({
            "cogs":      cogs[common].abs(),
            "inventory": inv[common],
        }, index=common).sort_index()

        if rev is not None:
            rc = rev.index.intersection(common)
            df.loc[rc, "revenue"] = rev[rc]

        # Average inventory for accuracy
        df["inv_avg"]  = (df["inventory"] + df["inventory"].shift(1)) / 2
        df["inv_avg"]  = df["inv_avg"].fillna(df["inventory"])
        df["turnover"] = df["cogs"] / df["inv_avg"]
        df["dio"]      = df["inv_avg"] / df["cogs"] * 365
        df["year"]     = df.index.year

        return df[df.index >= "2020-01-01"] if len(df) > 0 else None
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def get_quarterly_financials(ticker):
    """
    Quarterly: Revenue, Inventory, COGS → annualized Turnover & DIO.
    """
    try:
        t   = yf.Ticker(ticker)
        inc = t.quarterly_income_stmt
        bs  = t.quarterly_balance_sheet

        cogs = _find_row(inc, ["Cost Of Revenue", "Cost of Goods"], exclude="Gross")
        inv  = _find_row(bs,  ["Inventory"])
        rev  = _find_row(inc, ["Total Revenue", "Revenue"])

        if inv is None:
            return None

        idx = inv.index
        if cogs is not None:
            idx = idx.intersection(cogs.index)

        df = pd.DataFrame(index=idx)
        df["inventory"] = inv[idx]

        if cogs is not None:
            df["cogs"]     = cogs[idx].abs()
            df["inv_avg"]  = (df["inventory"] + df["inventory"].shift(1)) / 2
            df["inv_avg"]  = df["inv_avg"].fillna(df["inventory"])
            df["turnover"] = df["cogs"] * 4 / df["inv_avg"]       # annualized
            df["dio"]      = df["inv_avg"] / (df["cogs"] * 4) * 365

        if rev is not None:
            ri = rev.index.intersection(idx)
            df.loc[ri, "revenue"] = rev[ri]

        df = df.sort_index()
        df["q_label"] = [f"{d.year}-Q{(d.month-1)//3+1}" for d in df.index]
        return df if len(df) > 0 else None
    except Exception:
        return None


# ─── SIGNALS ────────────────────────────────────────────────────────────────────
def dio_signal(df_a):
    """Annual DIO trend. DIO down = faster selling = 🟢"""
    if df_a is None or "dio" not in df_a.columns or len(df_a) < 2:
        return None, "N/A", "badge-grey"
    latest = df_a["dio"].iloc[-1]
    prev   = df_a["dio"].iloc[-2]
    if pd.isna(prev) or prev == 0:
        return None, "N/A", "badge-grey"
    chg = (latest - prev) / prev * 100
    if chg < -5:
        return chg, f"▼ {abs(chg):.1f}% → {latest:.0f}d", "badge-green"
    elif chg > 5:
        return chg, f"▲ {chg:.1f}% → {latest:.0f}d", "badge-red"
    return chg, f"→ {chg:.1f}% ({latest:.0f}d)", "badge-yellow"


def inv_yoy(df_q):
    if df_q is None or "inventory" not in df_q.columns or len(df_q) < 5:
        return None, "N/A", "badge-grey"
    s = df_q["inventory"].dropna()
    if len(s) < 5:
        return None, "N/A", "badge-grey"
    pct = (s.iloc[-1] - s.iloc[-5]) / abs(s.iloc[-5]) * 100
    if pct < -5:  return pct, f"▼ {abs(pct):.1f}%", "badge-green"
    if pct > 5:   return pct, f"▲ {pct:.1f}%",  "badge-red"
    return pct, f"→ {pct:.1f}%", "badge-yellow"


def rev_yoy(df_q):
    if df_q is None or "revenue" not in df_q.columns:
        return None, "N/A", "badge-grey"
    s = df_q["revenue"].dropna()
    if len(s) < 5:
        return None, "N/A", "badge-grey"
    pct = (s.iloc[-1] - s.iloc[-5]) / abs(s.iloc[-5]) * 100
    if pct > 5:   return pct, f"▲ {pct:.1f}%",  "badge-green"
    if pct < -5:  return pct, f"▼ {abs(pct):.1f}%", "badge-red"
    return pct, f"→ {pct:.1f}%", "badge-yellow"


def overall_signal(dio_chg, inv_pct, rev_pct):
    score = 0
    if dio_chg is not None: score += (-1 if dio_chg < -5 else 1 if dio_chg > 5 else 0)
    if inv_pct is not None: score += (-1 if inv_pct < -5 else 1 if inv_pct > 5 else 0)
    if rev_pct is not None: score += ( 1 if rev_pct >  5 else -1 if rev_pct < -5 else 0)
    if score <= -2: return "🟢 Tích cực",  "badge-green"
    if score >=  2: return "🔴 Tiêu cực",  "badge-red"
    return "🟡 Trung tính", "badge-yellow"


# ─── CHARTS ─────────────────────────────────────────────────────────────────────
def chart_retail(series):
    df = series.reset_index(); df.columns = ["date", "value"]
    df["mom"] = df["value"].pct_change() * 100
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df["date"], y=df["value"]/1e3, name="Sales ($B)",
                             line=dict(color="#58a6ff", width=2.5), fill="tozeroy",
                             fillcolor="rgba(88,166,255,0.07)"), secondary_y=False)
    bc = ["#3fb950" if v >= 0 else "#f85149" for v in df["mom"].fillna(0)]
    fig.add_trace(go.Bar(x=df["date"], y=df["mom"], name="MoM%",
                         marker_color=bc, opacity=0.55), secondary_y=True)
    fig.update_layout(height=300, title="US Retail Sales – Clothing MRTSSM4481USS", **CHART_BASE)
    fig.update_yaxes(title_text="$B",   secondary_y=False, gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(title_text="MoM%", secondary_y=True,  showgrid=False)
    return fig


def chart_cotton(series):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, name="Cotton ¢/lb",
                             line=dict(color="#e3b341", width=2)))
    fig.add_trace(go.Scatter(x=series.index, y=series.rolling(20).mean(), name="MA20",
                             line=dict(color="#ff9800", width=1.2, dash="dot")))
    fig.add_trace(go.Scatter(x=series.index, y=series.rolling(60).mean(), name="MA60",
                             line=dict(color="#e040fb", width=1.2, dash="dash")))
    fig.update_layout(height=300, title="Cotton Futures CT=F", **CHART_BASE)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")
    return fig


def chart_pmi(series):
    """IPMAN – Industrial Production Manufacturing (Index 2017=100)."""
    df = series.reset_index(); df.columns = ["date", "value"]
    df["yoy"] = df["value"].pct_change(12) * 100
    ma12 = df["value"].rolling(12).mean()
    colors = ["#3fb950" if (v or 0) >= 0 else "#f85149" for v in df["yoy"].fillna(0)]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=df["date"], y=df["value"], name="IPMAN (Index)",
                             line=dict(color="#58a6ff", width=2)), secondary_y=False)
    fig.add_trace(go.Scatter(x=df["date"], y=ma12, name="MA12",
                             line=dict(color="#ff9800", width=1.2, dash="dot")),
                  secondary_y=False)
    fig.add_trace(go.Bar(x=df["date"], y=df["yoy"], name="YoY%",
                         marker_color=colors, opacity=0.55), secondary_y=True)
    fig.update_layout(height=300,
                      title="Sản xuất Công nghiệp Mỹ – IPMAN (2017=100)",
                      **CHART_BASE)
    fig.update_yaxes(title_text="Index", secondary_y=False,
                     gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(title_text="YoY%", secondary_y=True, showgrid=False)
    return fig


def chart_dio_annual(df_a, ticker, name):
    """
    Annual DIO bars (colored: green if dropping, red if rising) + Turnover line.
    This is the KEY chart showing inventory cycle from 2020.
    """
    if df_a is None or "dio" not in df_a.columns or len(df_a) == 0:
        return None
    ylabels = df_a["year"].astype(str).tolist()
    dio_v   = df_a["dio"].tolist()
    turn_v  = df_a["turnover"].tolist()

    bar_colors = []
    for i, v in enumerate(dio_v):
        if i == 0:
            bar_colors.append("#58a6ff")
        else:
            bar_colors.append("#3fb950" if v < dio_v[i-1] else "#f85149")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=ylabels, y=dio_v, name="DIO (ngày tồn kho)",
               marker_color=bar_colors, opacity=0.78,
               text=[f"{v:.0f}d" for v in dio_v],
               textposition="outside", textfont=dict(size=12, color="white")),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=ylabels, y=turn_v, name="Vòng quay (lần/năm)",
                   line=dict(color="#e3b341", width=2.5),
                   mode="lines+markers+text",
                   text=[f"{v:.1f}x" for v in turn_v],
                   textposition="top center", textfont=dict(size=11, color="#e3b341"),
                   marker=dict(size=8)),
        secondary_y=True,
    )
    fig.update_yaxes(title_text="DIO (ngày)",      secondary_y=False,
                     gridcolor="rgba(255,255,255,0.07)")
    fig.update_yaxes(title_text="Vòng quay (x/năm)", secondary_y=True, showgrid=False)
    fig.update_layout(
        height=320,
        title=f"{ticker} – {name} | Vòng Quay & DIO (Annual 2020→)",
        **CHART_BASE,
    )
    return fig


def chart_dio_quarterly(df_q, ticker):
    """Quarterly DIO bars + Inventory level line."""
    if df_q is None or "dio" not in df_q.columns:
        return None
    df = df_q.dropna(subset=["dio"]).tail(12)
    if len(df) < 3:
        return None
    ql = df["q_label"].tolist()
    bc = []
    for i, v in enumerate(df["dio"].tolist()):
        bc.append("#58a6ff" if i == 0
                  else "#3fb950" if v < df["dio"].iloc[i-1] else "#f85149")

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=ql, y=df["dio"], name="DIO (ngày)",
               marker_color=bc, opacity=0.72,
               text=[f"{v:.0f}d" for v in df["dio"]],
               textposition="outside", textfont=dict(size=10)),
        secondary_y=False,
    )
    if "inventory" in df.columns:
        fig.add_trace(
            go.Scatter(x=ql, y=df["inventory"]/1e6, name="Inventory ($M)",
                       line=dict(color="#e040fb", width=2), mode="lines+markers",
                       marker=dict(size=5)),
            secondary_y=True,
        )
    fig.update_yaxes(title_text="DIO (ngày)",     secondary_y=False,
                     gridcolor="rgba(255,255,255,0.06)")
    fig.update_yaxes(title_text="Inventory ($M)", secondary_y=True, showgrid=False)
    fig.update_layout(height=280,
                      title=f"{ticker} – Quarterly DIO (12 quý gần nhất)", **CHART_BASE)
    return fig


def chart_revenue_quarterly(df_q, ticker):
    if df_q is None or "revenue" not in df_q.columns:
        return None
    df = df_q.dropna(subset=["revenue"]).tail(12)
    if len(df) < 2:
        return None
    ql = df["q_label"].tolist()
    yoy_colors = []
    for i in range(len(df)):
        if i < 4:
            yoy_colors.append("#58a6ff")
        else:
            yoy_colors.append(
                "#3fb950" if df["revenue"].iloc[i] > df["revenue"].iloc[i-4] else "#f85149")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=ql, y=df["revenue"]/1e6, name="Revenue ($M)",
                         marker_color=yoy_colors, opacity=0.82,
                         text=[f"${v/1e6:.0f}M" for v in df["revenue"]],
                         textposition="outside", textfont=dict(size=10)))
    fig.update_layout(height=270,
                      title=f"{ticker} – Quarterly Revenue ($M)", **CHART_BASE,
                      yaxis=dict(gridcolor="rgba(255,255,255,0.06)"))
    return fig


def chart_price(series, ticker, color="#58a6ff"):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series.values, name=ticker,
                             line=dict(color=color, width=2), fill="tozeroy",
                             fillcolor="rgba(88,166,255,0.06)"))
    fig.add_trace(go.Scatter(x=series.index, y=series.rolling(50).mean(), name="MA50",
                             line=dict(color="#ff9800", width=1.2, dash="dot")))
    fig.add_trace(go.Scatter(x=series.index, y=series.rolling(200).mean(), name="MA200",
                             line=dict(color="#e040fb", width=1.2, dash="dash")))
    fig.update_layout(height=220, title=f"{ticker} – Giá cổ phiếu (5Y)", **CHART_BASE)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")
    return fig


# ─── COMPARISON CHARTS ──────────────────────────────────────────────────────────
def chart_compare_dio(customer_list, label):
    fig = go.Figure()
    for i, (tk, nm, _, _) in enumerate(customer_list):
        df = get_annual_financials(tk)
        if df is None or "dio" not in df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df["year"].astype(str).tolist(), y=df["dio"].tolist(),
            name=tk, line=dict(color=PALETTE[i], width=2.3),
            mode="lines+markers+text",
            text=[f"{v:.0f}" for v in df["dio"]],
            textposition="top center", textfont=dict(size=9),
            marker=dict(size=7),
        ))
    fig.update_layout(
        height=380,
        title=f"So sánh DIO theo năm – {label}<br>"
              f"<sup>🟢 Giảm = bán nhanh hơn = sắp đặt đơn mới cho MSH/TNG</sup>",
        **CHART_BASE,
        yaxis=dict(title="DIO (ngày tồn kho)", gridcolor="rgba(255,255,255,0.07)"),
    )
    return fig


def chart_compare_turnover(customer_list, label):
    fig = go.Figure()
    for i, (tk, nm, _, _) in enumerate(customer_list):
        df = get_annual_financials(tk)
        if df is None or "turnover" not in df.columns:
            continue
        fig.add_trace(go.Scatter(
            x=df["year"].astype(str).tolist(), y=df["turnover"].tolist(),
            name=tk, line=dict(color=PALETTE[i], width=2.3),
            mode="lines+markers", marker=dict(size=7),
        ))
    fig.update_layout(
        height=350,
        title=f"Vòng Quay Tồn Kho (lần/năm) – {label}<br>"
              f"<sup>🟢 Tăng = bán hàng tốt hơn</sup>",
        **CHART_BASE,
        yaxis=dict(title="Vòng quay (x/năm)", gridcolor="rgba(255,255,255,0.07)"),
    )
    return fig


def chart_compare_inv_quarterly(customer_list, label):
    """Indexed quarterly inventory (base = first quarter available = 100)."""
    fig = go.Figure()
    fig.add_hline(y=100, line_dash="dot", line_color="#8b949e", line_width=1,
                  annotation_text="Base = 100", annotation_font_color="#8b949e")
    for i, (tk, nm, _, _) in enumerate(customer_list):
        df = get_quarterly_financials(tk)
        if df is None or "inventory" not in df.columns or len(df) < 4:
            continue
        base = df["inventory"].dropna().iloc[0]
        if base == 0 or pd.isna(base):
            continue
        indexed = df["inventory"] / base * 100
        fig.add_trace(go.Scatter(
            x=df["q_label"].tolist(), y=indexed.tolist(),
            name=tk, line=dict(color=PALETTE[i], width=2),
            mode="lines+markers", marker=dict(size=4),
        ))
    fig.update_layout(
        height=340,
        title=f"Mức Tồn Kho (index, quý đầu = 100) – {label}",
        **CHART_BASE,
        yaxis=dict(title="Index", gridcolor="rgba(255,255,255,0.07)"),
    )
    return fig


# ─── CUSTOMER CARD ───────────────────────────────────────────────────────────────
def render_customer_card(ticker, name, role, segment):
    df_a  = get_annual_financials(ticker)
    df_q  = get_quarterly_financials(ticker)
    price = stock_price(ticker)

    dio_chg, dio_lbl, dio_cls = dio_signal(df_a)
    inv_pct, inv_lbl, inv_cls = inv_yoy(df_q)
    rev_pct, rev_lbl, rev_cls = rev_yoy(df_q)
    sig_txt, sig_cls          = overall_signal(dio_chg, inv_pct, rev_pct)

    with st.expander(f"**{ticker}**  —  {name}  |  {segment}", expanded=True):
        c_info, c_metrics, c_charts = st.columns([1.0, 1.2, 3.8])

        with c_info:
            st.markdown(
                f"<div class='section-title'>{ticker}</div>"
                f"<div class='sub-note'>{role}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"Tín hiệu đặt hàng:<br><span class='{sig_cls}'>{sig_txt}</span>",
                unsafe_allow_html=True,
            )

        with c_metrics:
            if price is not None and len(price) >= 2:
                cur = price.iloc[-1]; prev = price.iloc[-2]
                st.metric("Giá CP", f"${cur:.2f}", f"{(cur-prev)/prev*100:+.2f}%")

            st.markdown(
                f"**DIO YoY:** <span class='{dio_cls}'>{dio_lbl}</span><br>"
                f"**Tồn kho YoY:** <span class='{inv_cls}'>{inv_lbl}</span><br>"
                f"**Doanh số YoY:** <span class='{rev_cls}'>{rev_lbl}</span>",
                unsafe_allow_html=True,
            )

        with c_charts:
            t_annual, t_quarterly, t_revenue, t_price = st.tabs([
                "📊 Vòng Quay (Annual 2020→)",
                "📦 DIO Quarterly",
                "💰 Revenue Quarterly",
                "📈 Giá CP",
            ])
            with t_annual:
                f = chart_dio_annual(df_a, ticker, name)
                st.plotly_chart(f, use_container_width=True) if f else \
                    st.info("Không đủ dữ liệu annual. Yahoo Finance thường có 4 năm gần nhất.")
            with t_quarterly:
                f = chart_dio_quarterly(df_q, ticker)
                st.plotly_chart(f, use_container_width=True) if f else \
                    st.info("Không đủ dữ liệu quarterly DIO.")
            with t_revenue:
                f = chart_revenue_quarterly(df_q, ticker)
                st.plotly_chart(f, use_container_width=True) if f else \
                    st.info("Không đủ dữ liệu revenue.")
            with t_price:
                if price is not None and len(price) > 20:
                    st.plotly_chart(chart_price(price, ticker), use_container_width=True)
                else:
                    st.info("Không có dữ liệu giá.")


# ══════════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════════
st.title("📊 MSH & TNG – Investment Monitor v2")
st.caption("Vòng Quay Tồn Kho · Leading Indicators · Chu kỳ Ngành 2020–nay")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📦  Vòng Quay Tồn Kho",
    "📈  Leading Indicators",
    "🏭  MSH Customers",
    "👕  TNG Customers",
    "🚦  Signal Board",
])


# ══════════════════════════════════════════════════════════════════════════════════
#  TAB 1 – VÒNG QUAY (NEW KEY FEATURE)
# ══════════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("""
<div class='section-title'>📦 Vòng Quay Tồn Kho – Toàn bộ khách hàng (Annual 2020 → nay)</div>
<div class='sub-note'>
  DIO (Days Inventory Outstanding) = số ngày để bán hết hàng tồn.
  <b>Giảm = bán nhanh hơn → sắp cần đặt thêm hàng từ MSH/TNG</b>.
</div>
""", unsafe_allow_html=True)

    with st.expander("💡 Đọc biểu đồ & Chu kỳ ngành"):
        st.markdown("""
**Công thức:**
- `DIO = Inventory_TB ÷ (COGS ÷ 365)` → Càng thấp = bán càng nhanh
- `Vòng quay = COGS ÷ Inventory_TB` → Càng cao = càng tốt

**Chu kỳ ngành may mặc điển hình 2020–2024:**
| Giai đoạn | DIO | Giải thích | Tín hiệu cho MSH/TNG |
|-----------|-----|-----------|----------------------|
| 2020 | 🔴 Tăng vọt | COVID – kênh bán sập | Đơn hàng sụt mạnh |
| 2021 | 🟢 Giảm mạnh | Mở cửa + thiếu hàng | Đơn hàng bùng nổ |
| 2022 | 🔴 Tăng trở lại | Overstocking (đặt quá nhiều) | Đơn hàng cắt giảm |
| 2023 | 🟡 Giảm dần | Destocking đang diễn ra | Đơn hàng phục hồi nhẹ |
| 2024→ | 🟢 Về mức bình thường? | Tùy từng brand | Xem biểu đồ |
        """)

    # ── MSH Customers DIO ───────────────────────────────────────────────────────
    st.markdown("### 🏭 MSH Customers")
    ca, cb = st.columns(2)
    with ca:
        with st.spinner("Tải dữ liệu COLM, GIII, WMT, TGT..."):
            fig = chart_compare_dio(MSH_CUSTOMERS, "MSH Customers")
        st.plotly_chart(fig, use_container_width=True)
    with cb:
        fig2 = chart_compare_turnover(MSH_CUSTOMERS, "MSH Customers")
        st.plotly_chart(fig2, use_container_width=True)

    with st.spinner("Tải dữ liệu quarterly..."):
        fig3 = chart_compare_inv_quarterly(MSH_CUSTOMERS, "MSH Customers")
    st.plotly_chart(fig3, use_container_width=True)

    st.divider()

    # ── TNG Customers DIO ───────────────────────────────────────────────────────
    st.markdown("### 👕 TNG Customers")
    cc, cd = st.columns(2)
    with cc:
        with st.spinner("Tải dữ liệu NKE, ADDYY, PLCE, HNNMY..."):
            fig4 = chart_compare_dio(TNG_CUSTOMERS, "TNG Customers")
        st.plotly_chart(fig4, use_container_width=True)
    with cd:
        fig5 = chart_compare_turnover(TNG_CUSTOMERS, "TNG Customers")
        st.plotly_chart(fig5, use_container_width=True)

    fig6 = chart_compare_inv_quarterly(TNG_CUSTOMERS, "TNG Customers")
    st.plotly_chart(fig6, use_container_width=True)

    st.divider()

    # ── Summary table ────────────────────────────────────────────────────────────
    st.markdown("### 📋 Bảng DIO theo năm (ngày)")
    rows = []
    all_years = list(range(2021, datetime.now().year + 1))
    for tk, nm, _, seg in ALL_CUSTOMERS:
        df = get_annual_financials(tk)
        row = {"Ticker": tk, "Tên": nm}
        if df is not None and "dio" in df.columns:
            for yr in all_years:
                y_df = df[df["year"] == yr]
                row[str(yr)] = f"{y_df['dio'].iloc[0]:.0f}d" if len(y_df) > 0 else "–"
            chg, lbl, cls = dio_signal(df)
            row["YoY ∆DIO"] = lbl
            row["Tín hiệu"] = "🟢" if "green" in cls else "🔴" if "red" in cls else "🟡"
        else:
            for yr in all_years:
                row[str(yr)] = "–"
            row["YoY ∆DIO"] = "N/A"
            row["Tín hiệu"] = "⚪"
        rows.append(row)

    df_tbl = pd.DataFrame(rows).set_index("Ticker")
    st.dataframe(df_tbl, use_container_width=True, height=340)
    st.caption("DIO (ngày tồn kho). 🟢 Giảm = bán nhanh hơn = tốt cho đơn hàng MSH/TNG")


# ══════════════════════════════════════════════════════════════════════════════════
#  TAB 2 – LEADING INDICATORS
# ══════════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("<div class='section-title'>🌐 Chỉ số Vĩ mô từ 2020</div>", unsafe_allow_html=True)

    ca, cb = st.columns(2)
    with ca:
        st.markdown("#### 🛍️ US Retail Sales – Apparel (MRTSSM4481USS)")
        st.markdown("<div class='sub-note'>Tín hiệu: Tăng ≥2T liên tiếp → đơn hàng sau 3–6T</div>",
                    unsafe_allow_html=True)
        with st.spinner("FRED MRTSSM4481USS..."):
            rrsfs, err_r = fred_series("MRTSSM4481USS", fred_key, START_MACRO)
        if rrsfs is not None:
            st.plotly_chart(chart_retail(rrsfs), use_container_width=True)
            last3 = rrsfs.pct_change().dropna().tail(3) * 100
            pos   = sum(1 for v in last3 if v > 0)
            if pos == 3:   st.success("🟢 Tăng 3 tháng liên tiếp – Tích cực")
            elif pos >= 2: st.warning("🟡 Tăng 2/3 tháng – Quan sát thêm")
            else:          st.error("🔴 Xu hướng giảm – Thận trọng")
        elif err_r == "API_KEY_MISSING":
            st.info("👉 Nhập **FRED API Key** ở sidebar để xem biểu đồ này\n\n"
                    "Đăng ký miễn phí: https://fred.stlouisfed.org/api/key.php")
        else:
            st.error(f"FRED: {err_r}")

    with cb:
        st.markdown("#### 🌾 Giá Bông – Cotton #2 (CT=F)")
        st.markdown("<div class='sub-note'>Tín hiệu: Giá giảm → biên LNG của MSH cải thiện</div>",
                    unsafe_allow_html=True)
        with st.spinner("Cotton CT=F..."):
            cotton = stock_price("CT=F")
        if cotton is not None and len(cotton) > 10:
            st.plotly_chart(chart_cotton(cotton), use_container_width=True)
            cur = cotton.iloc[-1]; avg = cotton.mean()
            pct = (cur - avg) / avg * 100
            (st.success if pct < -5 else st.error if pct > 5 else st.info)(
                f"{'🟢' if pct < -5 else '🔴' if pct > 5 else '🟡'} "
                f"{cur:.2f}¢/lb ({pct:+.1f}% vs TB 5 năm)")
        else:
            st.warning("Không lấy được giá bông")

    st.divider()
    cc, cd = st.columns(2)

    with cc:
        st.markdown("#### 🏭 ISM Manufacturing PMI (IPMAN)")
        with st.spinner("FRED IPMAN..."):
            pmi_s, err_pmi = fred_series("IPMAN", fred_key, START_MACRO)
        if pmi_s is not None:
            st.plotly_chart(chart_pmi(pmi_s), use_container_width=True)
            val = pmi_s.iloc[-1]
            yoy = (val - pmi_s.iloc[-13]) / pmi_s.iloc[-13] * 100 if len(pmi_s) > 13 else 0
            (st.success if yoy >= 1 else st.warning if yoy >= 0 else st.error)(
                f"{'🟢' if yoy >= 1 else '🟡' if yoy >= 0 else '🔴'} "
                f"IPMAN = {val:.1f} (YoY {yoy:+.1f}%) – "
                f"{'Tăng trưởng' if yoy >= 1 else 'Đi ngang' if yoy >= 0 else 'Suy giảm'}")
        elif err_pmi == "API_KEY_MISSING":
            st.info("👉 Cần FRED API Key")
        else:
            st.error(f"Lỗi: {err_pmi}")

    with cd:
        st.markdown("#### 🚢 Dry Bulk Shipping (BDRY ETF)")
        with st.spinner("BDRY..."):
            bdry = stock_price("BDRY")
        if bdry is not None and len(bdry) > 10:
            fig_b = go.Figure()
            fig_b.add_trace(go.Scatter(x=bdry.index, y=bdry.values, name="BDRY",
                                        fill="tozeroy", line=dict(color="#7986cb", width=2),
                                        fillcolor="rgba(121,134,203,0.10)"))
            fig_b.add_trace(go.Scatter(x=bdry.index, y=bdry.rolling(50).mean(),
                                        name="MA50", line=dict(color="#8b949e",
                                                               width=1.2, dash="dot")))
            fig_b.update_layout(height=300, title="BDRY – Dry Bulk ETF", **CHART_BASE)
            fig_b.update_yaxes(gridcolor="rgba(255,255,255,0.07)")
            st.plotly_chart(fig_b, use_container_width=True)
            v = bdry.iloc[-1]; d = (v - bdry.mean()) / bdry.mean() * 100
            (st.success if d > 5 else st.info)(f"BDRY ${v:.2f} ({d:+.1f}% vs avg)")
        else:
            st.warning("Không có dữ liệu BDRY")


# ══════════════════════════════════════════════════════════════════════════════════
#  TAB 3 – MSH CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("<div class='section-title'>🏭 May Sông Hồng – Khách hàng</div>",
                unsafe_allow_html=True)
    st.markdown("<div class='sub-note'>Mỗi card: Annual DIO từ 2020 + Quarterly trend + Revenue + Giá CP</div>",
                unsafe_allow_html=True)
    for tk, nm, role, seg in MSH_CUSTOMERS:
        render_customer_card(tk, nm, role, seg)


# ══════════════════════════════════════════════════════════════════════════════════
#  TAB 4 – TNG CUSTOMERS
# ══════════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("<div class='section-title'>👕 TNG Thái Nguyên – Khách hàng</div>",
                unsafe_allow_html=True)
    st.markdown("<div class='sub-note'>Mỗi card: Annual DIO từ 2020 + Quarterly trend + Revenue + Giá CP</div>",
                unsafe_allow_html=True)
    for tk, nm, role, seg in TNG_CUSTOMERS:
        render_customer_card(tk, nm, role, seg)

    st.divider()
    st.markdown("#### Inditex / Zara (ITX.MC – Sàn Madrid)")
    with st.spinner("Inditex..."):
        itx = stock_price("ITX.MC")
    if itx is not None and len(itx) > 10:
        st.plotly_chart(chart_price(itx, "ITX.MC", "#e040fb"), use_container_width=True)
    with st.expander("ℹ️ Decathlon & nguồn theo dõi thủ công"):
        st.markdown("""
| Công ty | Nguồn IR | Ghi chú |
|---------|---------|---------|
| **Decathlon** | decathlongroup.com → Investors | Private – chỉ có Annual Report |
| **Inditex** | inditex.com/investors | Niêm yết Madrid (ITX.MC) |
| **H&M** | hmgroup.com/investors | Niêm yết Stockholm (HM-B.ST) |
        """)


# ══════════════════════════════════════════════════════════════════════════════════
#  TAB 5 – SIGNAL BOARD
# ══════════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("<div class='section-title'>🚦 Bảng Tín hiệu Tổng hợp</div>",
                unsafe_allow_html=True)

    st.markdown("### 🌐 Macro")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        ct = stock_price("CT=F")
        if ct is not None and len(ct) > 2:
            v = ct.iloc[-1]; d = (v - ct.mean()) / ct.mean() * 100
            st.metric("🌾 Cotton", f"{v:.1f}¢", f"{d:+.1f}% vs avg", delta_color="inverse")
        else:
            st.metric("🌾 Cotton", "N/A")
    with m2:
        rs, _ = fred_series("MRTSSM4481USS", fred_key, START_MACRO)
        if rs is not None and len(rs) >= 3:
            pos = sum(1 for v in rs.pct_change().dropna().tail(3) if v > 0)
            st.metric("🛍️ Retail Sales", f"Tăng {pos}/3T",
                      f"${rs.iloc[-1]/1e3:.1f}B",
                      delta_color="normal" if pos >= 2 else "inverse")
        else:
            st.metric("🛍️ Retail Sales", "Cần FRED Key")
    with m3:
        pm, _ = fred_series("IPMAN", fred_key, START_MACRO)
        if pm is not None:
            v = pm.iloc[-1]
            yoy = (v - pm.iloc[-13]) / pm.iloc[-13] * 100 if len(pm) > 13 else 0
            st.metric("🏭 Sản xuất CN (IPMAN)", f"{v:.1f}",
                      f"YoY {yoy:+.1f}%",
                      delta_color="normal" if yoy >= 0 else "inverse")
        else:
            st.metric("🏭 IPMAN", "Cần FRED Key")
    with m4:
        bd = stock_price("BDRY")
        if bd is not None and len(bd) > 2:
            v = bd.iloc[-1]; d = (v - bd.mean()) / bd.mean() * 100
            st.metric("🚢 BDRY", f"${v:.2f}", f"{d:+.1f}%")
        else:
            st.metric("🚢 BDRY", "N/A")

    st.divider()
    for grp_label, customers in [("🏭 MSH", MSH_CUSTOMERS), ("👕 TNG", TNG_CUSTOMERS)]:
        st.markdown(f"### {grp_label}")
        cols = st.columns(len(customers))
        for i, (tk, nm, _, _) in enumerate(customers):
            df_a = get_annual_financials(tk)
            df_q = get_quarterly_financials(tk)
            dio_chg, dio_lbl, _ = dio_signal(df_a)
            inv_pct, inv_lbl, _ = inv_yoy(df_q)
            rev_pct, rev_lbl, _ = rev_yoy(df_q)
            sig_txt, sig_cls    = overall_signal(dio_chg, inv_pct, rev_pct)
            dc = "normal" if "Tích" in sig_txt else "inverse" if "Tiêu" in sig_txt else "off"
            with cols[i]:
                st.metric(
                    label=tk,
                    value=sig_txt,
                    delta=f"DIO {dio_lbl} | Inv {inv_lbl} | Rev {rev_lbl}",
                    delta_color=dc,
                )
                st.caption(nm)
        st.divider()

    with st.expander("📖 Hướng dẫn"):
        st.markdown("""
| Score | Tín hiệu | Hành động |
|-------|----------|-----------|
| DIO ↓ & Inv ↓ & Rev ↑ | 🟢 Tích cực | Tích lũy MSH/TNG |
| Hỗn hợp | 🟡 Trung tính | Quan sát 1–2 quý |
| DIO ↑ hoặc Rev ↓ mạnh | 🔴 Tiêu cực | Thận trọng |

**DIO = Days Inventory Outstanding.** Giảm YoY → khách hàng đang bán tốt → chuẩn bị đặt thêm hàng.
        """)
