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
from pathlib import Path

import numpy as np
import pandas as pd

# Relative to this file (repo_root/multi-agents/scripts/), not a hardcoded local
# path - see the identical fix and rationale in goldenacre_insights_app.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from snowflake_connection import get_connection

BRAND_EXPR = "COALESCE(NULLIF(GA_BRAND, ''), AC_BRAND)"
TRAILING_WEEKS = 12
RETAILERS = ["ASDA", "MORRISONS", "SAINSBURY", "TESCO"]

# GA_BUYER is Golden Acre's real, production business classification - Halal,
# Polish, Other. It is null on exactly the rows that failed to match the
# reference database at all (confirmed directly: GA_BUYER IS NULL <=>
# REFERENCE_MATCH_STATUS = 'UNMATCHED', a 1:1 correspondence, checked live
# 2026-08-06). That's not a 4th business category - it's the classification
# gap already surfaced via kpis['unmatched_value_sales_mat_pct'] - and as of
# 2026-08-06 it's 45.8% of MAT value (was ~28% of rows at the original build,
# 2026-07-29 - the gap has grown as LANDING has grown without matching
# REFERENCE coverage keeping pace). Category/brand-map/prediction breakdowns
# below are scoped to the 3 real segments only, per Helena's explicit request -
# never silently drop the excluded total, always disclose it via the existing
# kpis unmatched_* fields alongside any output that uses this filter.
REAL_CATEGORIES = ["HALAL", "POLISH", "OTHER"]
CLASSIFIED_FILTER_SQL = "GA_BUYER IN ({})".format(", ".join(f"'{c}'" for c in REAL_CATEGORIES))


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
    """Halal/Polish/Other only - excludes the unmatched-to-reference rows (see
    kpis['unmatched_value_sales_mat_pct'] for that figure). share_pct here is
    therefore each segment's share of the CLASSIFIED total, not of all MAT
    value - callers must disclose the exclusion alongside this, not just plot it."""
    df = _df(conn, f"""
        SELECT GA_BUYER AS CATEGORY, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA') AND {CLASSIFIED_FILTER_SQL}
        GROUP BY 1, 2
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
    """retailer=None means all four retailers combined. Halal/Polish/Other only -
    see CLASSIFIED_FILTER_SQL's docstring above."""
    where_retailer = f"AND RETAILER = '{retailer}'" if retailer else ""
    df = _df(conn, f"""
        SELECT GA_BUYER AS CATEGORY, {BRAND_EXPR} AS BRAND, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE PERIOD_MATX IN ('MAT', 'MAT YA') AND {BRAND_EXPR} NOT IN ('{{UNATTRIBUTED}}') AND {BRAND_EXPR} IS NOT NULL
        AND {CLASSIFIED_FILTER_SQL}
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
        SELECT GA_BUYER AS CATEGORY, TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER WHERE {CLASSIFIED_FILTER_SQL} GROUP BY 1, 2 ORDER BY 1, 2
    """)
    # weekly_total intentionally stays unfiltered (TOTAL momentum = the whole
    # business, unmatched rows included) - only the per-category momentum below
    # is scoped to Halal/Polish/Other, per CLASSIFIED_FILTER_SQL's docstring.
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


# Golden Acre's own brands (manufacturer view) - ported from
# multi-agents/scripts/build_goldenacre_manufacturer_view.py, which has the full
# methodology writeup (which brands are Golden Acre's own, why the category filter
# alone undercounts Najma, and why the same correction is applied uniformly to
# every competitor rather than just Golden Acre's own brands). This is queried
# live rather than reading that script's JSON snapshot, same as every other
# load_* function here.
GA_CATEGORY = "HALAL"


def _trend_pct(values):
    """Same maths as load_predictions()'s inline trend_pct - pulled out to a
    module function so load_manufacturer_view() can reuse it without duplicating
    the formula (a QA pass on this project has twice caught a copy-pasted
    calculation drifting from its original - not duplicating it here on purpose)."""
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


# Brands the DATA'S OWN AC_MANUFACTURER field attributes to Golden Acre, which
# the NAJMA%/JALDEE% brand-name rule below never sees. Found 2026-08-06: the
# original manufacturer view was built on brand-string matching because scan
# data was assumed to carry no manufacturer column. It does - AC_MANUFACTURER is
# 98.9% populated, and 1,214 of the 2,279 'GOLDEN ACRE FOODS' rows were invisible
# to the brand rule.
#
# The two are kept apart deliberately, because they are not the same claim:
#   OWNED       - Golden Acre's own brand. The Hungry Boar is absent from their
#                 own /our-brands/ page (which is why it was missed), but the
#                 trade press covers the Booker/Tesco launch and goldenacrefoods
#                 .com carries its awards page. It belongs in own-brand share.
#   DISTRIBUTED - Golden Acre is named only as the UK distributor. Folding this
#                 into "Golden Acre's share" would overstate a manufacturer
#                 metric, so it is reported separately and excluded from it.
GA_MANUFACTURER = "GOLDEN ACRE FOODS"
GA_EXTRA_OWNED = {"THE HUNGRY BOAR": "%HUNGRY BOAR%"}
GA_EXTRA_DISTRIBUTED = {"X ENERGY": "X ENERGY%"}


def _load_portfolio_extras(conn):
    """Per-brand MAT/MAT YA for the AC_MANUFACTURER-attributed brands above.

    Scoped by manufacturer AND brand pattern together: manufacturer alone would
    sweep in Najma/Jaldee (already counted by the main view, so double-counting),
    and brand alone risks catching an unrelated third party using a similar name.
    """
    def rows_for(patterns):
        out = []
        for brand, like in patterns.items():
            df = _df(conn, f"""
                SELECT PERIOD_MATX,
                       SUM(VALUE_SALES) AS VALUE_SALES,
                       SUM(UNIT_SALES)  AS UNIT_SALES,
                       COUNT(DISTINCT RETAILER) AS N_RETAILERS
                FROM GOLDENACRE.TRANSFORM.HC_MASTER
                WHERE UPPER(AC_MANUFACTURER) = '{GA_MANUFACTURER}'
                  AND UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE '{like}'
                  AND PERIOD_MATX IN ('MAT','MAT YA')
                GROUP BY 1
            """).set_index("PERIOD_MATX")
            if df.empty:
                continue
            mat = float(df.VALUE_SALES.get("MAT", 0) or 0)
            ya = float(df.VALUE_SALES.get("MAT YA", 0) or 0)
            ret = _df(conn, f"""
                SELECT DISTINCT RETAILER FROM GOLDENACRE.TRANSFORM.HC_MASTER
                WHERE UPPER(AC_MANUFACTURER) = '{GA_MANUFACTURER}'
                  AND UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE '{like}'
                  AND PERIOD_MATX = 'MAT' AND VALUE_SALES > 0
                ORDER BY 1
            """)
            out.append({
                "brand": brand,
                "value_sales_mat": mat,
                "value_sales_mat_ya": ya,
                "value_yoy_pct": pct_change(mat, ya),
                "unit_sales_mat": float(df.UNIT_SALES.get("MAT", 0) or 0),
                "retailers": list(ret.RETAILER) if not ret.empty else [],
            })
        return sorted(out, key=lambda r: r["value_sales_mat"], reverse=True)

    owned = rows_for(GA_EXTRA_OWNED)
    distributed = rows_for(GA_EXTRA_DISTRIBUTED)
    return {
        "owned_extra": owned,
        "distributed": distributed,
        "owned_extra_total_mat": sum(r["value_sales_mat"] for r in owned),
        "distributed_total_mat": sum(r["value_sales_mat"] for r in distributed),
    }


def load_manufacturer_view(conn):
    def brand_family(period, by_retailer=False):
        cols = "RETAILER, " if by_retailer else ""
        group = "1, 2" if by_retailer else "1"
        df = _df(conn, f"""
            SELECT {cols}CASE WHEN UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%' THEN 'NAJMA' ELSE 'JALDEE EATS' END AS FAMILY,
                   SUM(VALUE_SALES) AS VALUE_SALES, SUM(UNIT_SALES) AS UNIT_SALES
            FROM GOLDENACRE.TRANSFORM.HC_MASTER
            WHERE (UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%' OR UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%')
              AND PERIOD_MATX = '{period}'
            GROUP BY {group}
        """)
        df["VALUE_SALES"] = df["VALUE_SALES"].astype(float)
        df["UNIT_SALES"] = df["UNIT_SALES"].astype(float)
        return df

    fam_mat, fam_ya = brand_family("MAT").set_index("FAMILY"), brand_family("MAT YA").set_index("FAMILY")
    najma_mat = float(fam_mat.VALUE_SALES.get("NAJMA", 0) or 0)
    najma_ya = float(fam_ya.VALUE_SALES.get("NAJMA", 0) or 0)
    najma_units_mat = float(fam_mat.UNIT_SALES.get("NAJMA", 0) or 0)
    najma_units_ya = float(fam_ya.UNIT_SALES.get("NAJMA", 0) or 0)
    jaldee_mat = float(fam_mat.VALUE_SALES.get("JALDEE EATS", 0) or 0)
    jaldee_ya = float(fam_ya.VALUE_SALES.get("JALDEE EATS", 0) or 0)
    jaldee_units_mat = float(fam_mat.UNIT_SALES.get("JALDEE EATS", 0) or 0)
    jaldee_units_ya = float(fam_ya.UNIT_SALES.get("JALDEE EATS", 0) or 0)

    fam_mat_ret, fam_ya_ret = brand_family("MAT", True), brand_family("MAT YA", True)

    def by_retailer(family):
        mat_r = fam_mat_ret[fam_mat_ret.FAMILY == family].set_index("RETAILER")
        ya_r = fam_ya_ret[fam_ya_ret.FAMILY == family].set_index("RETAILER")
        rows = []
        for ret in sorted(set(mat_r.index) | set(ya_r.index)):
            v_mat = float(mat_r.VALUE_SALES.get(ret, 0) or 0)
            v_ya = float(ya_r.VALUE_SALES.get(ret, 0) or 0)
            rows.append({
                "retailer": ret, "value_sales_mat": v_mat, "value_sales_mat_ya": v_ya,
                "value_yoy_pct": pct_change(v_mat, v_ya),
            })
        return rows

    najma_by_retailer, jaldee_by_retailer = by_retailer("NAJMA"), by_retailer("JALDEE EATS")

    cat = _df(conn, f"""
        SELECT PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{GA_CATEGORY}' AND PERIOD_MATX IN ('MAT','MAT YA')
        GROUP BY 1
    """).set_index("PERIOD_MATX").VALUE_SALES
    cat_mat, cat_ya = float(cat.get("MAT", 0) or 0), float(cat.get("MAT YA", 0) or 0)

    cat_by_retailer = _df(conn, f"""
        SELECT RETAILER, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{GA_CATEGORY}' AND PERIOD_MATX IN ('MAT','MAT YA')
        GROUP BY 1, 2
    """)
    cat_mat_r = cat_by_retailer[cat_by_retailer.PERIOD_MATX == "MAT"].set_index("RETAILER").VALUE_SALES
    cat_ya_r = cat_by_retailer[cat_by_retailer.PERIOD_MATX == "MAT YA"].set_index("RETAILER").VALUE_SALES

    by_retailer_share = []
    for ret in sorted(set(cat_mat_r.index) | set(cat_ya_r.index)):
        c_mat, c_ya = float(cat_mat_r.get(ret, 0) or 0), float(cat_ya_r.get(ret, 0) or 0)
        najma_r = next((x for x in najma_by_retailer if x["retailer"] == ret), None)
        jaldee_r = next((x for x in jaldee_by_retailer if x["retailer"] == ret), None)
        ga_v_mat = (najma_r["value_sales_mat"] if najma_r else 0) + (jaldee_r["value_sales_mat"] if jaldee_r else 0)
        ga_v_ya = (najma_r["value_sales_mat_ya"] if najma_r else 0) + (jaldee_r["value_sales_mat_ya"] if jaldee_r else 0)
        ga_share_mat = ga_v_mat / c_mat * 100 if c_mat else None
        ga_share_ya = ga_v_ya / c_ya * 100 if c_ya else None
        by_retailer_share.append({
            "retailer": ret, "category_value_mat": c_mat, "category_value_yoy_pct": pct_change(c_mat, c_ya),
            "ga_value_mat": ga_v_mat,
            "ga_share_mat_pct": round(ga_share_mat, 2) if ga_share_mat is not None else None,
            "ga_share_mat_ya_pct": round(ga_share_ya, 2) if ga_share_ya is not None else None,
            "share_point_change": round(ga_share_mat - ga_share_ya, 2) if ga_share_mat is not None and ga_share_ya is not None else None,
        })

    ga_mat, ga_ya = najma_mat + jaldee_mat, najma_ya + jaldee_ya
    share_mat = ga_mat / cat_mat * 100 if cat_mat else None
    share_ya = ga_ya / cat_ya * 100 if cat_ya else None

    # Najma's own reference-match split (how much of its true value sits on the
    # clean matched brand string vs. a raw unmatched fallback)
    najma_match = _df(conn, """
        SELECT CASE WHEN NULLIF(GA_BRAND,'') IS NOT NULL THEN 'MATCHED' ELSE 'UNMATCHED' END AS STATUS,
               SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%' AND PERIOD_MATX = 'MAT'
        GROUP BY 1
    """).set_index("STATUS").VALUE_SALES
    matched_val = float(najma_match.get("MATCHED", 0) or 0)
    unmatched_val = float(najma_match.get("UNMATCHED", 0) or 0)

    # uniform correction, same rule for every brand: fold in same-brand rows sitting
    # outside GA_BUYER='HALAL' only where the raw retailer text also says "HALAL"
    ranked = _df(conn, f"""
        WITH halal_rows AS (
            SELECT COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) AS BRAND, VALUE_SALES, UNIT_SALES
            FROM GOLDENACRE.TRANSFORM.HC_MASTER
            WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{GA_CATEGORY}' AND PERIOD_MATX = 'MAT'
              AND COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) IS NOT NULL
        ),
        halal_roots AS (SELECT DISTINCT BRAND AS ROOT FROM halal_rows),
        outside_agg AS (
            SELECT AC_BRAND, SUM(VALUE_SALES) AS VALUE_SALES, SUM(UNIT_SALES) AS UNIT_SALES
            FROM GOLDENACRE.TRANSFORM.HC_MASTER
            WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') != '{GA_CATEGORY}' AND PERIOD_MATX = 'MAT'
              AND UPPER(AC_BRAND) LIKE '%HALAL%'
            GROUP BY 1
        ),
        matched_outside AS (
            SELECT o.VALUE_SALES, o.UNIT_SALES, r.ROOT,
                   ROW_NUMBER() OVER (PARTITION BY o.AC_BRAND ORDER BY LENGTH(r.ROOT) DESC) AS RN
            FROM outside_agg o JOIN halal_roots r ON UPPER(o.AC_BRAND) LIKE UPPER(r.ROOT) || '%'
        )
        SELECT ROOT AS BRAND, VALUE_SALES, UNIT_SALES FROM matched_outside WHERE RN = 1
        UNION ALL
        SELECT BRAND, VALUE_SALES, UNIT_SALES FROM halal_rows
    """)
    ranked["VALUE_SALES"] = ranked["VALUE_SALES"].astype(float)
    ranked["UNIT_SALES"] = ranked["UNIT_SALES"].astype(float)
    ranked = ranked.groupby("BRAND", as_index=False)[["VALUE_SALES", "UNIT_SALES"]].sum().sort_values("VALUE_SALES", ascending=False).reset_index(drop=True)
    ranked["RANK"] = ranked.index + 1
    ranked["PRICE_PER_UNIT"] = ranked.VALUE_SALES / ranked.UNIT_SALES.replace(0, np.nan)

    naive = _df(conn, f"""
        SELECT COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) AS BRAND, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{GA_CATEGORY}' AND PERIOD_MATX = 'MAT'
          AND COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) IS NOT NULL
        GROUP BY 1
    """)
    naive["VALUE_SALES"] = naive["VALUE_SALES"].astype(float)
    naive = naive.sort_values("VALUE_SALES", ascending=False).reset_index(drop=True)
    naive["RANK"] = naive.index + 1

    najma_rank_row = ranked[ranked.BRAND == "NAJMA"]
    najma_naive_row = naive[naive.BRAND == "NAJMA"]

    top12 = [
        {
            "brand": r.BRAND, "rank": int(r.RANK), "value_sales_mat": float(r.VALUE_SALES),
            "unit_sales_mat": float(r.UNIT_SALES),
            "price_per_unit": round(float(r.PRICE_PER_UNIT), 3) if pd.notna(r.PRICE_PER_UNIT) else None,
            "is_golden_acre": r.BRAND == "NAJMA",
        }
        for _, r in ranked.head(12).iterrows()
    ]

    # trailing-12-week momentum: Najma, Jaldee Eats, and the Halal category
    weekly_najma = _df(conn, """
        SELECT TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%' GROUP BY 1 ORDER BY 1
    """)
    weekly_jaldee = _df(conn, """
        SELECT TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%' GROUP BY 1 ORDER BY 1
    """)
    weekly_category = _df(conn, f"""
        SELECT TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{GA_CATEGORY}' GROUP BY 1 ORDER BY 1
    """)
    najma_slope, najma_r2, najma_n = _trend_pct(weekly_najma.VALUE_SALES.to_numpy())
    jaldee_slope, jaldee_r2, jaldee_n = _trend_pct(weekly_jaldee.VALUE_SALES.to_numpy())
    cat_slope, cat_r2, cat_n = _trend_pct(weekly_category.VALUE_SALES.to_numpy())

    # monthly series for the Trend page: combined Golden Acre, and by retailer
    # (mirrors load_monthly_trend()'s own partial-month logic, scoped to GA)
    monthly = _df(conn, """
        SELECT YEAR, MONTH_NUMBER,
               SUM(CASE WHEN UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%'
                        OR UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%'
                   THEN VALUE_SALES ELSE 0 END) AS GA_VALUE_SALES,
               COUNT(DISTINCT TIME_PERIODS) AS N_WEEKS
        FROM GOLDENACRE.TRANSFORM.HC_MASTER GROUP BY 1, 2 ORDER BY 1, 2
    """)
    monthly["GA_VALUE_SALES"] = monthly["GA_VALUE_SALES"].astype(float)
    weeks_per_month = monthly.N_WEEKS
    typical_weeks = weeks_per_month.median()
    max_idx = monthly[["YEAR", "MONTH_NUMBER"]].apply(tuple, axis=1).idxmax()
    max_year_month = tuple(monthly.loc[max_idx, ["YEAR", "MONTH_NUMBER"]])
    monthly_ga = [
        {
            "year": int(r.YEAR), "month": int(r.MONTH_NUMBER), "value_sales": round(float(r.GA_VALUE_SALES), 2),
            "partial_month": bool((int(r.YEAR), int(r.MONTH_NUMBER)) == max_year_month and r.N_WEEKS < typical_weeks),
        }
        for _, r in monthly.iterrows()
    ]

    monthly_by_retailer = _df(conn, """
        SELECT RETAILER, YEAR, MONTH_NUMBER,
               SUM(CASE WHEN UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%'
                        OR UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%'
                   THEN VALUE_SALES ELSE 0 END) AS GA_VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
    """)
    monthly_by_retailer["GA_VALUE_SALES"] = monthly_by_retailer["GA_VALUE_SALES"].astype(float)
    monthly_ga_by_retailer = {
        ret: [
            {
                "year": int(r.YEAR), "month": int(r.MONTH_NUMBER), "value_sales": round(float(r.GA_VALUE_SALES), 2),
                "partial_month": bool((int(r.YEAR), int(r.MONTH_NUMBER)) == max_year_month and
                                       int(weeks_per_month[(monthly.YEAR == r.YEAR) & (monthly.MONTH_NUMBER == r.MONTH_NUMBER)].iloc[0]) < typical_weeks),
            }
            for _, r in g.sort_values(["YEAR", "MONTH_NUMBER"]).iterrows()
        ]
        for ret, g in monthly_by_retailer.groupby("RETAILER")
    }

    absent_check = _df(conn, """
        SELECT COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) AS BRAND, COUNT(*) AS N
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE ANY
              ('%ELSINORE%','%ACTI-SHAKE%','%ACTISHAKE%','%GOLDEN ACRE%')
        GROUP BY 1
    """)

    extras = _load_portfolio_extras(conn)

    return {
        "category": GA_CATEGORY,
        # THE HUNGRY BOAR / X ENERGY were found via AC_MANUFACTURER, not via the
        # website's /our-brands/ page, which lists neither - see GA_EXTRA_OWNED.
        "owned_brands_checked": ["NAJMA", "JALDEE EATS", "THE HUNGRY BOAR", "ELSINORE",
                                 "ACTI-SHAKE", "GOLDEN ACRE YOGURTS"],
        "owned_brands_present_in_dataset": ["NAJMA", "JALDEE EATS", "THE HUNGRY BOAR"],
        "distributed_brands_present_in_dataset": ["X ENERGY"],
        "portfolio_extras": extras,
        "owned_brands_absent_confirmed": (
            {row.BRAND: int(row.N) for _, row in absent_check.iterrows()} if not absent_check.empty
            else {"ELSINORE": 0, "ACTI-SHAKE": 0, "GOLDEN ACRE YOGURTS": 0}
        ),
        "najma": {
            "value_sales_mat": najma_mat, "value_sales_mat_ya": najma_ya, "value_yoy_pct": pct_change(najma_mat, najma_ya),
            "unit_sales_mat": najma_units_mat, "unit_sales_mat_ya": najma_units_ya,
            "unit_yoy_pct": pct_change(najma_units_mat, najma_units_ya),
            "n_retailers": len([r for r in najma_by_retailer if r["value_sales_mat"] > 0]),
            "by_retailer": najma_by_retailer,
        },
        "jaldee_eats": {
            "value_sales_mat": jaldee_mat, "value_sales_mat_ya": jaldee_ya, "value_yoy_pct": pct_change(jaldee_mat, jaldee_ya),
            "unit_sales_mat": jaldee_units_mat, "unit_sales_mat_ya": jaldee_units_ya,
            "unit_yoy_pct": pct_change(jaldee_units_mat, jaldee_units_ya),
            "n_retailers": len([r for r in jaldee_by_retailer if r["value_sales_mat"] > 0]),
            "by_retailer": jaldee_by_retailer,
        },
        "najma_reference_match": {
            "matched_value_mat": matched_val, "unmatched_value_mat": unmatched_val,
            "matched_pct": round(matched_val / (matched_val + unmatched_val) * 100, 1) if (matched_val + unmatched_val) else None,
        },
        "category_total": {"value_sales_mat": cat_mat, "value_sales_mat_ya": cat_ya, "value_yoy_pct": pct_change(cat_mat, cat_ya)},
        "golden_acre_share": {
            "combined_value_mat": ga_mat, "combined_value_mat_ya": ga_ya,
            "share_mat_pct": round(share_mat, 2) if share_mat is not None else None,
            "share_mat_ya_pct": round(share_ya, 2) if share_ya is not None else None,
            "share_point_change": round(share_mat - share_ya, 2) if share_mat is not None and share_ya is not None else None,
        },
        "by_retailer_share": by_retailer_share,
        "najma_rank_correction": {
            "naive_rank": int(najma_naive_row.iloc[0].RANK) if len(najma_naive_row) else None,
            "naive_value_mat": float(najma_naive_row.iloc[0].VALUE_SALES) if len(najma_naive_row) else None,
            "corrected_rank": int(najma_rank_row.iloc[0].RANK) if len(najma_rank_row) else None,
            "corrected_value_mat": float(najma_rank_row.iloc[0].VALUE_SALES) if len(najma_rank_row) else None,
        },
        "competitive_set_top12": top12,
        "trend": {
            "najma": {"slope_pct_per_week": najma_slope, "r_squared": najma_r2, "weeks_used": najma_n},
            "jaldee_eats": {"slope_pct_per_week": jaldee_slope, "r_squared": jaldee_r2, "weeks_used": jaldee_n},
            "category": {"slope_pct_per_week": cat_slope, "r_squared": cat_r2, "weeks_used": cat_n},
        },
        "trend_monthly_golden_acre": monthly_ga,
        "trend_monthly_golden_acre_by_retailer": monthly_ga_by_retailer,
    }


def build_insight_texts(kpis, manufacturer_view):
    """The Insights page's narrative cards, as [(key, html), ...].

    Lives here, not in the Streamlit app, because it has two consumers that must
    never disagree: the app renders these as cards, and
    build_goldenacre_audio.py pre-generates the spoken clips from the very same
    strings. Duplicating the wording in the audio builder would reintroduce this
    project's most persistent failure mode - hand-written narrative drifting away
    from the live figures beside it - except this time the drift would be audible
    and invisible to a code review of the page.
    """
    price_mat = kpis["avg_price_per_unit_mat"]
    price_mat_ya = kpis["value_sales_mat_ya"] / kpis["unit_sales_mat_ya"] if kpis["unit_sales_mat_ya"] else None
    price_change = pct_change(price_mat, price_mat_ya) if price_mat_ya else None

    # The price clause is built conditionally on BOTH facts it asserts. The
    # previous version hardcoded the "cushioned" conclusion regardless of which
    # way price actually moved, so a refresh in which price fell would have had
    # the card claim the exact opposite of its own figures; and when price_change
    # was None it emitted a dangling fragment starting with " - ".
    value_dir = "down" if kpis["value_sales_change_pct"] < 0 else "up"
    unit_dir = "fell" if kpis["unit_sales_change_pct"] < 0 else "rose"
    if price_change is None:
        price_clause = "."
    else:
        # All four quadrants, because the wording is not symmetric: price/mix
        # either reinforces the volume move or works against it, and "cushioned"
        # only makes sense against a decline. Getting this from the data rather
        # than hardcoding it is the point - the previous copy asserted
        # "cushioned...decline" unconditionally.
        volume_fell = kpis["unit_sales_change_pct"] < 0
        same_direction = (price_change > 0) == (not volume_fell)
        if volume_fell:
            effect = "compounded the volume decline" if same_direction else "cushioned part of the volume decline"
        else:
            effect = "added to the volume gain" if same_direction else "offset part of the volume gain"
        price_clause = (
            f", while average price per unit {'rose' if price_change > 0 else 'fell'} "
            f"{abs(price_change):.1f}% - price/mix {effect}."
        )

    cards = [
        ("insight_1",
         f"<strong>Overall value sales are {value_dir} {abs(kpis['value_sales_change_pct']):.1f}% MAT vs. MAT YA</strong> "
         f"(£{kpis['value_sales_mat']/1e9:.2f}bn vs. £{kpis['value_sales_mat_ya']/1e9:.2f}bn). Unit sales "
         f"{unit_dir} {abs(kpis['unit_sales_change_pct']):.1f}%" + price_clause),
        ("insight_2",
         f"<strong>{kpis['unmatched_value_sales_mat_pct']:.1f}% of MAT value sales</strong> "
         f"(£{kpis['unmatched_value_sales_mat']/1e9:.2f}bn) sit in products with no product-reference match at all - "
         "the single biggest lever for sharper category reporting is expanding reference-database coverage, not merchandising."),
    ]

    ga_share = manufacturer_view["golden_acre_share"]
    ga_corr = manufacturer_view["najma_rank_correction"]
    cards.append((
        "insight_ga",
        f"<strong>Golden Acre is gaining share in a shrinking category.</strong> Halal overall is down "
        f"{abs(manufacturer_view['category_total']['value_yoy_pct']):.1f}% MAT, but Najma + Jaldee Eats' combined "
        f"share rose {'+' if ga_share['share_point_change'] > 0 else ''}{ga_share['share_point_change']:.2f}pp - and "
        f"gained share in every retailer it's listed in, not just on average. Najma's true rank is #{ga_corr['corrected_rank']} "
        f"(not #{ga_corr['naive_rank']} - see Golden Acre View for why), and the clearest near-term lever isn't demand, "
        f"it's distribution: Jaldee Eats is Tesco-only while Najma is already established in the other three retailers."
    ))

    extras = manufacturer_view.get("portfolio_extras") or {}
    rows = (extras.get("owned_extra") or []) + (extras.get("distributed") or [])
    if rows:
        by_brand = ", ".join(
            f"{r['brand'].title()} £{r['value_sales_mat']/1e3:.0f}k ({r['value_yoy_pct']:+.0f}%)" for r in rows
        )
        cards.append((
            "insight_extras",
            f"<strong>Golden Acre's fastest growth is outside Halal, and outside this report until now.</strong> "
            f"{by_brand}. Both were found through the data's own manufacturer field rather than Golden Acre's "
            f"\"Our Brands\" page, which lists neither. The Hungry Boar is an own brand; X Energy is distributed, "
            f"not owned, so it is excluded from own-brand share. Neither sits in Halal, Polish or Other, so both "
            f"are invisible on every category view - see Golden Acre View for the detail."
        ))
    return cards
