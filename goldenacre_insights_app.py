"""Golden Acre Foods brand analytics - standalone local Streamlit app, mirroring
vithit_insights_app.py's structure and boilerplate exactly, restructured into a
left-nav multi-page shell so it reads as the same product as the static HTML
report's left-nav app shell (see multi-agents/scripts's html build).

Run with: streamlit run goldenacre_insights_app.py

All analytics/data-access logic lives in
multi-agents/scripts/goldenacre_analytics_engine.py - this file is UI only, it
never computes a number itself. Styling lives in goldenacre_theme.py. The live
Q&A assistant ("Sprout") lives in goldenacre_pulp.py, and is now a full nav
page rather than a corner popover - the real, working chat, promoted to first-class
status since a full page reads as more "Claude-like" than a widget in a corner.

Source: GOLDENACRE.TRANSFORM.HC_MASTER - Optia's additive HC_ harmonisation
layer (see multi-agents/docs/goldenacre/), never the client's original
sqlmesh-managed production pipeline.
"""
import os

# Must run before any import that might touch Python's ssl module - see the
# identical comment in vithit_insights_app.py for why.
os.environ.pop("SSLKEYLOGFILE", None)

import sys

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, r"c:\Users\helen\Projects\snowflake\multi-agents\scripts")
import goldenacre_analytics_engine as engine
import goldenacre_pulp
from goldenacre_theme import (
    inject_global_css, render_header, render_hero, render_metric_tile, render_badge,
    render_insight_card, render_sidebar_brand, COLORS, RETAILER_COLOR, RETAILER_LABEL,
    CATEGORY_COLOR, CATEGORY_LABEL,
)

load_dotenv()

st.set_page_config(page_title="Golden Acre Foods - Retail Analytics", layout="wide", page_icon="\U0001F4CA")


def check_password():
    def password_entered():
        st.session_state["authenticated"] = st.session_state["password_input"] == os.environ.get("DASHBOARD_PASSWORD")

    if st.session_state.get("authenticated"):
        return True
    st.text_input("Password", type="password", on_change=password_entered, key="password_input")
    if "authenticated" in st.session_state and not st.session_state["authenticated"]:
        st.error("Incorrect password")
    return False


if not check_password():
    st.stop()

st.markdown(inject_global_css(), unsafe_allow_html=True)


# ---------- cached wrappers around the analytics engine (UI-layer caching only) ----------

@st.cache_resource(ttl=1800)
def conn():
    return engine.connection()


@st.cache_data(ttl=600)
def cached_kpis():
    return engine.load_kpis(conn())


@st.cache_data(ttl=600)
def cached_retailer_share():
    return engine.load_retailer_share(conn())


@st.cache_data(ttl=600)
def cached_category_share():
    return engine.load_category_share(conn())


@st.cache_data(ttl=600)
def cached_top_brands():
    return engine.load_top_brands(conn())


@st.cache_data(ttl=600)
def cached_treemap(retailer):
    return engine.load_treemap(conn(), retailer=retailer)


@st.cache_data(ttl=600)
def cached_monthly_trend():
    return engine.load_monthly_trend(conn())


@st.cache_data(ttl=600)
def cached_predictions():
    return engine.load_predictions(conn())


kpis = cached_kpis()
retailer_share = cached_retailer_share()
category_share = cached_category_share()
top_brands = cached_top_brands()
monthly_trend = cached_monthly_trend()
predictions = cached_predictions()

# ---------- left-nav sidebar ----------
PAGES = ["Overview", "Market Share", "Top Brands", "Brand Map", "Trend", "Predictions", "Insights", "Ask Sprout"]
with st.sidebar:
    st.markdown(render_sidebar_brand(), unsafe_allow_html=True)
    page = st.radio("Navigate", PAGES, label_visibility="collapsed")
    st.markdown(
        f"<div style='margin-top:24px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.14);"
        f"font-size:11px;color:rgba(255,255,255,0.55);'>ASDA &middot; Morrisons &middot; Sainsbury's &middot; Tesco</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    render_header(
        scope_note=(
            "ASDA, Morrisons, Sainsbury's, Tesco - Halal / Polish / World Foods categories. "
            "Source: Optia's harmonised HC_ layer, additive to Golden Acre's existing production pipeline."
        )
    ),
    unsafe_allow_html=True,
)


