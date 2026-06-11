"""
Excel InsightForge Agent — main Streamlit application.

Tabs: Overview | KPIs | Charts | AI Summary | Ask Data
Modes: 🟢 AI Mode (Groq key present) | 🟡 Analytics Mode (no key)
"""

from __future__ import annotations

import logging
from typing import Dict

import pandas as pd
import streamlit as st

from config import APP_NAME, APP_SUBTITLE, GROQ_MODEL, PROVIDER, resolve_api_key
from services import ai_service, analytics, dataset_generator, visualization

logger = logging.getLogger("insightforge.app")

st.set_page_config(page_title=APP_NAME, page_icon="📊", layout="wide")


# --------------------------------------------------------------------------- #
# Cached helpers
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Generating demo dataset…")
def cached_demo_workbook() -> Dict[str, pd.DataFrame]:
    return dataset_generator.generate_workbook()


@st.cache_data(show_spinner="Reading Excel file…")
def read_excel(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    import io

    xls = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    return {name: xls.parse(name) for name in xls.sheet_names}


@st.cache_data(show_spinner="Computing KPIs…")
def cached_kpis(_sheets: Dict[str, pd.DataFrame], cache_key: str):
    return analytics.generate_kpis(_sheets)


# --------------------------------------------------------------------------- #
# Sidebar — AI configuration
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("🤖 AI Configuration")
    st.text(f"Provider: {PROVIDER}")
    st.text(f"Model: {GROQ_MODEL}")
    sidebar_key = st.text_input(
        "API Key", type="password",
        help="Groq API key. Leave empty to use .env / env var / Analytics Mode.",
    )
    cfg = resolve_api_key(sidebar_key)
    if cfg.ai_enabled:
        st.success("🟢 AI Enabled")
        st.caption(f"Status: AI Mode • {PROVIDER} • {GROQ_MODEL}")
    else:
        st.warning("🟡 Analytics Mode")
        st.caption("No AI services configured — all analytics still work.")

    st.divider()
    st.caption("FDP Demo • Agentic AI → Docker → Kubernetes → ArgoCD")


# --------------------------------------------------------------------------- #
# Header & data input
# --------------------------------------------------------------------------- #
st.title(f"📊 {APP_NAME}")
st.caption(APP_SUBTITLE)

col_u, col_d = st.columns([2, 1])
with col_u:
    uploaded = st.file_uploader("Upload Excel", type=["xlsx", "xls"])
with col_d:
    st.write("")
    if st.button("✨ Generate Demo Dataset", use_container_width=True):
        st.session_state["use_demo"] = True
        st.session_state.pop("uploaded_name", None)

sheets: Dict[str, pd.DataFrame] | None = None
source_label = ""

if uploaded is not None:
    try:
        sheets = read_excel(uploaded.getvalue())
        source_label = uploaded.name
        st.session_state["use_demo"] = False
        st.session_state["uploaded_name"] = uploaded.name
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read Excel file: {exc}")
elif st.session_state.get("use_demo"):
    sheets = cached_demo_workbook()
    source_label = "Global E-Commerce Analytics (demo)"

if sheets is None:
    st.info("⬆️ Upload an Excel file or click **Generate Demo Dataset** to begin.")
    st.stop()

st.success(f"Loaded **{source_label}** — {len(sheets)} sheet(s).")

if st.session_state.get("use_demo"):
    st.download_button(
        "⬇️ Download Dataset (.xlsx)",
        data=dataset_generator.workbook_to_excel_bytes(sheets),
        file_name="global_ecommerce_analytics.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

kpis = cached_kpis(sheets, source_label)
profiles = analytics.profile_workbook(sheets)

tab_overview, tab_kpi, tab_charts, tab_ai, tab_ask = st.tabs(
    ["📋 Overview", "📈 KPIs", "📊 Charts", "🧠 AI Summary", "💬 Ask Data"]
)

# --------------------------------------------------------------------------- #
# Tab 1 — Overview
# --------------------------------------------------------------------------- #
with tab_overview:
    for p in profiles:
        with st.expander(
            f"**{p['sheet']}** — {p['rows']:,} rows × {p['columns']} cols "
            f"({p['memory_mb']} MB)",
            expanded=False,
        ):
            c1, c2, c3 = st.columns(3)
            c1.metric("Missing values %", f"{p['missing_pct']}%")
            c2.metric("Duplicate rows", p["duplicate_rows"])
            c3.metric("Columns", p["columns"])
            if p["missing"]:
                st.write("**Columns with missing values:**", p["missing"])
            st.write("**Data types:**")
            st.json(p["dtypes"], expanded=False)
            st.dataframe(sheets[p["sheet"]].head(10), use_container_width=True)

# --------------------------------------------------------------------------- #
# Tab 2 — KPIs
# --------------------------------------------------------------------------- #
with tab_kpi:
    pub = {k: v for k, v in kpis.items() if not k.startswith("_")}
    if not pub:
        st.info("No business KPIs detected (need revenue/profit-like columns).")
    else:
        cols = st.columns(4)
        simple = [
            ("total_revenue", "Total Revenue", "{:,.0f}"),
            ("total_profit", "Total Profit", "{:,.0f}"),
            ("profit_margin_pct", "Profit Margin", "{}%"),
            ("growth_pct", "Growth", "{}%"),
            ("avg_order_value", "Avg Order Value", "{:,.2f}"),
            ("marketing_roi", "Marketing ROI", "{}x"),
            ("total_customers", "Customers", "{:,}"),
            ("items_below_reorder_point", "SKUs Below Reorder", "{}"),
        ]
        i = 0
        for key, label, fmt in simple:
            if key in pub:
                cols[i % 4].metric(label, fmt.format(pub[key]))
                i += 1
        st.divider()
        c1, c2 = st.columns(2)
        if "top_products" in pub:
            c1.subheader("🏆 Top Products")
            c1.dataframe(
                pd.Series(pub["top_products"], name="revenue"),
                use_container_width=True,
            )
        if "top_regions" in pub:
            c2.subheader("🌍 Top Regions")
            c2.dataframe(
                pd.Series(pub["top_regions"], name="revenue"),
                use_container_width=True,
            )
        if "region_margins_pct" in pub:
            st.subheader("⚠️ Region Margins (lowest first)")
            st.dataframe(
                pd.Series(pub["region_margins_pct"], name="margin %"),
                use_container_width=True,
            )
        if "channel_roi" in pub:
            st.subheader("📣 Marketing Channel ROI")
            st.dataframe(
                pd.Series(pub["channel_roi"], name="ROI (x)"),
                use_container_width=True,
            )

# --------------------------------------------------------------------------- #
# Tab 3 — Charts
# --------------------------------------------------------------------------- #
with tab_charts:
    rev_sheet = kpis.get("_revenue_sheet")
    rev_col = kpis.get("_revenue_col")
    if rev_sheet and rev_col:
        df = sheets[rev_sheet]
        c1, c2 = st.columns(2)
        region_col = analytics._find_col(df, analytics.REGION_KEYS, numeric=False)
        product_col = analytics._find_col(df, analytics.PRODUCT_KEYS, numeric=False)
        if region_col:
            c1.plotly_chart(
                visualization.bar_top(df, region_col, rev_col, "Revenue by Region"),
                use_container_width=True,
            )
            c2.plotly_chart(
                visualization.pie_share(df, region_col, rev_col, "Revenue Share"),
                use_container_width=True,
            )
        if product_col:
            st.plotly_chart(
                visualization.bar_top(df, product_col, rev_col, "Top Products"),
                use_container_width=True,
            )
        trend = analytics.monthly_trend(df)
        if trend is not None:
            st.plotly_chart(
                visualization.line_trend(trend, "Monthly Revenue Trend"),
                use_container_width=True,
            )
            fc = visualization.forecast_chart(df, "Revenue Forecast (6 months)")
            if fc:
                st.plotly_chart(fc, use_container_width=True)
        heat = visualization.correlation_heatmap(df, f"Correlations — {rev_sheet}")
        if heat:
            st.plotly_chart(heat, use_container_width=True)
        anomalies = analytics.detect_anomalies(df)
        if anomalies:
            st.subheader("🚨 Revenue Anomalies")
            st.dataframe(pd.DataFrame(anomalies), use_container_width=True)
    else:
        st.info("No revenue-like column found — charts need sales/revenue data.")

# --------------------------------------------------------------------------- #
# Tab 4 — AI Summary
# --------------------------------------------------------------------------- #
with tab_ai:
    st.caption(f"Status: **{cfg.mode}**")
    if st.button("📝 Generate Executive Summary", type="primary"):
        summary = None
        if cfg.ai_enabled:
            with st.spinner("Groq Llama 3.3 70B is analysing your data…"):
                summary = ai_service.ai_executive_summary(cfg, kpis, profiles)
            if summary is None:
                st.warning("AI call failed — falling back to rule-based summary.")
        if summary is None:
            summary = analytics.rule_based_summary(kpis, sheets)
        st.session_state["summary"] = summary
    if "summary" in st.session_state:
        st.markdown(st.session_state["summary"])

# --------------------------------------------------------------------------- #
# Tab 5 — Ask Data (agentic Q&A)
# --------------------------------------------------------------------------- #
with tab_ask:
    st.subheader("💬 Ask About Your Data")
    st.caption(
        "The agent plans → calls analytics tools → observes → answers. "
        "Expand the trace to see each step (ReAct pattern)."
    )
    examples = [
        "What is driving revenue growth?",
        "Which region is underperforming?",
        "What are the biggest risks?",
        "Which products should be discontinued?",
        "How can management improve profitability?",
    ]
    ex_cols = st.columns(len(examples))
    for i, q in enumerate(examples):
        if ex_cols[i].button(q, key=f"ex{i}", use_container_width=True):
            st.session_state["question"] = q

    question = st.text_input(
        "Your question",
        value=st.session_state.get("question", ""),
        placeholder="e.g. Which marketing channel is wasting budget?",
    )
    if st.button("🤖 Ask Agent", type="primary") and question.strip():
        with st.spinner("Agent is working…"):
            result = ai_service.agentic_answer(cfg, question, sheets, kpis)
        st.markdown(result["answer"])
        if result["steps"]:
            with st.expander(f"🔍 Agent trace — {len(result['steps'])} tool call(s)"):
                for i, s in enumerate(result["steps"], 1):
                    st.markdown(f"**Step {i}:** `{s['tool']}({s['args']})`")
                    st.code(s["observation"], language="json")
