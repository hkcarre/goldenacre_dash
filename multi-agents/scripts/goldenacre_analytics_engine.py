"""Golden Acre analytics - live compute layer, no Streamlit dependency (mirrors the
split in vithit_analytics_engine.py: this file only queries and computes, styling
and display live in goldenacre_theme.py / goldenacre_insights_app.py).

Every query here is the same, already-QA-verified logic from
build_goldenacre_insights_data.py (a separate subagent independently re-derived
every one of these figures directly from Snowflake and confirmed exact matches
before the static HTML report shipped) - refactored into reusable functions so
the live Streamlit app queries Snowflake directly rather than reading a frozen
JSON snapshot.

Source: GOLDENACRE.TRANSFORM.HC_MASTER joined to HC_PERIOD_DIM_CLEAN - the
harmonised, additive layer built this session (see
multi-agents/docs/goldenacre/goldenacre_target_architecture.md), never the
client's original sqlmesh-managed production pipeline.
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r"c:\Users\helen\Projects\snowflake")
from snowflake_connection import get_connection

BRAND_EXPR = "COALESCE(NULLIF(GA_BRAND, ''), AC_BRAND)"
CATEGORY_EXPR = "COALESCE(GA_BUYER, 'UNCLASSIFIED')"
TRAILING_WEEKS = 12
RETAILERS = ["ASDA", "MORRISONS", "SAINSBURY", "TESCO"]


def connection():
    return get_connection(schema="TRANSFORM")


def _df(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def pct_change(cur_val, prior_val):
    if prior_val is None or prior_val == 0 or pd.isna(prior_val):
        return None
    return round((cur_val - prior_val) / prior_val * 100, 2)


def load_kpis(conn):
    overall = _df(conn, f"""
        SELECT PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES, SUM(UNIT_SALES) AS UNIT_SALES,
               COUNT(DISTINCT BARCODE) AS DISTINCT_PRODUCTS, COUNT(DISTINCT {BRAND_EXPR}) AS DISTINCT_BRANDS
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA')
        GROUP BY PERIOD_MATX
    """)
    mat = overall[overall.PERIOD_MATX == "MAT"].iloc[0]
    ya_rows = overall[overall.PERIOD_MATX == "MAT YA"]
    ya = ya_rows.iloc[0] if len(ya_rows) else None

    ref_mat = _df(conn, "SELECT REFERENCE_MATCH_STATUS, SUM(VALUE_SALES) AS V, COUNT(*) AS N "
                         "FROM GOLDENACRE.TRANSFORM.HC_MASTER WHERE PERIOD_MATX = 'MAT' GROUP BY 1")
    total_rows = ref_mat.N.sum()
    total_value = ref_mat.V.sum()
    unmatched_value = float(ref_mat[ref_mat.REFERENCE_MATCH_STATUS == "UNMATCHED"].V.sum())
    matched_rows = float(ref_mat[ref_mat.REFERENCE_MATCH_STATUS == "MATCHED"].N.sum())

    return {
        "value_sales_mat": float(mat.VALUE_SALES),
        "value_sales_mat_ya": float(ya.VALUE_SALES) if ya is not None else None,
        "value_sales_change_pct": pct_change(float(mat.VALUE_SALES), float(ya.VALUE_SALES) if ya is not None else None),
        "unit_sales_mat": float(mat.UNIT_SALES),
        "unit_sales_mat_ya": float(ya.UNIT_SALES) if ya is not None else None,
        "unit_sales_change_pct": pct_change(float(mat.UNIT_SALES), float(ya.UNIT_SALES) if ya is not None else None),
        "avg_price_per_unit_mat": round(float(mat.VALUE_SALES) / float(mat.UNIT_SALES), 4) if float(mat.UNIT_SALES) else None,
        "distinct_products_mat": int(mat.DISTINCT_PRODUCTS),
        "distinct_brands_mat": int(mat.DISTINCT_BRANDS),
        "reference_match_pct_mat_rows": round(matched_rows / total_rows * 100, 2),
        "unmatched_value_sales_mat": round(unmatched_value, 2),
        "unmatched_value_sales_mat_pct": round(unmatched_value / float(total_value) * 100, 2),
    }


def load_retailer_share(conn):
    df = _df(conn, """
        SELECT RETAILER, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER WHERE PERIOD_MATX IN ('MAT', 'MAT YA') GROUP BY 1, 2
    """)
    mat = df[df.PERIOD_MATX == "MAT"].set_index("RETAILER").VALUE_SALES
    ya = df[df.PERIOD_MATX == "MAT YA"].set_index("RETAILER").VALUE_SALES
    total = mat.sum()
    rows = []
    for ret, val in mat.sort_values(ascending=False).items():
        prior = ya.get(ret)
        rows.append({
            "retailer": ret, "value_sales_mat": float(val), "share_pct": round(float(val) / float(total) * 100, 2),
            "value_sales_mat_ya": float(prior) if prior is not None else None,
            "change_pct": pct_change(float(val), float(prior) if prior is not None else None),
        })
    return pd.DataFrame(rows)


def load_category_share(conn):
    df = _df(conn, f"""
        SELECT {CATEGORY_EXPR} AS CATEGORY, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER WHERE PERIOD_MATX IN ('MAT', 'MAT YA') GROUP BY 1, 2
    """)
    mat = df[df.PERIOD_MATX == "MAT"].set_index("CATEGORY").VALUE_SALES
    ya = df[df.PERIOD_MATX == "MAT YA"].set_index("CATEGORY").VALUE_SALES
    total = mat.sum()
    rows = []
    for cat, val in mat.sort_values(ascending=False).items():
        prior = ya.get(cat)
        rows.append({
            "category": cat, "value_sales_mat": float(val), "share_pct": round(float(val) / float(total) * 100, 2),
            "value_sales_mat_ya": float(prior) if prior is not None else None,
            "change_pct": pct_change(float(val), float(prior) if prior is not None else None),
        })
    return pd.DataFrame(rows)


def load_top_brands(conn, limit=10):
    df = _df(conn, f"""
        SELECT {BRAND_EXPR} AS BRAND, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA') AND {BRAND_EXPR} NOT IN ('{{UNATTRIBUTED}}') AND {BRAND_EXPR} IS NOT NULL
        GROUP BY 1, 2
    """)
    mat = df[df.PERIOD_MATX == "MAT"].set_index("BRAND").VALUE_SALES
    ya = df[df.PERIOD_MATX == "MAT YA"].set_index("BRAND").VALUE_SALES
    total = mat.sum()
    rows = []
    for brand, val in mat.sort_values(ascending=False).head(limit).items():
        prior = ya.get(brand)
        rows.append({
            "brand": brand, "value_sales_mat": float(val), "share_pct": round(float(val) / float(total) * 100, 2),
            "value_sales_mat_ya": float(prior) if prior is not None else None,
            "change_pct": pct_change(float(val), float(prior) if prior is not None else None),
        })
    return pd.DataFrame(rows)


def load_treemap(conn, retailer=None, top_n=5):
    """retailer=None means all four retailers combined."""
    where_retailer = f"AND RETAILER = '{retailer}'" if retailer else ""
    df = _df(conn, f"""
        SELECT {CATEGORY_EXPR} AS CATEGORY, {BRAND_EXPR} AS BRAND, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA') AND {BRAND_EXPR} NOT IN ('{{UNATTRIBUTED}}') AND {BRAND_EXPR} IS NOT NULL
        {where_retailer}
        GROUP BY 1, 2, 3
    """)
    mat = df[df.PERIOD_MATX == "MAT"].groupby(["CATEGORY", "BRAND"], as_index=False).VALUE_SALES.sum()
    ya = df[df.PERIOD_MATX == "MAT YA"].groupby(["CATEGORY", "BRAND"]).VALUE_SALES.sum()
    leaves = []
    for cat, g in mat.groupby("CATEGORY"):
        g = g.sort_values("VALUE_SALES", ascending=False)
        top, rest = g.head(top_n), g.iloc[top_n:]
        for _, row in top.iterrows():
            prior = ya.get((cat, row.BRAND))
            leaves.append({"category": cat, "brand": row.BRAND, "value_sales_mat": float(row.VALUE_SALES),
                            "change_pct": pct_change(float(row.VALUE_SALES), float(prior) if prior is not None else None)})
        if len(rest):
            rest_mat = float(rest.VALUE_SALES.sum())
            rest_prior = sum(float(ya.get((cat, b), 0) or 0) for b in rest.BRAND)
            leaves.append({"category": cat, "brand": "Other", "value_sales_mat": rest_mat,
                            "change_pct": pct_change(rest_mat, rest_prior if rest_prior else None)})
    return pd.DataFrame(leaves)


def load_monthly_trend(conn):
    df = _df(conn, """
        SELECT RETAILER, YEAR, MONTH_NUMBER, SUM(VALUE_SALES) AS VALUE_SALES, COUNT(DISTINCT TIME_PERIODS) AS N_WEEKS
        FROM GOLDENACRE.TRANSFORM.HC_MASTER GROUP BY 1, 2, 3 ORDER BY 2, 3
    """)
    weeks_per_month = df.groupby(["YEAR", "MONTH_NUMBER"], as_index=False).N_WEEKS.max()
    typical = weeks_per_month.N_WEEKS.median()
    max_ym = (weeks_per_month.YEAR.max(), weeks_per_month.loc[weeks_per_month.YEAR == weeks_per_month.YEAR.max(), "MONTH_NUMBER"].max())
    df["PARTIAL_MONTH"] = df.apply(
        lambda r: bool((r.YEAR, r.MONTH_NUMBER) == max_ym and r.N_WEEKS < typical), axis=1)
    return df


def load_predictions(conn):
    """Directional trend only - a straight-line fit over the trailing
    TRAILING_WEEKS, normalised to %/week of that window's own mean. Explicitly
    NOT a statistical forecast, same discipline as vithit_analytics_engine.py's
    linear_trend()."""
    weekly_retailer = _df(conn, """
        SELECT RETAILER, TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER GROUP BY 1, 2 ORDER BY 1, 2
    """)
    weekly_category = _df(conn, f"""
        SELECT {CATEGORY_EXPR} AS CATEGORY, TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER GROUP BY 1, 2 ORDER BY 1, 2
    """)
    weekly_total = weekly_retailer.groupby("TIME_PERIODS", as_index=False).VALUE_SALES.sum().sort_values("TIME_PERIODS")

    def trend_pct(values):
        y = np.asarray(values, dtype=float)
        y = y[~np.isnan(y)]
        if len(y) < 4:
            return None, None, len(y)
        y = y[-TRAILING_WEEKS:] if len(y) >= TRAILING_WEEKS else y
        x = np.arange(len(y))
        slope, intercept = np.polyfit(x, y, 1)
        mean = y.mean()
        if mean == 0:
            return None, None, len(y)
        fitted = slope * x + intercept
        ss_res = np.sum((y - fitted) ** 2)
        ss_tot = np.sum((y - mean) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
        return round(slope / mean * 100, 3), round(r2, 3), len(y)

    rows = []
    slope, r2, n = trend_pct(weekly_total.VALUE_SALES.to_numpy())
    rows.append({"series": "TOTAL", "slope_pct_per_week": slope, "r_squared": r2, "weeks_used": n})
    for ret, g in weekly_retailer.groupby("RETAILER"):
        slope, r2, n = trend_pct(g.sort_values("TIME_PERIODS").VALUE_SALES.to_numpy())
        rows.append({"series": ret, "slope_pct_per_week": slope, "r_squared": r2, "weeks_used": n})
    for cat, g in weekly_category.groupby("CATEGORY"):
        slope, r2, n = trend_pct(g.sort_values("TIME_PERIODS").VALUE_SALES.to_numpy())
        rows.append({"series": cat, "slope_pct_per_week": slope, "r_squared": r2, "weeks_used": n})
    return pd.DataFrame(rows)
