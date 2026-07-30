"""Manufacturer-side competitive analysis: Golden Acre Foods' OWN brands (Najma,
Jaldee Eats) against the rest of the Halal category, from HC_MASTER.

This is a different lens from the rest of the report, which never named a specific
manufacturer - here Golden Acre is the vendor being analysed, not the retailer.
"Which brands does Golden Acre actually own" is not a fact in Nielsen/Circana-style
retail scan data (there's no manufacturer/supplier column) - it's external knowledge,
taken from Golden Acre's own real "Our Brands" page (goldenacrefoods.com/our-brands/):
Najma (halal cooked meat, nationwide Tesco/Asda/Sainsbury's/Morrisons/Co-op), Jaldee
Eats (new halal ready-to-eat range, Tesco only), Elsinore (Scandi seafood, Waitrose/
Ocado only) and Acti-Shake (protein drink, Co-op/Amazon/Nisa/Costcutter). Elsinore and
Acti-Shake are confirmed ABSENT from this dataset (checked directly) because none of
their listed retailers are ASDA/Morrisons/Sainsbury's/Tesco - only Najma and Jaldee
Eats are in scope here.

Brand-family normalisation: COALESCE(NULLIF(GA_BRAND,''), AC_BRAND) - the same
expression the rest of the report uses - resolves most Najma rows to the clean
'NAJMA' string, but ~22% of Najma's true MAT value falls back to raw, unmatched
AC_BRAND text ('NAJMA HALAL TURKEY', 'NAJMA HALAL CHICKEN', etc.), and because
category (GA_BUYER) comes from the same match, those rows are ALSO miscategorised
as "Unclassified" instead of Halal.

IMPORTANT correction to this analysis's own first pass: an initial version fixed
this gap only for Najma/Jaldee Eats and left every competitor on the unfixed,
naive GA_BUYER='HALAL' total - an independent QA agent re-deriving these numbers
correctly flagged that as an unfair, inconsistent comparison, since the same
category-classification gap turns out to affect most of the top competitors too
(e.g. Haji Baba has ~£14.7m sitting unmatched vs £28.2m matched - bigger than the
gap being corrected for Najma). The ranking below now applies ONE mechanical rule
uniformly to every brand: pull in same-brand rows sitting outside GA_BUYER='HALAL'
ONLY where the raw retailer text also literally contains "HALAL" - auditable, and
deliberately conservative (it correctly excludes e.g. "LANCASHIRE FARM YOGHURT" and
"HUMZA ORIGINAL PARATHA", which share a brand name with a Halal producer but are a
genuinely different, non-halal product line). Under this uniform rule, Najma's real
rank is still 4th (GBP19.8m, ahead of Lancashire Farm's GBP15.8m) even though most
of the top 5 also gained value from the correction - the finding survives being
applied fairly to everyone, which is a stronger result than the first pass's.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from snowflake_connection import get_connection

CATEGORY = "HALAL"
GA_OWNED_PREFIXES = {"NAJMA": "NAJMA%", "JALDEE EATS": "JALDEE%"}
TRAILING_WEEKS = 12


def df(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return pd.DataFrame(cur.fetchall(), columns=cols)


def linear_trend_pct(weekly_values):
    y = np.asarray(weekly_values, dtype=float)
    y = y[~np.isnan(y)]
    if len(y) < 4:
        return None, None, len(y)
    y = y[-TRAILING_WEEKS:] if len(y) >= TRAILING_WEEKS else y
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)
    mean_y = y.mean()
    if mean_y == 0:
        return None, None, len(y)
    fitted = slope * x + intercept
    ss_res = np.sum((y - fitted) ** 2)
    ss_tot = np.sum((y - mean_y) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    return round(float(slope / mean_y * 100), 3), (round(float(r2), 3) if r2 is not None else None), len(y)


def pct_change(cur_val, prior_val):
    if prior_val is None or prior_val == 0 or pd.isna(prior_val):
        return None
    return round(float((cur_val - prior_val) / prior_val * 100), 2)


def main():
    conn = get_connection(schema="TRANSFORM")
    cur = conn.cursor()
    cur.execute("USE ROLE GOLDENACRE_ANALYST_ROLE")
    cur.execute("USE WAREHOUSE GOLDENACRE_WH")

    brand_family_case = " ".join(
        f"WHEN UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE '{prefix}' THEN '{family}'"
        for family, prefix in GA_OWNED_PREFIXES.items()
    )

    # ---- confirm Elsinore / Acti-Shake / Golden Acre Yogurts are genuinely absent ----
    absent_check = df(cur, """
        SELECT COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) AS BRAND, COUNT(*) AS N
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE ANY
              ('%ELSINORE%','%ACTI-SHAKE%','%ACTISHAKE%','%GOLDEN ACRE%')
        GROUP BY 1
    """)

    # ---- Golden Acre family totals, MAT vs MAT YA, overall and by retailer ----
    ga_family = df(cur, f"""
        SELECT CASE {brand_family_case} END AS GA_BRAND_FAMILY, RETAILER, PERIOD_MATX,
               SUM(VALUE_SALES) AS VALUE_SALES, SUM(UNIT_SALES) AS UNIT_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE (UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%'
               OR UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%')
          AND PERIOD_MATX IN ('MAT','MAT YA')
        GROUP BY 1, 2, 3
    """)

    # ---- Najma's own reference-match rate (how much of its true value is on the
    #      clean matched string vs a raw unmatched fallback) ----
    najma_match = df(cur, """
        SELECT CASE WHEN NULLIF(GA_BRAND,'') IS NOT NULL THEN 'MATCHED' ELSE 'UNMATCHED' END AS STATUS,
               SUM(VALUE_SALES) AS VALUE_SALES, COUNT(*) AS N_ROWS
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%' AND PERIOD_MATX = 'MAT'
        GROUP BY 1
    """)

    # ---- Halal category total, MAT vs MAT YA, overall and by retailer ----
    category_total = df(cur, f"""
        SELECT RETAILER, PERIOD_MATX, SUM(VALUE_SALES) AS VALUE_SALES, SUM(UNIT_SALES) AS UNIT_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{CATEGORY}' AND PERIOD_MATX IN ('MAT','MAT YA')
        GROUP BY 1, 2
    """)

    # ---- naive baseline: every Halal brand exactly as GA_BUYER='HALAL' resolves it ----
    # (kept separately, unmodified, as the "before" figure for the correction callout)
    halal_rows_naive = df(cur, f"""
        SELECT COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) AS BRAND, SUM(VALUE_SALES) AS VALUE_SALES,
               SUM(UNIT_SALES) AS UNIT_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{CATEGORY}' AND PERIOD_MATX = 'MAT'
          AND COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) IS NOT NULL
        GROUP BY 1
    """)
    halal_rows_naive["VALUE_SALES"] = halal_rows_naive["VALUE_SALES"].astype(float)
    naive_rank = halal_rows_naive.sort_values("VALUE_SALES", ascending=False).reset_index(drop=True)
    naive_rank["RANK"] = naive_rank.index + 1
    najma_naive_row = naive_rank[naive_rank.BRAND == "NAJMA"].iloc[0]

    # ---- competitive set: every Halal brand, MAT, ranked, WITH the same correction
    #      applied uniformly to every brand (not just Golden Acre's own) ----
    # GA_BUYER (category) comes from the same product-reference match as GA_BRAND, so
    # ANY brand's unmatched fragments are ALSO missing from GA_BUYER='HALAL' even when
    # their raw text says "...HALAL...". Checked this for the whole top-10 (not just
    # Najma) and several competitors have exactly the same gap (e.g. Haji Baba, Tariq
    # Halal) - a first pass at this analysis fixed only Najma/Jaldee, which an
    # independent QA agent correctly flagged as an unfair, inconsistent comparison.
    # This query fixes it properly: for every brand identity already seen inside
    # GA_BUYER='HALAL', pull in same-brand rows sitting outside that category filter
    # ONLY where the raw retailer text also literally contains "HALAL" - a mechanical,
    # auditable rule applied identically to every brand, not a manual per-brand list.
    # (This deliberately excludes e.g. "LANCASHIRE FARM YOGHURT" and "HUMZA ORIGINAL
    # PARATHA" - same brand name, unrelated non-halal product line, correctly left out.)
    all_brands_mat = df(cur, f"""
        WITH halal_rows AS (
            SELECT COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) AS BRAND, VALUE_SALES, UNIT_SALES
            FROM GOLDENACRE.TRANSFORM.HC_MASTER
            WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{CATEGORY}' AND PERIOD_MATX = 'MAT'
              AND COALESCE(NULLIF(GA_BRAND,''),AC_BRAND) IS NOT NULL
        ),
        halal_roots AS (SELECT DISTINCT BRAND AS ROOT FROM halal_rows),
        outside_agg AS (
            SELECT AC_BRAND, SUM(VALUE_SALES) AS VALUE_SALES, SUM(UNIT_SALES) AS UNIT_SALES
            FROM GOLDENACRE.TRANSFORM.HC_MASTER
            WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') != '{CATEGORY}' AND PERIOD_MATX = 'MAT'
              AND UPPER(AC_BRAND) LIKE '%HALAL%'
            GROUP BY 1
        ),
        matched_outside AS (
            SELECT o.VALUE_SALES, o.UNIT_SALES, r.ROOT,
                   ROW_NUMBER() OVER (PARTITION BY o.AC_BRAND ORDER BY LENGTH(r.ROOT) DESC) AS RN
            FROM outside_agg o
            JOIN halal_roots r ON UPPER(o.AC_BRAND) LIKE UPPER(r.ROOT) || '%'
        )
        SELECT ROOT AS BRAND, VALUE_SALES, UNIT_SALES FROM matched_outside WHERE RN = 1
        UNION ALL
        SELECT BRAND, VALUE_SALES, UNIT_SALES FROM halal_rows
    """)
    all_brands_mat["VALUE_SALES"] = all_brands_mat["VALUE_SALES"].astype(float)
    all_brands_mat["UNIT_SALES"] = all_brands_mat["UNIT_SALES"].astype(float)
    all_brands_mat["BRAND_NORM"] = all_brands_mat["BRAND"]
    ranked = all_brands_mat.groupby("BRAND_NORM", as_index=False)[["VALUE_SALES", "UNIT_SALES"]].sum()
    ranked = ranked.sort_values("VALUE_SALES", ascending=False).reset_index(drop=True)
    ranked["RANK"] = ranked.index + 1
    ranked["PRICE_PER_UNIT"] = ranked.VALUE_SALES / ranked.UNIT_SALES.replace(0, np.nan)

    # ---- trailing-12-week trend: Najma + Jaldee Eats total vs Halal category total ----
    weekly_najma = df(cur, """
        SELECT TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%'
        GROUP BY 1 ORDER BY 1
    """)
    weekly_jaldee = df(cur, """
        SELECT TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%'
        GROUP BY 1 ORDER BY 1
    """)
    weekly_category = df(cur, f"""
        SELECT TIME_PERIODS, SUM(VALUE_SALES) AS VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        WHERE COALESCE(GA_BUYER,'UNCLASSIFIED') = '{CATEGORY}'
        GROUP BY 1 ORDER BY 1
    """)
    najma_slope, najma_r2, najma_n = linear_trend_pct(weekly_najma.VALUE_SALES.to_numpy())
    jaldee_slope, jaldee_r2, jaldee_n = linear_trend_pct(weekly_jaldee.VALUE_SALES.to_numpy())
    cat_slope, cat_r2, cat_n = linear_trend_pct(weekly_category.VALUE_SALES.to_numpy())

    # ---- monthly series for the Trend page overlay (mirrors the main report's
    #      monthly builder exactly, scoped to Najma+Jaldee combined, and again
    #      broken out by retailer for the "Golden Acre by retailer" filter -
    #      Najma is in all four, Jaldee Eats is Tesco-only, so that one retailer's
    #      line is Najma+Jaldee while the other three are Najma alone) ----
    monthly = df(cur, """
        SELECT YEAR, MONTH_NUMBER,
               SUM(CASE WHEN UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%'
                        OR UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%'
                   THEN VALUE_SALES ELSE 0 END) AS GA_VALUE_SALES,
               COUNT(DISTINCT TIME_PERIODS) AS N_WEEKS
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        GROUP BY 1, 2 ORDER BY 1, 2
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

    monthly_by_retailer = df(cur, """
        SELECT RETAILER, YEAR, MONTH_NUMBER,
               SUM(CASE WHEN UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'NAJMA%'
                        OR UPPER(COALESCE(NULLIF(GA_BRAND,''),AC_BRAND)) LIKE 'JALDEE%'
                   THEN VALUE_SALES ELSE 0 END) AS GA_VALUE_SALES
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        GROUP BY 1, 2, 3 ORDER BY 1, 2, 3
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

    conn.close()

    # ---------------- assemble snapshot ----------------
    def family_pivot(family):
        sub = ga_family[ga_family.GA_BRAND_FAMILY == family]
        mat = sub[sub.PERIOD_MATX == "MAT"].set_index("RETAILER")
        ya = sub[sub.PERIOD_MATX == "MAT YA"].set_index("RETAILER")
        retailers = sorted(set(mat.index) | set(ya.index))
        out = []
        for r in retailers:
            v_mat = float(mat.VALUE_SALES.get(r, 0) or 0)
            v_ya = float(ya.VALUE_SALES.get(r, 0) or 0)
            u_mat = float(mat.UNIT_SALES.get(r, 0) or 0)
            u_ya = float(ya.UNIT_SALES.get(r, 0) or 0)
            out.append({
                "retailer": r, "value_sales_mat": v_mat, "value_sales_mat_ya": v_ya,
                "value_yoy_pct": pct_change(v_mat, v_ya), "unit_sales_mat": u_mat,
                "unit_sales_mat_ya": u_ya,
            })
        total_mat = float(mat.VALUE_SALES.sum())
        total_ya = float(ya.VALUE_SALES.sum())
        return {
            "value_sales_mat": total_mat, "value_sales_mat_ya": total_ya,
            "value_yoy_pct": pct_change(total_mat, total_ya),
            "unit_sales_mat": float(mat.UNIT_SALES.sum()), "unit_sales_mat_ya": float(ya.UNIT_SALES.sum()),
            "unit_yoy_pct": pct_change(float(mat.UNIT_SALES.sum()), float(ya.UNIT_SALES.sum())),
            "n_retailers": len([r for r in out if r["value_sales_mat"] > 0]),
            "by_retailer": out,
        }

    najma = family_pivot("NAJMA")
    jaldee = family_pivot("JALDEE EATS")

    cat_mat = category_total[category_total.PERIOD_MATX == "MAT"].set_index("RETAILER")
    cat_ya = category_total[category_total.PERIOD_MATX == "MAT YA"].set_index("RETAILER")
    cat_total_mat = float(cat_mat.VALUE_SALES.sum())
    cat_total_ya = float(cat_ya.VALUE_SALES.sum())

    ga_combined_mat = najma["value_sales_mat"] + jaldee["value_sales_mat"]
    ga_combined_ya = najma["value_sales_mat_ya"] + jaldee["value_sales_mat_ya"]
    share_mat = ga_combined_mat / cat_total_mat * 100
    share_ya = ga_combined_ya / cat_total_ya * 100

    by_retailer_share = []
    for r in sorted(set(cat_mat.index) | set(cat_ya.index)):
        cat_v_mat = float(cat_mat.VALUE_SALES.get(r, 0) or 0)
        cat_v_ya = float(cat_ya.VALUE_SALES.get(r, 0) or 0)
        najma_r = next((x for x in najma["by_retailer"] if x["retailer"] == r), None)
        jaldee_r = next((x for x in jaldee["by_retailer"] if x["retailer"] == r), None)
        ga_v_mat = (najma_r["value_sales_mat"] if najma_r else 0) + (jaldee_r["value_sales_mat"] if jaldee_r else 0)
        ga_v_ya = (najma_r["value_sales_mat_ya"] if najma_r else 0) + (jaldee_r["value_sales_mat_ya"] if jaldee_r else 0)
        by_retailer_share.append({
            "retailer": r,
            "category_value_mat": cat_v_mat, "category_value_yoy_pct": pct_change(cat_v_mat, cat_v_ya),
            "ga_value_mat": ga_v_mat,
            "ga_share_mat_pct": round(ga_v_mat / cat_v_mat * 100, 2) if cat_v_mat else None,
            "ga_share_mat_ya_pct": round(ga_v_ya / cat_v_ya * 100, 2) if cat_v_ya else None,
            "share_point_change": round(ga_v_mat / cat_v_mat * 100 - ga_v_ya / cat_v_ya * 100, 2) if cat_v_mat and cat_v_ya else None,
        })

    competitive_set = [
        {
            "brand": row.BRAND_NORM, "rank": int(row.RANK), "value_sales_mat": float(row.VALUE_SALES),
            "unit_sales_mat": float(row.UNIT_SALES),
            "price_per_unit": round(float(row.PRICE_PER_UNIT), 3) if pd.notna(row.PRICE_PER_UNIT) else None,
            "is_golden_acre": row.BRAND_NORM in ("NAJMA", "JALDEE EATS"),
        }
        for _, row in ranked.head(12).iterrows()
    ]

    najma_match_idx = najma_match.set_index("STATUS")
    matched_val = float(najma_match_idx.VALUE_SALES.get("MATCHED", 0) or 0)
    unmatched_val = float(najma_match_idx.VALUE_SALES.get("UNMATCHED", 0) or 0)

    snapshot = {
        "category": "HALAL",
        "as_of_note": "Same HC_MASTER MAT/MAT YA windows as the rest of this report - per-retailer MAT, not a shared calendar.",
        "owned_brands_checked": ["NAJMA", "JALDEE EATS", "ELSINORE", "ACTI-SHAKE", "GOLDEN ACRE YOGURTS"],
        "owned_brands_present_in_dataset": ["NAJMA", "JALDEE EATS"],
        # An empty absent_check means zero matching rows - i.e. every one of these
        # was checked and genuinely confirmed absent. Record that explicitly as
        # {brand: 0} rather than an empty dict, which read as "not checked" (a QA
        # agent flagged the ambiguity - the claim was always true, this just makes
        # the audit trail for it actually match the prose that cites it).
        "owned_brands_absent_confirmed": (
            {row.BRAND: int(row.N) for _, row in absent_check.iterrows()} if not absent_check.empty
            else {"ELSINORE": 0, "ACTI-SHAKE": 0, "GOLDEN ACRE YOGURTS": 0}
        ),
        "najma": najma,
        "jaldee_eats": jaldee,
        "najma_reference_match": {
            "matched_value_mat": matched_val, "unmatched_value_mat": unmatched_val,
            "matched_pct": round(matched_val / (matched_val + unmatched_val) * 100, 1),
        },
        "najma_rank_correction": {
            "naive_rank_using_matched_string_only": int(najma_naive_row.RANK),
            "naive_value_mat": float(najma_naive_row.VALUE_SALES),
            "corrected_rank": int(ranked[ranked.BRAND_NORM == "NAJMA"].iloc[0].RANK),
            "corrected_value_mat": float(ranked[ranked.BRAND_NORM == "NAJMA"].iloc[0].VALUE_SALES),
        },
        "category_total": {
            "value_sales_mat": cat_total_mat, "value_sales_mat_ya": cat_total_ya,
            "value_yoy_pct": pct_change(cat_total_mat, cat_total_ya),
        },
        "golden_acre_share": {
            "combined_value_mat": ga_combined_mat, "combined_value_mat_ya": ga_combined_ya,
            "share_mat_pct": round(share_mat, 2), "share_mat_ya_pct": round(share_ya, 2),
            "share_point_change": round(share_mat - share_ya, 2),
        },
        "by_retailer_share": by_retailer_share,
        "competitive_set_top12": competitive_set,
        "trend": {
            "najma": {"slope_pct_per_week": najma_slope, "r_squared": najma_r2, "weeks_used": najma_n},
            "jaldee_eats": {"slope_pct_per_week": jaldee_slope, "r_squared": jaldee_r2, "weeks_used": jaldee_n},
            "category": {"slope_pct_per_week": cat_slope, "r_squared": cat_r2, "weeks_used": cat_n},
        },
        "trend_monthly_golden_acre": monthly_ga,
        "trend_monthly_golden_acre_by_retailer": monthly_ga_by_retailer,
    }

    out_path = r"C:\Users\helen\AppData\Local\Temp\claude\c--Users-helen-Projects-snowflake\00e37359-5341-4479-93c1-e898e7ff006d\scratchpad\goldenacre_manufacturer_view_snapshot.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Wrote {out_path}")
    print(json.dumps(snapshot, indent=2)[:3000])


if __name__ == "__main__":
    main()
