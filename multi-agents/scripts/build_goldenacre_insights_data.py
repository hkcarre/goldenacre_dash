"""Computes every figure shown in the Golden Acre analytics HTML deliverable and
snapshots them to a single JSON file - the HTML build reads only from this file,
never invents or hand-types a number. This mirrors the discipline in
vithit_analytics_engine.py (compute layer) / vithit_insights_app.py (display layer
never computes) and vithit_pulp.py's "only ever sees numbers that actually came
out of Snowflake" rule.

Source: GOLDENACRE.TRANSFORM.HC_MASTER (the QA'd, NUMBER(38,4)-precision-fixed
harmonization layer - see multi-agents/docs/goldenacre/goldenacre_target_architecture.md).

"Predictions" here means exactly what vithit_analytics_engine.py's linear_trend()
means: a directional slope from a straight-line fit over trailing weeks, explicitly
NOT a statistical forecast - the same honesty discipline is kept here on purpose.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from snowflake_connection import get_connection

BRAND_EXPR = "COALESCE(NULLIF(GA_BRAND, ''), AC_BRAND)"
TRAILING_WEEKS = 12

# GA_BUYER is Golden Acre's real business classification (Halal/Polish/Other),
# null exactly on rows unmatched to the reference database (see
# goldenacre_analytics_engine.py's identical constant for the full rationale -
# kept in sync with that file, not duplicated logic drifting independently).
# Category/brand-map/prediction breakdowns below are scoped to the 3 real
# segments only; the excluded total is already surfaced via
# kpis['unmatched_value_sales_mat_pct'], never silently dropped.
REAL_CATEGORIES = ["HALAL", "POLISH", "OTHER"]
CLASSIFIED_FILTER_SQL = "GA_BUYER IN ({})".format(", ".join(f"'{c}'" for c in REAL_CATEGORIES))


def df(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def linear_trend_pct(weekly_values):
    """Slope of a straight-line fit over the trailing TRAILING_WEEKS, expressed as
    a % of the series' own mean over that window - a directional read, not a forecast.
    Mirrors vithit_analytics_engine.py's linear_trend(), adapted to return a
    normalized % rather than raw units so retailers/categories of very different
    scale are comparable. Returns (pct_per_week, r_squared, n_weeks_used)."""
    y = np.asarray(weekly_values, dtype=float)
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


def main():
    conn = get_connection(schema="TRANSFORM")
    cur = conn.cursor()

    snapshot = {"source": "GOLDENACRE.TRANSFORM.HC_MASTER", "trailing_weeks_for_trend": TRAILING_WEEKS}

    # ---- as-of date: latest TIME_PERIODS actually in the data ----
    cur.execute("SELECT MAX(TIME_PERIODS) FROM GOLDENACRE.TRANSFORM.HC_MASTER")
    snapshot["as_of_latest_period"] = str(cur.fetchone()[0])

    # ---- overall MAT vs MAT YA ----
    overall = df(cur, """
        SELECT PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES, SUM(UNIT_SALES) AS UNIT_SALES,
               COUNT(DISTINCT BARCODE) AS DISTINCT_PRODUCTS,
               COUNT(DISTINCT {brand}) AS DISTINCT_BRANDS
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA')
        GROUP BY PERIOD_MATX
    """.format(brand=BRAND_EXPR))
    mat = overall[overall.PERIOD_MATX == "MAT"].iloc[0]
    mat_ya_rows = overall[overall.PERIOD_MATX == "MAT YA"]
    mat_ya = mat_ya_rows.iloc[0] if len(mat_ya_rows) else None

    def pct_change(cur_val, prior_val):
        if prior_val is None or prior_val == 0:
            return None
        return round((cur_val - prior_val) / prior_val * 100, 2)

    snapshot["kpis"] = {
        "value_sales_mat": float(mat.VALUE_SALES),
        "value_sales_mat_ya": float(mat_ya.VALUE_SALES) if mat_ya is not None else None,
        "value_sales_change_pct": pct_change(float(mat.VALUE_SALES), float(mat_ya.VALUE_SALES) if mat_ya is not None else None),
        "unit_sales_mat": float(mat.UNIT_SALES),
        "unit_sales_mat_ya": float(mat_ya.UNIT_SALES) if mat_ya is not None else None,
        "unit_sales_change_pct": pct_change(float(mat.UNIT_SALES), float(mat_ya.UNIT_SALES) if mat_ya is not None else None),
        "avg_price_per_unit_mat": round(float(mat.VALUE_SALES) / float(mat.UNIT_SALES), 4) if float(mat.UNIT_SALES) else None,
        "distinct_products_mat": int(mat.DISTINCT_PRODUCTS),
        "distinct_brands_mat": int(mat.DISTINCT_BRANDS),
    }

    # ---- reference match coverage: overall (all-time) and MAT-only ----
    ref_overall = df(cur, "SELECT REFERENCE_MATCH_STATUS, COUNT(*) AS N FROM GOLDENACRE.TRANSFORM.HC_MASTER GROUP BY 1")
    ref_mat = df(cur, "SELECT REFERENCE_MATCH_STATUS, SUM(VALUE_SALES) AS V, COUNT(*) AS N FROM GOLDENACRE.TRANSFORM.HC_MASTER WHERE PERIOD_MATX = 'MAT' GROUP BY 1")
    total_all = ref_overall.N.sum()
    total_mat_rows = ref_mat.N.sum()
    total_mat_value = ref_mat.V.sum()
    snapshot["kpis"]["reference_match_pct_overall_rows"] = round(
        float(ref_overall[ref_overall.REFERENCE_MATCH_STATUS == "MATCHED"].N.sum()) / total_all * 100, 2)
    snapshot["kpis"]["reference_match_pct_mat_rows"] = round(
        float(ref_mat[ref_mat.REFERENCE_MATCH_STATUS == "MATCHED"].N.sum()) / total_mat_rows * 100, 2)
    unmatched_mat_value = float(ref_mat[ref_mat.REFERENCE_MATCH_STATUS == "UNMATCHED"].V.sum())
    snapshot["kpis"]["unmatched_value_sales_mat"] = round(unmatched_mat_value, 2)
    snapshot["kpis"]["unmatched_value_sales_mat_pct"] = round(unmatched_mat_value / float(total_mat_value) * 100, 2)

    # ---- retailer share, MAT vs MAT YA ----
    retailer = df(cur, """
        SELECT RETAILER, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA')
        GROUP BY 1, 2
    """)
    r_mat = retailer[retailer.PERIOD_MATX == "MAT"].set_index("RETAILER").VALUE_SALES
    r_mat_ya = retailer[retailer.PERIOD_MATX == "MAT YA"].set_index("RETAILER").VALUE_SALES
    total_mat_val = r_mat.sum()
    retailer_share = []
    for ret, val in r_mat.sort_values(ascending=False).items():
        prior = r_mat_ya.get(ret)
        retailer_share.append({
            "retailer": ret,
            "value_sales_mat": round(float(val), 2),
            "share_pct": round(float(val) / float(total_mat_val) * 100, 2),
            "value_sales_mat_ya": round(float(prior), 2) if prior is not None else None,
            "change_pct": pct_change(float(val), float(prior) if prior is not None else None),
        })
    snapshot["retailer_share"] = retailer_share

    # ---- category (GA_BUYER) share, MAT vs MAT YA - Halal/Polish/Other only.
    # share_pct is each segment's share of the CLASSIFIED total, not of all MAT
    # value - the HTML build must disclose the excluded unmatched total
    # (snapshot["kpis"]["unmatched_value_sales_mat_pct"]) alongside this, not
    # just render it silently. ----
    category = df(cur, f"""
        SELECT GA_BUYER AS CATEGORY, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA') AND {CLASSIFIED_FILTER_SQL}
        GROUP BY 1, 2
    """)
    c_mat = category[category.PERIOD_MATX == "MAT"].set_index("CATEGORY").VALUE_SALES
    c_mat_ya = category[category.PERIOD_MATX == "MAT YA"].set_index("CATEGORY").VALUE_SALES
    total_classified_mat_val = c_mat.sum()
    category_share = []
    for cat, val in c_mat.sort_values(ascending=False).items():
        prior = c_mat_ya.get(cat)
        category_share.append({
            "category": cat,
            "value_sales_mat": round(float(val), 2),
            "share_pct": round(float(val) / float(total_classified_mat_val) * 100, 2),
            "value_sales_mat_ya": round(float(prior), 2) if prior is not None else None,
            "change_pct": pct_change(float(val), float(prior) if prior is not None else None),
        })
    snapshot["category_share"] = category_share

    # ---- top brands, MAT vs MAT YA ----
    brands = df(cur, f"""
        SELECT {BRAND_EXPR} AS BRAND, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA') AND {BRAND_EXPR} NOT IN ('{{UNATTRIBUTED}}') AND {BRAND_EXPR} IS NOT NULL
        GROUP BY 1, 2
    """)
    b_mat = brands[brands.PERIOD_MATX == "MAT"].set_index("BRAND").VALUE_SALES
    b_mat_ya = brands[brands.PERIOD_MATX == "MAT YA"].set_index("BRAND").VALUE_SALES
    top_brands = []
    for brand, val in b_mat.sort_values(ascending=False).head(10).items():
        prior = b_mat_ya.get(brand)
        top_brands.append({
            "brand": brand,
            "value_sales_mat": round(float(val), 2),
            "share_pct": round(float(val) / float(total_mat_val) * 100, 2),
            "value_sales_mat_ya": round(float(prior), 2) if prior is not None else None,
            "change_pct": pct_change(float(val), float(prior) if prior is not None else None),
        })
    snapshot["top_brands"] = top_brands

    # ---- treemap: category > brand, sized by MAT value, colored by MAT-vs-MAT-YA
    # change_pct (a diverging scale, not categorical-by-identity - a treemap is an
    # all-pairs adjacency form where the dataviz skill's categorical cap is 3 series,
    # which 4 categories would blow past; coloring by growth instead of category
    # identity sidesteps that cap entirely AND is a more informative "map": it shows
    # not just size but which brands are winning/losing at a glance). Built once for
    # "ALL" retailers combined (the default view) and once per retailer, so the HTML
    # can offer a client-side retailer filter without any further Snowflake calls.
    tree = df(cur, f"""
        SELECT RETAILER, GA_BUYER AS CATEGORY, {BRAND_EXPR} AS BRAND, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA') AND {BRAND_EXPR} NOT IN ('{{UNATTRIBUTED}}') AND {BRAND_EXPR} IS NOT NULL
        AND {CLASSIFIED_FILTER_SQL}
        GROUP BY 1, 2, 3, 4
    """)

    def build_treemap_leaves(df_slice):
        mat_slice = df_slice[df_slice.PERIOD_MATX == "MAT"].groupby(["CATEGORY", "BRAND"], as_index=False).VALUE_SALES.sum()
        ya_slice = df_slice[df_slice.PERIOD_MATX == "MAT YA"].groupby(["CATEGORY", "BRAND"]).VALUE_SALES.sum()
        # "Other"'s prior-year total for the growth %, NOT the sum of ya_slice looked
        # up only for brands that still have a current-MAT row (the previous version's
        # bug) - a brand with MAT YA sales but zero current MAT sales in that category
        # simply has no row in mat_slice at all, so it silently dropped out of "rest"
        # and its prior value never got counted, understating rest_prior and making
        # "Other"'s decline look smaller than it really was (found by an independent
        # QA agent re-deriving every treemap number from Snowflake - wrong in 7 of 20
        # cases, the tile's own VALUE was always right, only this YoY% was off).
        # Fix: category's true prior total minus the CURRENT top5's prior total -
        # correct regardless of which specific brands moved in/out of the long tail.
        ya_cat_totals = df_slice[df_slice.PERIOD_MATX == "MAT YA"].groupby("CATEGORY").VALUE_SALES.sum()
        leaves = []
        for cat, g in mat_slice.groupby("CATEGORY"):
            g = g.sort_values("VALUE_SALES", ascending=False)
            top5, rest = g.head(5), g.iloc[5:]
            top5_prior_sum = 0.0
            for _, row in top5.iterrows():
                prior = ya_slice.get((cat, row.BRAND))
                top5_prior_sum += float(prior) if prior is not None else 0.0
                leaves.append({
                    "category": cat, "brand": row.BRAND,
                    "value_sales_mat": round(float(row.VALUE_SALES), 2),
                    "change_pct": pct_change(float(row.VALUE_SALES), float(prior) if prior is not None else None),
                })
            if len(rest):
                rest_mat = float(rest.VALUE_SALES.sum())
                rest_prior = float(ya_cat_totals.get(cat, 0) or 0) - top5_prior_sum
                leaves.append({
                    "category": cat, "brand": "Other",
                    "value_sales_mat": round(rest_mat, 2),
                    "change_pct": pct_change(rest_mat, rest_prior if rest_prior else None),
                })
        return leaves

    snapshot["treemap_by_retailer"] = {"ALL": build_treemap_leaves(tree)}
    for ret, g in tree.groupby("RETAILER"):
        snapshot["treemap_by_retailer"][ret] = build_treemap_leaves(g)

    # ---- monthly trend, by retailer, full history ----
    # Week-count per (YEAR, MONTH_NUMBER) bucket is included so a partial trailing
    # month (data cuts off mid-month, e.g. as_of_latest_period 2026-07-19 means July
    # 2026 only has ~3 weeks, not the ~4.3 a full month gets) can be flagged rather
    # than silently plotted as if it were a real month-on-month drop - caught while
    # building this, not by a later QA pass, since it's exactly the kind of thing
    # that would otherwise mislead a chart reader.
    monthly = df(cur, """
        SELECT RETAILER, YEAR, MONTH_NUMBER, SUM(VALUE_SALES) AS VALUE_SALES,
               COUNT(DISTINCT TIME_PERIODS) AS N_WEEKS
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        GROUP BY 1, 2, 3
        ORDER BY 2, 3
    """)
    weeks_per_month = monthly.groupby(["YEAR", "MONTH_NUMBER"], as_index=False).N_WEEKS.max()
    typical_weeks = weeks_per_month.N_WEEKS.median()
    max_year_month = (weeks_per_month.YEAR.max(), weeks_per_month.loc[weeks_per_month.YEAR == weeks_per_month.YEAR.max(), "MONTH_NUMBER"].max())

    def is_partial(year, month):
        row = weeks_per_month[(weeks_per_month.YEAR == year) & (weeks_per_month.MONTH_NUMBER == month)]
        n = int(row.N_WEEKS.iloc[0]) if len(row) else 0
        return bool((year, month) == max_year_month and n < typical_weeks)

    monthly_total = monthly.groupby(["YEAR", "MONTH_NUMBER"], as_index=False).VALUE_SALES.sum()
    snapshot["trend_monthly_total"] = [
        {"year": int(r.YEAR), "month": int(r.MONTH_NUMBER), "value_sales": round(float(r.VALUE_SALES), 2),
         "partial_month": is_partial(int(r.YEAR), int(r.MONTH_NUMBER))}
        for _, r in monthly_total.iterrows()
    ]
    snapshot["trend_monthly_by_retailer"] = {
        ret: [
            {"year": int(r.YEAR), "month": int(r.MONTH_NUMBER), "value_sales": round(float(r.VALUE_SALES), 2),
             "partial_month": is_partial(int(r.YEAR), int(r.MONTH_NUMBER))}
            for _, r in g.sort_values(["YEAR", "MONTH_NUMBER"]).iterrows()
        ]
        for ret, g in monthly.groupby("RETAILER")
    }

    # ---- weekly series for trend-slope predictions: by retailer and by category ----
    weekly_retailer = df(cur, """
        SELECT RETAILER, TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER GROUP BY 1, 2 ORDER BY 1, 2
    """)
    weekly_category = df(cur, f"""
        SELECT GA_BUYER AS CATEGORY, TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER WHERE {CLASSIFIED_FILTER_SQL} GROUP BY 1, 2 ORDER BY 1, 2
    """)
    weekly_total = weekly_retailer.groupby("TIME_PERIODS", as_index=False).VALUE_SALES.sum().sort_values("TIME_PERIODS")

    predictions = []
    slope_pct, r2, n = linear_trend_pct(weekly_total.VALUE_SALES.to_numpy())
    predictions.append({"series": "TOTAL", "slope_pct_per_week": slope_pct, "r_squared": r2, "weeks_used": n})
    for ret, g in weekly_retailer.groupby("RETAILER"):
        g = g.sort_values("TIME_PERIODS")
        slope_pct, r2, n = linear_trend_pct(g.VALUE_SALES.to_numpy())
        predictions.append({"series": ret, "slope_pct_per_week": slope_pct, "r_squared": r2, "weeks_used": n})
    for cat, g in weekly_category.groupby("CATEGORY"):
        g = g.sort_values("TIME_PERIODS")
        slope_pct, r2, n = linear_trend_pct(g.VALUE_SALES.to_numpy())
        predictions.append({"series": cat, "slope_pct_per_week": slope_pct, "r_squared": r2, "weeks_used": n})
    snapshot["predictions"] = predictions

    conn.close()

    # Repo-relative, not a hardcoded absolute path. This previously pointed at a
    # PREVIOUS session's temp scratchpad, which no longer exists - so re-running
    # this script would either fail or silently write somewhere nobody looks,
    # while html_report/ still held an older snapshot. Same class of bug as the
    # hardcoded sys.path entries fixed for the Streamlit Cloud deploy.
    out_path = Path(__file__).resolve().parents[2] / "html_report" / "goldenacre_insights_snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Wrote {out_path}")
    print(json.dumps(snapshot["kpis"], indent=2))
    print("\nRetailer share:", json.dumps(snapshot["retailer_share"], indent=2))
    print("\nCategory share:", json.dumps(snapshot["category_share"], indent=2))
    print("\nPredictions:", json.dumps(snapshot["predictions"], indent=2))


if __name__ == "__main__":
    main()