# ============================================================ Overview ============================================================
if page == "Overview":
    st.markdown(
        render_hero(
            "Retail Performance Analytics",
            "Built on Optia's harmonised <code>HC_MASTER</code> data layer - every figure here is "
            "computed live from Snowflake, the same source and logic independently QA-verified for "
            "the delivered analytics report.",
        ),
        unsafe_allow_html=True,
    )
    st.subheader("Headline performance - latest MAT vs. prior year")
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1:
        st.markdown(render_metric_tile(
            "Value sales (MAT)", f"£{kpis['value_sales_mat']/1e9:.2f}bn",
            f"{kpis['value_sales_change_pct']:+.1f}%", kpis["value_sales_change_pct"] > 0,
            f"vs £{kpis['value_sales_mat_ya']/1e9:.2f}bn MAT YA",
        ), unsafe_allow_html=True)
    with k2:
        st.markdown(render_metric_tile(
            "Unit sales (MAT)", f"{kpis['unit_sales_mat']/1e6:.0f}m",
            f"{kpis['unit_sales_change_pct']:+.1f}%", kpis["unit_sales_change_pct"] > 0,
            f"vs {kpis['unit_sales_mat_ya']/1e6:.0f}m MAT YA",
        ), unsafe_allow_html=True)
    with k3:
        st.markdown(render_metric_tile("Avg price per unit", f"£{kpis['avg_price_per_unit_mat']:.2f}", sub="value / unit sales, MAT"), unsafe_allow_html=True)
    with k4:
        st.markdown(render_metric_tile("Distinct products", f"{kpis['distinct_products_mat']:,}", sub="by barcode, MAT"), unsafe_allow_html=True)
    with k5:
        st.markdown(render_metric_tile("Distinct brands", f"{kpis['distinct_brands_mat']:,}", sub="reference-matched + retailer-labelled"), unsafe_allow_html=True)
    with k6:
        st.markdown(render_metric_tile(
            "Reference match (rows)", f"{kpis['reference_match_pct_mat_rows']:.1f}%",
            sub=f"{kpis['unmatched_value_sales_mat_pct']:.1f}% of MAT value unmatched",
        ), unsafe_allow_html=True)

