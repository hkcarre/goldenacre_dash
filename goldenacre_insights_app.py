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
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

# Relative to this file, not a hardcoded local path - the original absolute
# Windows path only worked on the machine that wrote it. Streamlit Community
# Cloud clones this repo to a fresh Linux path, so anything hardcoded here
# would crash on import before the app even starts.
_APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_APP_DIR / "multi-agents" / "scripts"))
import goldenacre_analytics_engine as engine
import goldenacre_insight_copy
import goldenacre_pulp

# Optional: the voice feature's dependency chain (kokoro-onnx -> onnxruntime /
# phonemizer-fork / espeakng-loader) is heavier than anything else here and
# hasn't been confirmed to install cleanly on every deploy target - if it's
# unavailable, the rest of the app (including Halal/Polish/Other category
# breakdowns and everything else) must still work. See KOKORO_AVAILABLE below.
try:
    import kokoro_voice
    KOKORO_AVAILABLE = True
except ImportError as _kokoro_import_error:
    kokoro_voice = None
    KOKORO_AVAILABLE = False
    _KOKORO_IMPORT_ERROR = _kokoro_import_error
from goldenacre_theme import (
    inject_global_css, render_header, render_hero, render_metric_tile, render_badge,
    render_insight_card, render_sidebar_brand, render_powered_by_credit, COLORS,
    RETAILER_COLOR, RETAILER_LABEL, CATEGORY_COLOR, CATEGORY_LABEL,
)

load_dotenv()

# On Streamlit Community Cloud there's no .env file - secrets are pasted into
# the app's Secrets panel instead, exposed via st.secrets. Mirror them into
# os.environ so snowflake_connection.py, goldenacre_pulp.py etc. can keep
# reading plain env vars either way, without knowing which environment they're
# in. Wrapped defensively: st.secrets raises if no secrets.toml exists at all
# (the normal case for local dev), which must not crash the app.
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass

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


@st.cache_data(ttl=600)
def cached_manufacturer_view():
    return engine.load_manufacturer_view(conn())


kpis = cached_kpis()
retailer_share = cached_retailer_share()
category_share = cached_category_share()
top_brands = cached_top_brands()
manufacturer_view = cached_manufacturer_view()
monthly_trend = cached_monthly_trend()
predictions = cached_predictions()

