# Golden Acre raw data assessment (Discovery + Profiling phases)

Read-only findings from live Snowflake, captured 2026-07-29, ahead of building the `HC_` harmonization layer in `GOLDENACRE.TRANSFORM`. Mirrors the role of `docs/vithit/vithit_raw_assessment.md` for the Vithit exercise.

## LANDING schema (raw)

`ASDA`, `MORRISONS`, `SAINSBURY`, `TESCO` share an identical raw schema - weekly retail sales facts, everything `VARCHAR`, no typing applied at landing:

| Column | Notes |
|---|---|
| `Total Market` | constant `'TOTAL'` within every observed duplicate-key group |
| `AC_MANUFACTURER`, `AC_BRAND` | `{UNATTRIBUTED}` placeholder in 8-25% of rows depending on retailer |
| `Product Description` | free text |
| `BARCODE` | mixed formats: 12-digit UPC, 13-digit EAN with leading zero, 6-digit in-house codes |
| `TIME PERIODS` | text date, e.g. `'29 JUL 2023'` |
| `STORES SELLING`, `UNIT SALES`, `VALUE SALES`, `Unit Sales per Store`, `Value Sales per Store`, `Price Per Unit` | numeric-looking strings, mixed plain (`10943.27`) and currency-formatted (`£6,375.85`) |

Row counts and headline DQ findings:

| Table | Rows | Distinct barcodes | Dup (BARCODE, TIME PERIODS) groups | Period range |
|---|---|---|---|---|
| ASDA | 989,708 | 6,935 | 505 | 09 JUL 2022 - 18 JUL 2026 (211 weeks) |
| MORRISONS | 1,200,830 | 6,741 | 4,031 | 09 JUL 2022 - 18 JUL 2026 (211 weeks) |
| SAINSBURY | 429,343 | 2,446 | 0 | 09 JUL 2022 - 18 JUL 2026 (211 weeks) |
| TESCO | 368,598 | 2,244 | 0 | 10 JUL 2022 - 19 JUL 2026 (211 weeks) |

**Correction (2026-07-29, caught by an independent hallucination-check pass)**: an earlier version of this doc claimed Tesco's range (Dec 2024-May 2026) didn't overlap the other three retailers' (Apr 2023-May 2025). That was wrong - re-verified directly against `TIME_PERIODS` in the built `HC_*_CLEAN` tables, all four retailers span the identical 211-week history above. What IS true and independently confirmed: Tesco's week-ending date is offset by exactly 1 calendar day from the other three, every single week, with **zero exact-date matches** across all 211 dates (`SELECT COUNT(*) FROM HC_ASDA_CLEAN a JOIN HC_TESCO_CLEAN t ON a.TIME_PERIODS = t.TIME_PERIODS` returns 0). A period-window rank computed on a shared calendar would still scramble every retailer's bands throughout the full history because of this offset - not just at the edges as the original (wrong) non-overlap claim implied - so the per-retailer partitioning in `HC_PERIOD_DIM_CLEAN` is still the right call, just for a different reason than originally stated.

### Duplicate-key diagnostic (ran directly against Snowflake, not inferred)

- **ASDA (505 groups)**: 100% have fully identical `UNIT SALES`/`VALUE SALES` across the group (max group size 2), differing only in `Product Description` (e.g. barcode `0505407090912` appears as both `'ASDA TURKEY WTHIN 200G'` and `'ASDA TURKEY WTHIN 150G'` for the same period, same sales figures). `TOTAL_MARKET` and `AC_MANUFACTURER` never vary within a group. **Summing these would double-count real sales.**
- **MORRISONS (4,031 groups)**: a first-pass sample (2-3 examples) suggested the dominant pattern was a real, positive-sales row paired with a companion row literally labelled `'UNKNOWN PRODUCT_<barcode>'` at zero sales. **Correction (2026-07-29, caught by an independent validation pass that measured all 4,031 groups rather than trusting the small sample)**: re-classifying every group through the build's own numeric-cleaning logic (not raw-string comparison, which is skewed by cosmetic byte-encoding artifacts in the currency symbol) gives a materially different picture:
  - **~89% (3,586 groups)** resolve to identical cleaned measures - the same pattern as ASDA's, not the zero-sales-companion pattern.
  - **~8.6% (348 groups)** are two genuinely different real listings with materially different, non-zero sales (e.g. barcode `5010251795506`: one row 1,379 units/£2,933, the other 15,080 units/£27,348) - for these, keeping only the higher-sales row silently discards a real, non-trivial sales record. This is a genuine, if small, known limitation of the dedup rule, not a harmless simplification.
  - **~2.4% (~97 groups)** are the originally-illustrated real-row-plus-zero-sales-`UNKNOWN PRODUCT`-companion pattern, where summing or keeping-the-max both happen to give the same, correct answer.

  Regardless of which pattern applies, the build's actual rule - keep the single highest-`UNIT_SALES`/`VALUE_SALES` row per `(BARCODE, TIME PERIODS)` key - remains the right default (it never double-counts, unlike a blanket sum), but the 8.6% "two different real listings" case means it isn't lossless: a materially-sized alternate sales record is discarded for those ~348 keys.

### `REFERENCE_DATABASE`