# ============================================================ Market Share ============================================================
elif page == "Market Share":
    st.subheader("Value sales by retailer & category")
    share_col, cat_col = st.columns(2)
    with share_col:
        st.markdown("**By retailer**")
        df = retailer_share.copy()
        df["label"] = df.retailer.map(RETAILER_LABEL)
        fig = px.bar(
            df.sort_values("value_sales_mat"), x="value_sales_mat", y="label", orientation="h",
            color="retailer", color_discrete_map=RETAILER_COLOR,
            labels={"value_sales_mat": "Value sales (MAT, £)", "label": ""},
            text=df.sort_values("value_sales_mat")["share_pct"].map(lambda v: f"{v:.1f}%"),
        )
        fig.update_layout(showlegend=False, plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=280, margin=dict(l=0, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    with cat_col:
        st.markdown("**By category**")
        st.caption("\"Unclassified\" is not a business category - it's the share of value sales with no product-reference match at all.")
        df = category_share.copy()
        df["label"] = df.category.map(CATEGORY_LABEL)
        fig = px.bar(
            df, x="value_sales_mat", y=[""] * len(df), orientation="h", color="category",
            color_discrete_map=CATEGORY_COLOR, labels={"value_sales_mat": "Value sales (MAT, £)"},
            text=df["share_pct"].map(lambda v: f"{v:.1f}%"),
        )
        fig.update_layout(barmode="stack", plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=280, margin=dict(l=0, r=10, t=10, b=10),
                           legend_title_text="")
        st.plotly_chart(fig, use_container_width=True)

# ============================================================ Top Brands ============================================================
elif page == "Top Brands":
    st.subheader("Top 10 brands by value sales")
    st.caption("Brand identity is the reference-matched brand where one exists, otherwise the retailer's own product labelling - so retailer-name entries here are largely private label, not a single manufacturer.")
    df = top_brands.copy()
    fig = px.bar(
        df.sort_values("value_sales_mat"), x="value_sales_mat", y="brand", orientation="h",
        labels={"value_sales_mat": "Value sales (MAT, £)", "brand": ""},
    )
    fig.update_traces(marker_color=COLORS["primary"])
    fig.update_layout(showlegend=False, plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=420, margin=dict(l=0, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

# ============================================================ Brand Map ============================================================
elif page == "Brand Map":
    st.subheader("Category & brand map")
    st.caption("Tile size = MAT value sales. Colour = change vs. prior MAT. Golden Acre's data has no geographic dimension, so this treemap is the report's \"map\".")
    retailer_choice = st.selectbox("Retailer", ["All retailers"] + [RETAILER_LABEL[r] for r in engine.RETAILERS])
    retailer_key = None if retailer_choice == "All retailers" else next(r for r in engine.RETAILERS if RETAILER_LABEL[r] == retailer_choice)
    tree_df = cached_treemap(retailer_key)
    tree_df["category_label"] = tree_df.category.map(CATEGORY_LABEL)
    fig = px.treemap(
        tree_df, path=["category_label", "brand"], values="value_sales_mat", color="change_pct",
        color_continuous_scale=["#B23A3A", "#D8D5CB", "#1F7A45"], color_continuous_midpoint=0,
        labels={"change_pct": "% change vs MAT YA"},
    )
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)

# ============================================================ Trend ============================================================
elif page == "Trend":
    st.subheader("Monthly value sales")
    trend_view = st.radio("View", ["Total", "By retailer"], horizontal=True)
    mt = monthly_trend.copy()
    mt["date"] = pd.to_datetime(dict(year=mt.YEAR, month=mt.MONTH_NUMBER, day=1))
    if trend_view == "Total":
        agg = mt.groupby("date", as_index=False).agg(VALUE_SALES=("VALUE_SALES", "sum"), PARTIAL_MONTH=("PARTIAL_MONTH", "max"))
        fig = px.line(agg, x="date", y="VALUE_SALES", labels={"VALUE_SALES": "Value sales (£)", "date": ""})
        fig.update_traces(line_color=COLORS["primary"])
    else:
        mt["label"] = mt.RETAILER.map(RETAILER_LABEL)
        fig = px.line(mt, x="date", y="VALUE_SALES", color="RETAILER", color_discrete_map=RETAILER_COLOR,
                      labels={"VALUE_SALES": "Value sales (£)", "date": "", "RETAILER": ""})
    fig.update_layout(plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=440, margin=dict(l=0, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("The final month is a partial period (data cuts off mid-month) - treat it as incomplete, not a real month-on-month drop.")

# ============================================================ Predictions ============================================================
elif page == "Predictions":
    st.subheader("Trailing 12-week momentum")
    st.caption("A naive straight-line fit over the last 12 weeks, expressed as %/week - a directional read, not a statistical forecast. R² tells you how much to trust the direction.")
    name_map = {**RETAILER_LABEL, **CATEGORY_LABEL, "TOTAL": "Total"}
    for row_start in range(0, len(predictions), 3):
        cols = st.columns(3)
        for col, (_, row) in zip(cols, predictions.iloc[row_start:row_start + 3].iterrows()):
            with col:
                slope = row.slope_pct_per_week
                r2 = row.r_squared
                fit = "n/a" if r2 is None else ("Strong" if r2 >= 0.6 else "Moderate" if r2 >= 0.3 else "Weak")
                st.metric(name_map.get(row.series, row.series), f"{slope:+.1f}%/wk" if slope is not None else "n/a",
                          help=f"R²={r2:.2f}, {fit} fit, {row.weeks_used} weeks" if r2 is not None else "insufficient data")

# ============================================================ Insights ============================================================
elif page == "Insights":
    st.subheader("Actionable insights")
    price_mat = kpis["avg_price_per_unit_mat"]
    price_mat_ya = kpis["value_sales_mat_ya"] / kpis["unit_sales_mat_ya"] if kpis["unit_sales_mat_ya"] else None
    price_change = engine.pct_change(price_mat, price_mat_ya) if price_mat_ya else None
    insights_html = [
        (f"<strong>Overall value sales are down {abs(kpis['value_sales_change_pct']):.1f}% MAT vs. MAT YA</strong> "
         f"(£{kpis['value_sales_mat']/1e9:.2f}bn vs. £{kpis['value_sales_mat_ya']/1e9:.2f}bn). Unit sales fell "
         f"{abs(kpis['unit_sales_change_pct']):.1f}%, while average price per unit "
         f"{'rose' if price_change and price_change > 0 else 'fell'} {abs(price_change):.1f}%"
         if price_change is not None else "") + " - price/mix cushioned part of the volume decline.",
        (f"<strong>{kpis['unmatched_value_sales_mat_pct']:.1f}% of MAT value sales</strong> "
         f"(£{kpis['unmatched_value_sales_mat']/1e9:.2f}bn) sit in products with no product-reference match at all - "
         "the single biggest lever for sharper category reporting is expanding reference-database coverage, not merchandising."),
    ]
    for i, html in enumerate(insights_html, start=1):
        st.markdown(render_insight_card(i, html), unsafe_allow_html=True)

# ============================================================ Ask Sprout (full page, real chat) ============================================================
elif page == "Ask Sprout":
    st.subheader("\U0001F331 Ask Sprout")
    st.caption(
        f"{goldenacre_pulp.NAME} answers only from the data currently loaded in this app - nothing invented. "
        "Switch pages to load different data (e.g. the Brand Map's retailer filter) before asking about it."
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.info(f"{goldenacre_pulp.NAME} isn't switched on yet - add `ANTHROPIC_API_KEY` to `.env` to enable live Q&A.")
    else:
        sprout_context = goldenacre_pulp.build_context(kpis, retailer_share, category_share, top_brands, predictions)

        if "sprout_messages" not in st.session_state:
            st.session_state.sprout_messages = []

        for msg in st.session_state.sprout_messages:
            avatar = goldenacre_pulp.AVATAR_ICON if msg["role"] == "assistant" else None
            with st.chat_message(msg["role"], avatar=avatar):
                st.markdown(msg["content"])

        if len(st.session_state.sprout_messages) >= goldenacre_pulp.MAX_MESSAGES_PER_SESSION:
            st.warning(
                f"This conversation has hit its length limit ({goldenacre_pulp.MAX_MESSAGES_PER_SESSION} "
                f"messages) - refresh the page to start a new one with {goldenacre_pulp.NAME}."
            )

        question = st.chat_input(
            f"Ask {goldenacre_pulp.NAME} about Golden Acre's retail performance...",
            max_chars=goldenacre_pulp.MAX_QUESTION_CHARS,
            disabled=len(st.session_state.sprout_messages) >= goldenacre_pulp.MAX_MESSAGES_PER_SESSION,
        )
        if question:
            st.session_state.sprout_messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant", avatar=goldenacre_pulp.AVATAR_ICON):
                with st.spinner(f"{goldenacre_pulp.NAME} is thinking..."):
                    try:
                        reply = goldenacre_pulp.ask_sprout(question, sprout_context, st.session_state.sprout_messages[:-1])
                    except ValueError as e:
                        reply = f"Couldn't send that: {e}."
                    except Exception as e:
                        reply = f"{goldenacre_pulp.NAME} hit an error and couldn't answer: {e}"
                st.markdown(reply)
            st.session_state.sprout_messages.append({"role": "assistant", "content": reply})