# ---------- left-nav sidebar ----------
PAGES = ["Overview", "Market Share", "Top Brands", "Brand Map", "Trend", "Predictions", "Insights", "Golden Acre View", "Ask Sprout"]
with st.sidebar:
    st.markdown(render_sidebar_brand(), unsafe_allow_html=True)
    page = st.radio("Navigate", PAGES, label_visibility="collapsed")
    st.markdown(
        f"<div style='margin-top:24px;padding-top:14px;border-top:1px solid rgba(255,255,255,0.14);"
        f"font-size:11px;color:rgba(255,255,255,0.55);'>ASDA &middot; Morrisons &middot; Sainsbury's &middot; Tesco</div>",
        unsafe_allow_html=True,
    )
    st.markdown(render_powered_by_credit(), unsafe_allow_html=True)

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
            "Built on Optia's harmonised data layer - every figure here is computed live, "
            "and independently verified against source.",
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

    ga_share = manufacturer_view["golden_acre_share"]
    ga_corr = manufacturer_view["najma_rank_correction"]
    st.markdown(
        f"""<div style="margin-top:18px;padding:16px 20px;border-radius:12px;
             background:{COLORS['gold_bg']};border:1px solid {COLORS['gold']};
             display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">
          <div style="font-size:14px;color:{COLORS['text']};">
            <strong>Your brands, in this data.</strong> Najma + Jaldee Eats hold a combined
            <strong>{ga_share['share_mat_pct']:.1f}% share of Halal</strong>
            ({'+' if ga_share['share_point_change'] > 0 else ''}{ga_share['share_point_change']:.2f}pp vs MAT YA).
            Najma ranks <strong>#{ga_corr['corrected_rank']}</strong> among Halal brands at
            £{ga_corr['corrected_value_mat']/1e6:.1f}m &mdash; see Golden Acre View for the full breakdown.
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

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
        st.caption(
            f"Halal, Polish and Other only - shares are of the classified total, not all MAT value. "
            f"Excludes {kpis['unmatched_value_sales_mat_pct']:.1f}% of MAT value "
            f"(£{kpis['unmatched_value_sales_mat']/1e9:.2f}bn) with no product-reference match at all - "
            f"see Insights for that gap."
        )
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

    st.markdown("**Golden Acre's share, by retailer**")
    st.caption("Najma + Jaldee Eats combined, share of each retailer's own Halal category - a different question from the four-retailer totals above.")
    ga_df = pd.DataFrame(manufacturer_view["by_retailer_share"]).sort_values("ga_share_mat_pct", ascending=True)
    ga_df["label"] = ga_df.retailer.map(RETAILER_LABEL)
    fig = px.bar(
        ga_df, x="ga_share_mat_pct", y="label", orientation="h",
        labels={"ga_share_mat_pct": "Golden Acre share of Halal (%)", "label": ""},
        text=ga_df["share_point_change"].map(lambda v: f"{'+' if v > 0 else ''}{v:.2f}pp"),
    )
    fig.update_traces(marker_color=COLORS["gold"])
    fig.update_layout(showlegend=False, plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=240, margin=dict(l=0, r=10, t=10, b=10))
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

    ga_corr = manufacturer_view["najma_rank_correction"]
    st.info(
        f"Neither Najma nor Jaldee Eats appears above - that list ranks brands across ALL categories and is "
        f"dominated by retailers' own private-label buckets, not evidence Golden Acre is a small player. "
        f"Within its own category, Halal, Najma is the **#{ga_corr['corrected_rank']}-largest brand** at "
        f"£{ga_corr['corrected_value_mat']/1e6:.1f}m MAT - see Golden Acre View for the full ranking."
    )

# ============================================================ Brand Map ============================================================
elif page == "Brand Map":
    st.subheader("Category & brand map")
    st.caption("Tile size = MAT value sales. Colour = change vs. prior MAT. Golden Acre's data has no geographic dimension, so this treemap is the report's \"map\".")
    st.caption(
        f"Halal, Polish and Other only - excludes {kpis['unmatched_value_sales_mat_pct']:.1f}% of MAT value "
        f"(£{kpis['unmatched_value_sales_mat']/1e9:.2f}bn) with no product-reference match, so tile sizes don't sum to the KPI total."
    )
    retailer_choice = st.selectbox("Retailer", ["All retailers"] + [RETAILER_LABEL[r] for r in engine.RETAILERS])
    retailer_key = None if retailer_choice == "All retailers" else next(r for r in engine.RETAILERS if RETAILER_LABEL[r] == retailer_choice)
    tree_df = cached_treemap(retailer_key)
    tree_df["category_label"] = tree_df.category.map(CATEGORY_LABEL)

    # Najma's naive GA_BUYER='HALAL' total understates it (see Golden Acre View) -
    # swap in the corrected value/growth here too, so this page agrees with the
    # rest of the app instead of quietly showing the smaller, wrong figure.
    najma_correction = (
        manufacturer_view["najma"] if retailer_key is None
        else next((r for r in manufacturer_view["najma"]["by_retailer"] if r["retailer"] == retailer_key), None)
    )
    najma_mask = tree_df.brand == "NAJMA"
    if najma_correction and najma_mask.any():
        tree_df.loc[najma_mask, "value_sales_mat"] = najma_correction["value_sales_mat"]
        tree_df.loc[najma_mask, "change_pct"] = najma_correction["value_yoy_pct"]
        tree_df.loc[najma_mask, "brand"] = "\U0001F31F Najma (corrected)"

    fig = px.treemap(
        tree_df, path=["category_label", "brand"], values="value_sales_mat", color="change_pct",
        color_continuous_scale=["#B23A3A", "#D8D5CB", "#1F7A45"], color_continuous_midpoint=0,
        labels={"change_pct": "% change vs MAT YA"},
    )
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("\U0001F31F = Golden Acre-owned (Najma), value corrected for the reference-match gap - see Golden Acre View.")

# ============================================================ Trend ============================================================
elif page == "Trend":
    st.subheader("Monthly value sales")
    trend_view = st.radio("View", ["Total", "By retailer", "Golden Acre", "Golden Acre by retailer"], horizontal=True)
    if trend_view in ("Total", "By retailer"):
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
    elif trend_view == "Golden Acre":
        ga_mt = pd.DataFrame(manufacturer_view["trend_monthly_golden_acre"])
        ga_mt["date"] = pd.to_datetime(dict(year=ga_mt.year, month=ga_mt.month, day=1))
        fig = px.line(ga_mt, x="date", y="value_sales", labels={"value_sales": "Najma + Jaldee Eats value sales (£)", "date": ""})
        fig.update_traces(line_color=COLORS["gold"])
    else:
        rows = []
        for ret, points in manufacturer_view["trend_monthly_golden_acre_by_retailer"].items():
            for p in points:
                rows.append({**p, "RETAILER": ret})
        ga_mt = pd.DataFrame(rows)
        ga_mt["date"] = pd.to_datetime(dict(year=ga_mt.year, month=ga_mt.month, day=1))
        fig = px.line(ga_mt, x="date", y="value_sales", color="RETAILER", color_discrete_map=RETAILER_COLOR,
                      labels={"value_sales": "Value sales (£)", "date": "", "RETAILER": ""})
    fig.update_layout(plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=440, margin=dict(l=0, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    if trend_view == "Golden Acre by retailer":
        st.caption("Tesco's line includes Jaldee Eats (Tesco-only); the other three retailers are Najma alone. The final month is a partial period.")
    else:
        st.caption("The final month is a partial period (data cuts off mid-month) - treat it as incomplete, not a real month-on-month drop.")

# ============================================================ Predictions ============================================================
elif page == "Predictions":
    st.subheader("Trailing 12-week momentum")
    st.caption("A naive straight-line fit over the last 12 weeks, expressed as %/week - a directional read, not a statistical forecast. R² tells you how much to trust the direction.")

    st.markdown("**Golden Acre's own momentum**")
    ga_cols = st.columns(3)
    ga_trend = manufacturer_view["trend"]
    for col, (label, key) in zip(ga_cols, [("\U0001F31F Najma", "najma"), ("\U0001F31F Jaldee Eats", "jaldee_eats")]):
        row = ga_trend[key]
        with col:
            slope, r2 = row["slope_pct_per_week"], row["r_squared"]
            fit = "n/a" if r2 is None else ("Strong" if r2 >= 0.6 else "Moderate" if r2 >= 0.3 else "Weak")
            st.metric(label, f"{slope:+.1f}%/wk" if slope is not None else "n/a",
                      help=f"R²={r2:.2f}, {fit} fit, {row['weeks_used']} weeks" if r2 is not None else "insufficient data")
    cat_row = ga_trend["category"]
    st.caption(
        f"Halal category overall is at {cat_row['slope_pct_per_week']:+.1f}%/wk (R²={cat_row['r_squared']:.2f}) - "
        "Najma's decline is shallower than the category's, consistent with the share gain in Golden Acre View."
    )
    st.markdown("---")
    st.markdown("**Retailer & category momentum**")
    st.caption("Category momentum is Halal, Polish and Other only - unmatched-to-reference product rows have no stable category to trend, so they're excluded here (Total and each retailer's momentum above still include them).")
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
    # Shared with the audio builder so the clips speak these exact strings -
    # see goldenacre_insight_copy's docstring for why it sits at the repo root.
    insight_cards = goldenacre_insight_copy.build_insight_texts(kpis, manufacturer_view)
    def listen_button(key, html):
        """Lazy: only synthesizes on click, then stays visible across reruns via
        session_state - avoids paying Kokoro's generation cost (roughly the
        clip's own duration, on a free-tier vCPU) for every insight on every
        page load, only for ones actually asked for.

        Wrapped in a keyed container so the theme can style just this control
        and its audio player - see the "st-key-ga-listen-" rules in
        goldenacre_theme.inject_global_css."""
        if not KOKORO_AVAILABLE:
            return
        # to_speech(), not strip_html(): the card's shorthand ("MAT vs. MAT YA",
        # "£2.52bn") is written to be read, and the first deployed version voiced
        # it literally.
        speech = kokoro_voice.to_speech(html)
        if not kokoro_voice.can_speak(speech):
            return
        with st.container(key=f"ga-listen-{key}"):
            label = "\U0001F50A Listen" if kokoro_voice.has_clip(speech) else "\U0001F50A Listen (~30s)"
            if st.button(label, key=f"listen_{key}"):
                st.session_state[f"audio_{key}"] = True
            if st.session_state.get(f"audio_{key}"):
                # autoplay: the click already expressed the intent, so making the
                # user press play again after a wait is a second tax.
                st.audio(kokoro_voice.audio_wav(speech), format="audio/wav", autoplay=True)

    icons = {"insight_ga": "\U0001F31F", "insight_extras": "\U0001F50D"}
    for n, (key, html) in enumerate(insight_cards, start=1):
        st.markdown(render_insight_card(icons.get(key, n), html), unsafe_allow_html=True)
        listen_button(key, html)

# ============================================================ Golden Acre View ============================================================
elif page == "Golden Acre View":
    st.subheader("Golden Acre's own brands vs. the market")
    st.caption(
        "Everything on the other pages treats Golden Acre as the analytics platform, not a competitor. This page "
        "flips the lens. Najma and Jaldee Eats sit in Halal and form the competitive set below; The Hungry Boar "
        "and the distributed X Energy sit outside Halal and are shown separately under \"the rest of the portfolio\". "
        "Elsinore, Acti-Shake and Golden Acre Yogurts don't appear in this data at all - none of their stockists "
        "are ASDA, Morrisons, Sainsbury's or Tesco."
    )

    ga_share = manufacturer_view["golden_acre_share"]
    ga_corr = manufacturer_view["najma_rank_correction"]
    najma, jaldee = manufacturer_view["najma"], manufacturer_view["jaldee_eats"]
    ref_match = manufacturer_view["najma_reference_match"]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(render_metric_tile(
            "Combined share of Halal", f"{ga_share['share_mat_pct']:.1f}%",
            f"{'+' if ga_share['share_point_change'] > 0 else ''}{ga_share['share_point_change']:.2f}pp", ga_share["share_point_change"] > 0,
            f"vs {ga_share['share_mat_ya_pct']:.1f}% MAT YA",
        ), unsafe_allow_html=True)
    with m2:
        st.markdown(render_metric_tile(
            "Najma value sales (MAT)", f"£{najma['value_sales_mat']/1e6:.1f}m",
            f"{najma['value_yoy_pct']:+.1f}%", najma["value_yoy_pct"] > 0,
            f"rank #{ga_corr['corrected_rank']} of Halal brands (corrected)",
        ), unsafe_allow_html=True)
    with m3:
        st.markdown(render_metric_tile(
            "Jaldee Eats value sales (MAT)", f"£{jaldee['value_sales_mat']/1e3:.0f}k",
            f"{jaldee['value_yoy_pct']:+.1f}%", jaldee["value_yoy_pct"] > 0,
            "Tesco only - 1 of 4 retailers",
        ), unsafe_allow_html=True)
    with m4:
        st.markdown(render_metric_tile(
            "Najma's reference-match rate", f"{ref_match['matched_pct']:.1f}%",
            sub=f"{100 - ref_match['matched_pct']:.1f}% relies on raw retailer text",
        ), unsafe_allow_html=True)

    st.markdown("**Where Najma really ranks**")
    st.caption("Top Halal brands by MAT value sales. Golden Acre's own brand highlighted.")
    rank_df = pd.DataFrame(manufacturer_view["competitive_set_top12"])
    rank_df["label"] = rank_df.apply(lambda r: f"#{r['rank']} {r['brand']}" + (" \U0001F31F" if r["is_golden_acre"] else ""), axis=1)
    fig = px.bar(
        rank_df.sort_values("rank", ascending=False), x="value_sales_mat", y="label", orientation="h",
        color="is_golden_acre", color_discrete_map={True: COLORS["gold"], False: COLORS["primary"]},
        labels={"value_sales_mat": "Value sales (MAT, £)", "label": ""},
    )
    fig.update_layout(showlegend=False, plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=420, margin=dict(l=0, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    next_brand = next((r for r in manufacturer_view["competitive_set_top12"] if r["rank"] == ga_corr["corrected_rank"] + 1), None)
    st.info(
        f"**Najma's true rank is #{ga_corr['corrected_rank']}, not #{ga_corr['naive_rank']}.** "
        f"{ref_match['matched_pct']:.1f}% of Najma's sales sit on the clean, reference-matched \"NAJMA\" brand string "
        f"(£{ga_corr['naive_value_mat']/1e6:.1f}m MAT) - a plain query stops there and ranks Najma #{ga_corr['naive_rank']}. "
        f"The remaining {100 - ref_match['matched_pct']:.1f}% sits on SKUs like \"NAJMA HALAL TURKEY\" that failed the same "
        f"product-reference match - and because category comes from that same match, they also get mis-bucketed as "
        f"\"Unclassified\" instead of Halal. Folding Najma's brand family back together gives its real MAT value of "
        f"£{ga_corr['corrected_value_mat']/1e6:.1f}m - #{ga_corr['corrected_rank']}"
        + (f", ahead of {next_brand['brand']} (£{next_brand['value_sales_mat']/1e6:.1f}m)." if next_brand else ".") +
        " The same correction is applied identically to every brand in the chart above, not just Najma."
    )

    st.markdown("**Retailer distribution & share**")
    st.caption("Najma + Jaldee Eats combined, share of each retailer's own Halal category.")
    dist_df = pd.DataFrame(manufacturer_view["by_retailer_share"])
    dist_df["Retailer"] = dist_df.retailer.map(RETAILER_LABEL)
    dist_df["Halal category (MAT)"] = dist_df.category_value_mat.map(lambda v: f"£{v/1e6:.1f}m")
    dist_df["Category YoY"] = dist_df.category_value_yoy_pct.map(lambda v: f"{v:+.1f}%")
    dist_df["Golden Acre value (MAT)"] = dist_df.ga_value_mat.map(lambda v: f"£{v/1e6:.1f}m")
    dist_df["GA share (MAT)"] = dist_df.ga_share_mat_pct.map(lambda v: f"{v:.1f}%")
    dist_df["GA share (MAT YA)"] = dist_df.ga_share_mat_ya_pct.map(lambda v: f"{v:.1f}%")
    dist_df["Share change"] = dist_df.share_point_change.map(lambda v: f"{'+' if v > 0 else ''}{v:.2f}pp")
    st.dataframe(
        dist_df[["Retailer", "Halal category (MAT)", "Category YoY", "Golden Acre value (MAT)", "GA share (MAT)", "GA share (MAT YA)", "Share change"]],
        hide_index=True, use_container_width=True,
    )

    st.markdown("**Price positioning**")
    st.caption("Value ÷ unit sales, MAT. Golden Acre's own brand highlighted.")
    price_df = rank_df[rank_df.price_per_unit.notna()].head(7)
    fig = px.bar(
        price_df.sort_values("price_per_unit"), x="price_per_unit", y="brand", orientation="h",
        color="is_golden_acre", color_discrete_map={True: COLORS["gold"], False: COLORS["teal"]},
        labels={"price_per_unit": "Price per unit (£)", "brand": ""},
    )
    fig.update_layout(showlegend=False, plot_bgcolor=COLORS["card"], paper_bgcolor=COLORS["card"], height=320, margin=dict(l=0, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Najma and Lancashire Farm price well below Shazans/Haji Baba/Tariq Halal - a lower-unit-price, higher-volume segment within Halal, not evidence either pricing strategy is \"wrong\".")

    st.markdown("**Whitespace**")
    st.info(
        f"**Jaldee Eats is Golden Acre's newest halal range and is sold through Tesco only** "
        f"(£{jaldee['value_sales_mat']/1e3:.0f}k MAT, {jaldee['value_yoy_pct']:+.1f}% YoY). It has no presence in "
        "ASDA, Morrisons or Sainsbury's, the same three retailers where Najma is already listed and gaining share. "
        "That is a plausible listing-expansion opportunity, not a demand problem this data can diagnose on its own."
    )

    # Everything above is the Halal competitive set. These two brands are Golden
    # Acre's too but sit outside Halal, so they'd otherwise be invisible on every
    # page - including the Halal/Polish/Other category views, since both fall in
    # the unclassified reference-match bucket.
    extras = manufacturer_view["portfolio_extras"]
    if extras["owned_extra"] or extras["distributed"]:
        st.markdown("**The rest of the portfolio**")
        st.caption(
            "Golden Acre lines outside the Halal category, so neither appears in the competitive set above."
        )
        pcols = st.columns(max(2, len(extras["owned_extra"]) + len(extras["distributed"])))
        idx = 0
        for row in extras["owned_extra"]:
            with pcols[idx]:
                st.markdown(render_metric_tile(
                    f"{row['brand'].title()} (MAT)", f"£{row['value_sales_mat']/1e3:.0f}k",
                    f"{row['value_yoy_pct']:+.1f}%", row["value_yoy_pct"] > 0,
                    f"Own brand - {', '.join(RETAILER_LABEL.get(r, r) for r in row['retailers'])}",
                ), unsafe_allow_html=True)
            idx += 1
        for row in extras["distributed"]:
            with pcols[idx]:
                st.markdown(render_metric_tile(
                    f"{row['brand'].title()} (MAT)", f"£{row['value_sales_mat']/1e3:.0f}k",
                    f"{row['value_yoy_pct']:+.1f}%", row["value_yoy_pct"] > 0,
                    f"Distributed, not owned - {', '.join(RETAILER_LABEL.get(r, r) for r in row['retailers'])}",
                ), unsafe_allow_html=True)
            idx += 1
        st.info(
            f"**These are the fastest-growing lines in the portfolio.** Together they are "
            f"£{(extras['owned_extra_total_mat'] + extras['distributed_total_mat'])/1e3:.0f}k MAT, and because both sit "
            "outside Halal, Polish and Other, neither shows up in any category view. X Energy is deliberately excluded "
            "from the combined-share figure at the top of this page: Golden Acre distributes it rather than owning it, "
            "so counting it would overstate own-brand share."
        )

# ============================================================ Ask Sprout (full page, real chat) ============================================================
elif page == "Ask Sprout":
    st.subheader("\U0001F331 Ask Sprout")
    st.caption(
        f"{goldenacre_pulp.NAME} answers only from the data loaded into its context below - nothing invented. "
        "KPIs, retailer/category share, top brands, predictions, and Golden Acre's own brand figures are all "
        "in scope. The Brand Map's category/brand breakdown is a page-only chart and isn't loaded here yet - "
        f"{goldenacre_pulp.NAME} will say so rather than guess if you ask about it."
    )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        # Name the right place for the environment actually being run. The old
        # wording said ".env" unconditionally, which is wrong on Streamlit Cloud
        # (no filesystem to put one on) and sends you looking in the wrong place.
        _on_cloud = bool(os.environ.get("HOSTNAME", "").startswith("streamlit")) or Path("/mount/src").exists()
        _where = ("this app's **Settings -> Secrets** panel on Streamlit Cloud"
                  if _on_cloud else "`.env` in the project root")
        st.info(
            f"{goldenacre_pulp.NAME} isn't switched on yet - add `ANTHROPIC_API_KEY` to {_where} "
            "to enable live Q&A. Every other page works without it."
        )
    else:
        sprout_context = goldenacre_pulp.build_context(kpis, retailer_share, category_share, top_brands, predictions, manufacturer_view)

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
                        # ValueError is about the user's own input (empty/too
                        # long), so it is safe and useful to show verbatim.
                        reply = f"Couldn't send that: {e}."
                    except Exception as e:
                        # Anything else is our problem, not theirs - show a
                        # client-safe line and put the real cause in the server
                        # log, where Optia can see it and the client cannot.
                        reply, _detail = goldenacre_pulp.friendly_error(e)
                        print(f"[sprout] {_detail}", flush=True)
                st.markdown(reply)
            st.session_state.sprout_messages.append({"role": "assistant", "content": reply})
