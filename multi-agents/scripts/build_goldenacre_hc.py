"""Builds the HC_ harmonization layer for Golden Acre - the second applied
instance of the multi-agent framework proven on Vithit's HC2_ build
(see build_vithit_hc2.py), reused end-to-end: discovery + profiling already
captured in docs/goldenacre/goldenacre_raw_assessment.md, this script is the
transformation-design phase's output.

Additive only: every object created here is prefixed HC_, confirmed
collision-free against everything already in GOLDENACRE (see
config/write_allowed_objects.yaml). Never references, and never has
permission to write to, any pre-existing GOLDENACRE object - the real,
separate, sqlmesh-managed production pipeline (CLEANASDA/CLEANMORRISON/
CLEANSAINSBURY/CLEANTESCO/MASTER/REFERENCE, and the OUTPUT dashboard views)
stays completely untouched (see config/read_only_objects.yaml).

Design decisions here are evidence-driven, not copied blind from the Vithit
pattern - see docs/goldenacre/goldenacre_target_architecture.md for the
diagnostics behind each one. Headline ones:
  - Duplicate (BARCODE, TIME PERIODS) keys are resolved by keeping the single
    highest-sales row per key (QUALIFY ROW_NUMBER), not by summing - a
    diagnostic confirmed ASDA's 505 duplicate groups have fully IDENTICAL
    sales measures (summing would double-count), while MORRISONS' 4,031
    groups are mostly a real row paired with a zero-sales
    'UNKNOWN PRODUCT_<barcode>' placeholder (summing happens to be harmless
    there, but only because of the zero - a blanket sum rule is wrong).
  - BARCODE stays VARCHAR everywhere - the existing MASTER casts it to
    NUMBER(38,0), which loses leading zeros and can't hold the literal
    '{UNATTRIBUTED}' placeholder value.
  - REFERENCE_DATABASE is deduped to one row per barcode (completeness-score
    tie-break) before any join - the existing MASTER doesn't do this, and a
    diagnostic confirmed that's exactly why its row count is 57% higher than
    the sum of its 4 clean sources.
  - Period-window rank (MAT/12WK/4WK, RULE-0002 technique reused from the
    Vithit build) is computed PER RETAILER, not on a shared calendar rank -
    TESCO's period range (Dec 2024-May 2026) doesn't overlap the other three
    retailers' (Apr 2023-May 2025), so a global rank would mis-classify
    everyone's "current MAT" once Tesco's later dates are mixed in.
  - A plain TRIM(BARCODE) join to the reference table was kept deliberately
    simple: a live diagnostic confirmed the reference table's separate
    UPC12 column contributes zero incremental matches beyond BARCODE alone,
    across all four retailers - added join complexity wasn't justified.

Idempotent: CREATE OR REPLACE TABLE throughout, scoped only to the HC_
object names below - safe to re-run as LANDING refreshes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from snowflake_connection import get_connection

RETAILERS = ["ASDA", "MORRISONS", "SAINSBURY", "TESCO"]

# Numeric cleaning: strip everything except digits, '.', '-' (robust to whichever
# currency-symbol byte sequence is actually stored) then TRY_TO_NUMBER.
NUMERIC_COLS = [
    ("STORES SELLING", "STORES_SELLING"),
    ("UNIT SALES", "UNIT_SALES"),
    ("VALUE SALES", "VALUE_SALES"),
    ("Unit Sales per Store", "UNIT_SALES_PER_STORE"),
    ("Value Sales per Store", "VALUE_SALES_PER_STORE"),
    ("Price Per Unit", "PRICE_PER_UNIT"),
]


def clean_table(retailer):
    return f"HC_{retailer}_CLEAN"


def numeric_cast(raw_col):
    # TRY_TO_NUMBER with no explicit scale defaults to NUMBER(38,0), silently
    # rounding every fractional value to a whole number (caught by an adversarial
    # QA pass 2026-07-29 - confirmed damaging >50% of rows on VALUE_SALES/
    # PRICE_PER_UNIT/*_PER_STORE across all 4 retailers). Explicit scale required.
    return f"TRY_TO_NUMBER(REGEXP_REPLACE(\"{raw_col}\", '[^0-9.-]', ''), 38, 4)"


def build_retailer_clean(cur, retailer):
    numeric_select = ", ".join(f"{numeric_cast(raw)} AS {clean}" for raw, clean in NUMERIC_COLS)
    cur.execute(f"""
        CREATE OR REPLACE TABLE GOLDENACRE.TRANSFORM.{clean_table(retailer)} AS
        WITH typed AS (
            SELECT
                "Total Market" AS TOTAL_MARKET,
                AC_MANUFACTURER,
                AC_BRAND,
                "Product Description" AS PRODUCT_DESCRIPTION,
                TRIM(BARCODE) AS BARCODE,
                TO_DATE("TIME PERIODS", 'DD MON YYYY') AS TIME_PERIODS,
                {numeric_select}
            FROM GOLDENACRE.LANDING.{retailer}
        )
        SELECT '{retailer}' AS RETAILER, *
        FROM typed
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY BARCODE, TIME_PERIODS
            ORDER BY UNIT_SALES DESC NULLS LAST, VALUE_SALES DESC NULLS LAST, PRODUCT_DESCRIPTION
        ) = 1
    """)


def build_reference_clean(cur):
    completeness = " + ".join(
        f"CASE WHEN {col} IS NOT NULL THEN 1 ELSE 0 END"
        for col in [
            "BRAND", "BUYER", "GA_CATEGORY", "GA_SUBCAT", "GA_SUBCAT2",
            "FLAV_VARIETY_GEO", "UNIFIED_PRODUCT_NAME", "WT", "WTG",
        ]
    )
    cur.execute(f"""
        CREATE OR REPLACE TABLE GOLDENACRE.TRANSFORM.HC_REFERENCE_CLEAN AS
        WITH base AS (
            SELECT
                TRIM(BARCODE) AS BARCODE,
                "RETAILER PRODUCT DESCRIPTION" AS RETAILER_PRODUCT_DESCRIPTION,
                TRIM(UPC12) AS UPC12,
                "UNIFIED PRODUCT NAME" AS UNIFIED_PRODUCT_NAME,
                BRAND,
                BUYER,
                "GA CATEGORY" AS GA_CATEGORY,
                "GA SUBCAT" AS GA_SUBCAT,
                "GA SUBCAT2" AS GA_SUBCAT2,
                "FLAV/ VARIETY/GEO" AS FLAV_VARIETY_GEO,
                WT,
                WTG,
                SNAPSHOT_DATE
            FROM GOLDENACRE.LANDING.REFERENCE_DATABASE
            WHERE BARCODE IS NOT NULL
              AND TRIM(BARCODE) NOT IN ('', '{{UNATTRIBUTED}}')
        ),
        scored AS (
            SELECT *, ({completeness}) AS COMPLETENESS_SCORE
            FROM base
        )
        SELECT * EXCLUDE (COMPLETENESS_SCORE)
        FROM scored
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY BARCODE
            ORDER BY COMPLETENESS_SCORE DESC, RETAILER_PRODUCT_DESCRIPTION
        ) = 1
    """)


def build_period_dim_clean(cur):
    union_sql = "\n            UNION ALL\n            ".join(
        f"SELECT DISTINCT RETAILER, TIME_PERIODS FROM GOLDENACRE.TRANSFORM.{clean_table(r)}"
        for r in RETAILERS
    )
    cur.execute(f"""
        CREATE OR REPLACE TABLE GOLDENACRE.TRANSFORM.HC_PERIOD_DIM_CLEAN AS
        WITH periods AS (
            {union_sql}
        ),
        ranked AS (
            SELECT RETAILER, TIME_PERIODS,
                   RANK() OVER (PARTITION BY RETAILER ORDER BY TIME_PERIODS DESC) AS PERIOD_RANK
            FROM periods
        )
        SELECT
            RETAILER,
            TIME_PERIODS,
            PERIOD_RANK,
            YEAR(TIME_PERIODS) AS YEAR,
            QUARTER(TIME_PERIODS) AS QUARTER,
            MONTH(TIME_PERIODS) AS MONTH_NUMBER,
            MONTHNAME(TIME_PERIODS) AS MONTH,
            WEEKOFYEAR(TIME_PERIODS) AS WEEK_OF_YEAR,
            CASE
                WHEN PERIOD_RANK BETWEEN 1 AND 52 THEN 'MAT'
                WHEN PERIOD_RANK BETWEEN 53 AND 104 THEN 'MAT YA'
                WHEN PERIOD_RANK BETWEEN 105 AND 156 THEN 'MAT 2YA'
            END AS PERIOD_MATX,
            CASE
                WHEN PERIOD_RANK BETWEEN 1 AND 12 THEN '12 WK'
                WHEN PERIOD_RANK BETWEEN 53 AND 64 THEN '12 WK YA'
                WHEN PERIOD_RANK BETWEEN 105 AND 116 THEN '12 WK 2YA'
            END AS PERIOD_12X,
            CASE
                WHEN PERIOD_RANK BETWEEN 1 AND 4 THEN '4 WK'
                WHEN PERIOD_RANK BETWEEN 53 AND 56 THEN '4 WK YA'
                WHEN PERIOD_RANK BETWEEN 105 AND 108 THEN '4 WK 2YA'
            END AS PERIOD_4X
        FROM ranked
    """)


def build_master(cur):
    union_sql = "\n            UNION ALL\n            ".join(
        f"SELECT * FROM GOLDENACRE.TRANSFORM.{clean_table(r)}" for r in RETAILERS
    )
    cur.execute(f"""
        CREATE OR REPLACE TABLE GOLDENACRE.TRANSFORM.HC_MASTER AS
        SELECT
            f.RETAILER, f.TOTAL_MARKET, f.AC_MANUFACTURER, f.AC_BRAND, f.PRODUCT_DESCRIPTION,
            f.BARCODE, f.TIME_PERIODS,
            f.STORES_SELLING, f.UNIT_SALES, f.VALUE_SALES,
            f.UNIT_SALES_PER_STORE, f.VALUE_SALES_PER_STORE, f.PRICE_PER_UNIT,
            r.BRAND AS GA_BRAND, r.BUYER AS GA_BUYER,
            r.GA_CATEGORY, r.GA_SUBCAT, r.GA_SUBCAT2,
            r.FLAV_VARIETY_GEO AS GA_FLAV_VARIETY_GEO,
            r.UNIFIED_PRODUCT_NAME AS GA_UNIFIED_PRODUCT_NAME,
            CASE WHEN r.BARCODE IS NOT NULL THEN 'MATCHED' ELSE 'UNMATCHED' END AS REFERENCE_MATCH_STATUS,
            p.PERIOD_RANK, p.PERIOD_MATX, p.PERIOD_12X, p.PERIOD_4X,
            p.YEAR, p.QUARTER, p.MONTH, p.MONTH_NUMBER, p.WEEK_OF_YEAR
        FROM (
            {union_sql}
        ) f
        LEFT JOIN GOLDENACRE.TRANSFORM.HC_REFERENCE_CLEAN r ON f.BARCODE = r.BARCODE
        LEFT JOIN GOLDENACRE.TRANSFORM.HC_PERIOD_DIM_CLEAN p
            ON f.RETAILER = p.RETAILER AND f.TIME_PERIODS = p.TIME_PERIODS
    """)


def apply_comments(cur):
    for r in RETAILERS:
        t = clean_table(r)
        cur.execute(f"""
            COMMENT ON TABLE GOLDENACRE.TRANSFORM.{t} IS
            'HC build (multi-agents exercise, additive - does not replace CLEAN{r if r != "MORRISONS" else "MORRISON"}). Typed/renamed passthrough of LANDING.{r}, deduped on (BARCODE, TIME_PERIODS) by keeping the single highest-sales row per key. BARCODE kept as VARCHAR (never cast to NUMBER).'
        """)

    cur.execute("""
        COMMENT ON TABLE GOLDENACRE.TRANSFORM.HC_REFERENCE_CLEAN IS
        'HC build. Deduped LANDING.REFERENCE_DATABASE to one row per BARCODE (completeness-score tie-break) - the existing MASTER does not dedup before joining, causing a confirmed +57% row-count fan-out. Excludes blank/{UNATTRIBUTED} barcodes.'
    """)
    cur.execute("""
        COMMENT ON TABLE GOLDENACRE.TRANSFORM.HC_PERIOD_DIM_CLEAN IS
        'HC build. MAT/12WK/4WK period-window classification (same technique as the Vithit build''s RULE-0002), ranked PER RETAILER (not on a shared calendar) because TESCO''s period range does not overlap the other three retailers''.'
    """)
    cur.execute("""
        COMMENT ON TABLE GOLDENACRE.TRANSFORM.HC_MASTER IS
        'HC build (multi-agents exercise). Unions the 4 HC_*_CLEAN tables, LEFT JOINs HC_REFERENCE_CLEAN on TRIM(BARCODE) and HC_PERIOD_DIM_CLEAN on (RETAILER, TIME_PERIODS). Row count should equal the exact sum of the 4 HC_*_CLEAN tables - no fan-out, unlike the existing MASTER. REFERENCE_MATCH_STATUS makes unmatched barcodes explicit rather than a silent NULL.'
    """)


def verify(cur):
    print(f"\n{'=' * 70}\nVerification\n{'=' * 70}")

    clean_counts = {}
    for r in RETAILERS:
        cur.execute(f'SELECT COUNT(*) FROM GOLDENACRE.LANDING.{r}')
        raw_count = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM GOLDENACRE.TRANSFORM.{clean_table(r)}")
        clean_count = cur.fetchone()[0]
        clean_counts[r] = clean_count
        cur.execute(f"""
            SELECT COUNT(*) FROM (
                SELECT BARCODE, TIME_PERIODS FROM GOLDENACRE.TRANSFORM.{clean_table(r)}
                GROUP BY BARCODE, TIME_PERIODS HAVING COUNT(*) > 1
            )
        """)
        dup_remaining = cur.fetchone()[0]
        reduction_pct = (raw_count - clean_count) / raw_count * 100
        print(f"\n--- {r} ---")
        print(f"  raw LANDING row count:     {raw_count:>12,}")
        print(f"  HC_{r}_CLEAN row count:    {clean_count:>12,}  ({reduction_pct:.1f}% reduction from dedup)")
        print(f"  remaining duplicate keys:  {dup_remaining:>12,}  {'OK unique' if dup_remaining == 0 else '*** STILL DUPLICATED ***'}")

    cur.execute("SELECT COUNT(*), COUNT(DISTINCT BARCODE) FROM GOLDENACRE.TRANSFORM.HC_REFERENCE_CLEAN")
    ref_total, ref_distinct = cur.fetchone()
    print(f"\n--- HC_REFERENCE_CLEAN ---")
    print(f"  row count:        {ref_total:>12,}")
    print(f"  distinct BARCODE: {ref_distinct:>12,}  {'OK unique' if ref_total == ref_distinct else '*** DUPLICATE BARCODES REMAIN ***'}")

    for r in RETAILERS:
        cur.execute(f"""
            SELECT PERIOD_MATX, PERIOD_12X, PERIOD_4X FROM GOLDENACRE.TRANSFORM.HC_PERIOD_DIM_CLEAN
            WHERE RETAILER = '{r}' AND PERIOD_RANK = 1
        """)
        rank1 = cur.fetchone()
        expected = ('MAT', '12 WK', '4 WK')
        print(f"\n--- HC_PERIOD_DIM_CLEAN ({r}) rank=1 ---")
        print(f"  MATX={rank1[0]!r} 12X={rank1[1]!r} 4X={rank1[2]!r}  {'OK expected MAT/12 WK/4 WK' if rank1 == expected else '*** UNEXPECTED ***'}")

    cur.execute("SELECT COUNT(*) FROM GOLDENACRE.TRANSFORM.HC_MASTER")
    master_count = cur.fetchone()[0]
    expected_master = sum(clean_counts.values())
    print(f"\n--- HC_MASTER ---")
    print(f"  row count:          {master_count:>12,}")
    print(f"  expected (sum of 4): {expected_master:>12,}  {'OK matches exactly' if master_count == expected_master else '*** MISMATCH - fan-out present ***'}")

    cur.execute("""
        SELECT REFERENCE_MATCH_STATUS, COUNT(*)
        FROM GOLDENACRE.TRANSFORM.HC_MASTER
        GROUP BY REFERENCE_MATCH_STATUS
        ORDER BY REFERENCE_MATCH_STATUS
    """)
    print(f"\n  REFERENCE_MATCH_STATUS breakdown:")
    for status, count in cur.fetchall():
        pct = count / master_count * 100
        print(f"    {status}: {count:,} ({pct:.2f}%)")


def main():
    conn = get_connection(schema="TRANSFORM")
    cur = conn.cursor()
    try:
        # GOLDENACRE_ANALYST_ROLE is only active as a Snowflake *secondary* role here
        # (primary role is VITHIT_ANALYST_ROLE, from .env) - secondary roles grant
        # query/DML access but Snowflake does not allow CREATE TABLE via a secondary
        # role, only via the primary role. Switch primary role for this session to
        # the role that actually owns GOLDENACRE.TRANSFORM's CREATE TABLE grant.
        cur.execute("USE ROLE GOLDENACRE_ANALYST_ROLE")
        cur.execute("USE WAREHOUSE GOLDENACRE_WH")

        for r in RETAILERS:
            print(f"Building {clean_table(r)} ...")
            build_retailer_clean(cur, r)

        print("Building HC_REFERENCE_CLEAN ...")
        build_reference_clean(cur)

        print("Building HC_PERIOD_DIM_CLEAN ...")
        build_period_dim_clean(cur)

        print("Building HC_MASTER ...")
        build_master(cur)

        print("Applying comments ...")
        apply_comments(cur)

        verify(cur)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