21,829 rows, single snapshot (`SNAPSHOT_DATE = '072026'`). Columns: `BARCODE, "RETAILER PRODUCT DESCRIPTION", UPC12, "UNIFIED PRODUCT NAME", BRAND, BUYER, "GA CATEGORY", "GA SUBCAT", "GA SUBCAT2", "FLAV/ VARIETY/GEO", WT, WTG, Retailer, SNAPSHOT_DATE`.

- 515 duplicate-`BARCODE` groups (up to 8 rows for one barcode), including an 11-row group under the literal placeholder barcode `{UNATTRIBUTED}`.
- `BUYER` holds the category values `HALAL`/`POLISH`/`OTHER` that drive the existing `OUTPUT` schema segmentation.
- Barcode length profile: 12-digit (12,752 rows) and 13-digit (6,771) dominate, with a real tail of shorter in-house codes (11/6/7/4/5/8/3/9-digit, totalling ~2,300 rows).

**Barcode/UPC12 match-rate diagnostic** (ran directly against Snowflake): checked whether the reference table's separate `UPC12` column would rescue any fact-table barcode that a plain `BARCODE`-to-`BARCODE` match misses.

| Retailer | Distinct fact barcodes | Matched on BARCODE | Matched on UPC12 | Matched via either |
|---|---|---|---|---|
| ASDA | 6,935 | 4,419 | 4,412 | 4,419 |
| MORRISONS | 6,741 | 4,487 | 512 | 4,487 |
| SAINSBURY | 2,446 | 1,683 | 449 | 1,683 |
| TESCO | 2,244 | 1,520 | 219 | 1,520 |

**Matched via either == matched on BARCODE in every case** - `UPC12` contributes zero incremental matches anywhere. A plain `TRIM(BARCODE) = TRIM(BARCODE)` join is empirically as effective as a normalized/fallback join would be; the added complexity isn't justified by the evidence.

Distinct-barcode match rate is ~64-69% per retailer - a genuine reference-data coverage gap (a long tail of barcodes with no reference row at all), not something a matching-strategy change can fix. Row-level coverage is expected to be much higher than this distinct-barcode rate suggests, consistent with the existing `OUTPUT.EMPTY` bucket being only 0.03% of rows - high-volume products are well covered, the gap is concentrated in low-frequency long-tail barcodes.

## Existing TRANSFORM/OUTPUT pipeline (sqlmesh-managed, read-only reference only)

`CLEANASDA`/`CLEANMORRISON`/`CLEANSAINSBURY`/`CLEANTESCO`: thin views over sqlmesh physical tables, renaming columns and casting numerics/dates. Row counts are lower than raw LANDING by 3.5-26.1% depending on retailer (ASDA's 26.1% cut is the largest and its cause wasn't traceable from view DDL alone - the view is a passthrough of an sqlmesh model not visible via `GET_DDL`).

`MASTER`: unions the 4 clean views, adds a `RETAILER` column, and `LEFT JOIN`s `REFERENCE` on raw `BARCODE`. Two confirmed issues:
1. `BARCODE` is cast to `NUMBER(38,0)` here - loses leading zeros on EAN-13 codes and can't represent the `{UNATTRIBUTED}` placeholder.
2. Row count is **4,140,716**, which is **57% more** than the sum of the 4 clean views (2,639,356) - confirmed caused by the 515 duplicate-barcode reference groups fanning out the join (no dedup applied before joining).

`OUTPUT.DASHBOARD/HALAL/POLISH/OTHER/EMPTY`: `HALAL + POLISH + OTHER + EMPTY = DASHBOARD` exactly, partitioned by `MASTER.GA_BUYER` (`EMPTY` = `GA_BUYER IS NULL`, 1,040 rows / 0.03%).

## Object inventory / collision check

`SHOW TABLES/VIEWS` confirms: `TRANSFORM` and `OUTPUT` each hold views only (no tables) under the names listed above; `LANDING` holds tables only. An `INFORMATION_SCHEMA.TABLES` check with `ILIKE 'HC\_%'` across `LANDING`/`TRANSFORM`/`OUTPUT` returned zero matches - the `HC_` prefix is collision-free for the new build.

## What this means for the HC_ build

See `goldenacre_target_architecture.md` for the full design; headline decisions this assessment drove:
1. Numeric cleaning must handle both plain and currency-formatted strings (regex-strip non-numeric characters, not a literal `£` replace, since the exact byte sequence stored couldn't be confirmed from a terminal sample alone).
2. Duplicate `(BARCODE, TIME PERIODS)` keys are resolved by keeping the single highest-sales row per key, not by summing - a blanket SUM would double-count ASDA's identical-duplicate pattern.
3. `BARCODE` stays `VARCHAR` throughout, never cast to `NUMBER`.
4. `REFERENCE_DATABASE` is deduped to one row per barcode (completeness-score tie-break) before any join, to avoid repeating `MASTER`'s +57% fan-out.
5. Period-window classification (MAT/12WK/4WK, reusing the same technique as Vithit's RULE-0002) is computed **per retailer**, not on a shared calendar rank, because of Tesco's non-overlapping date range.
6. A `TRIM(BARCODE)` join to the reference table is sufficient - confirmed by direct measurement, not assumed.
