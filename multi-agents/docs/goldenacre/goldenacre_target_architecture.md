# Golden Acre HC_ target architecture

Second applied instance of the multi-agent harmonization framework (first: Vithit's `HC2_*` build, see `docs/vithit/vithit_target_architecture.md`). Built and verified against live data 2026-07-29. Mirrors the role of the Vithit exercise's Transformation Design + Validation phases.

## Why a new layer, not a fix to the existing pipeline

`GOLDENACRE.TRANSFORM`/`GOLDENACRE.OUTPUT` already run a real, separate, sqlmesh-managed pipeline feeding a live Power BI dashboard (`docs/goldenacre/goldenacre_raw_assessment.md` has the full profiling). It has two confirmed bugs (barcode cast to `NUMBER(38,0)` loses leading zeros/can't hold `{UNATTRIBUTED}`; `MASTER`'s reference join fans out +57% because `REFERENCE_DATABASE`'s 515 duplicate barcodes aren't deduped first) but fixing it in place wasn't requested and isn't in scope here - this build is additive only, prefixed `HC_`, and never references or writes to any pre-existing object.

## Build

```
GOLDENACRE.LANDING.ASDA/MORRISONS/SAINSBURY/TESCO
        v  (type-cast, dedupe on (BARCODE, TIME_PERIODS))
HC_ASDA_CLEAN / HC_MORRISONS_CLEAN / HC_SAINSBURY_CLEAN / HC_TESCO_CLEAN
        |
        +-- GOLDENACRE.LANDING.REFERENCE_DATABASE -> HC_REFERENCE_CLEAN (deduped)
        +-- per-retailer TIME_PERIODS -> HC_PERIOD_DIM_CLEAN (MAT/12WK/4WK bands)
        v
HC_MASTER
```

Script: `multi-agents/scripts/build_goldenacre_hc.py`. `CREATE OR REPLACE TABLE`, idempotent, scoped only to these 7 `HC_` names - safe to re-run as `LANDING` refreshes.

## Decisions and the evidence behind them

**Dedup rule: keep the single highest-sales row per `(BARCODE, TIME_PERIODS)`, don't sum.** A live diagnostic query (not assumption) checked what ASDA's 505 and MORRISONS' 4,031 duplicate-key groups actually contain:
- ASDA: 100% have fully identical `UNIT SALES`/`VALUE SALES` across the group (differing only in `Product Description`) - summing would double-count real sales.
- MORRISONS: a full re-classification of all 4,031 groups (not the small hand-picked sample this doc originally cited - see the QA section below) shows ~89% resolve to identical cleaned measures (ASDA-like), ~8.6% (348 groups) are two genuinely different real listings with materially different non-zero sales, and only ~2.4% are the illustrated real-row-plus-zero-sales-placeholder pattern.

A single blanket "sum the duplicates" rule (the first draft of this design) was wrong precisely because it's right for one retailer's failure mode and wrong for the other's. `QUALIFY ROW_NUMBER() OVER (PARTITION BY BARCODE, TIME_PERIODS ORDER BY UNIT_SALES DESC, VALUE_SALES DESC, PRODUCT_DESCRIPTION) = 1` never double-counts (unlike summing), which is why it's still the right default - but it isn't lossless: for Morrisons' ~348 "two different real listings" groups, a materially-sized alternate sales record is silently discarded. That's a genuine, disclosed limitation, not a fully solved case.

**`BARCODE` stays `VARCHAR` everywhere, never cast to `NUMBER`.** Direct fix vs. the existing `MASTER`, which casts to `NUMBER(38,0)` and loses leading zeros on EAN-13 codes.

**`HC_REFERENCE_CLEAN` deduped before any join (completeness-score tie-break).** Fixes the existing `MASTER`'s confirmed +57% row-count fan-out (4,140,716 actual vs. 2,639,356 expected from summing its 4 sources) - caused by not deduping `REFERENCE_DATABASE`'s 515 duplicate-barcode groups before joining.

**Plain `TRIM(BARCODE)` join, no `UPC12` fallback.** A live diagnostic checked whether the reference table's separate `UPC12` column would rescue any match that `BARCODE` alone misses, across all four retailers. Result: `UPC12` contributed **zero incremental matches** everywhere - the union of "matched on BARCODE" and "matched on UPC12" equalled "matched on BARCODE" exactly, every time. Building fallback-match complexity wasn't justified by the evidence.

**Period-window rank computed per retailer, not on a shared calendar.** All four retailers actually span the same 211-week history (09/10 JUL 2022 - 18/19 JUL 2026) - an earlier version of this doc wrongly claimed Tesco's range didn't overlap the others' (see the QA section below for how that was caught and corrected). The real reason to partition by retailer: Tesco's week-ending date is offset by exactly 1 calendar day from the other three, every single week, with zero exact-date matches across all 211 weeks. A global `RANK() OVER (ORDER BY TIME_PERIODS DESC)` across all retailers would therefore scramble every retailer's MAT/12WK/4WK bands throughout the entire history (not just at the edges, as the original wrong justification implied), since Tesco's dates would constantly interleave with and displace the others' ranks. `HC_PERIOD_DIM_CLEAN` instead ranks `PARTITION BY RETAILER` - the same reasoning the original Vithit build used to keep period windows scoped per category rather than merged across categories, just for a date-offset reason here rather than a date-range reason.

**`REFERENCE_MATCH_STATUS` column added to `HC_MASTER`.** Makes the ~1/3 of distinct barcodes with no reference row (a genuine reference-data coverage gap this build can't fix - fixing it means the client adding more product mappings, not a transformation change) explicit and queryable, rather than a silent `NULL` a Power BI report might drop unnoticed.

## Verification (run 2026-07-29, `verify()` in `build_goldenacre_hc.py`)

Row counts below are unchanged after the `NUMBER(38,4)` precision fix (rebuilt post-QA-pass) - the fix corrected column scale, not row selection.

| Check | Result |
|---|---|
| ASDA raw -> `HC_ASDA_CLEAN` | 989,708 -> 989,203 (505 exact duplicate keys collapsed, 0.1%) |
| MORRISONS raw -> `HC_MORRISONS_CLEAN` | 1,200,830 -> 1,196,799 (4,031 duplicate keys collapsed, 0.3%) |
| SAINSBURY / TESCO raw -> clean | unchanged (no duplicate keys existed) |
| Remaining duplicate `(BARCODE, TIME_PERIODS)` keys, all 4 tables | **0** |
| `HC_REFERENCE_CLEAN` row count vs. distinct `BARCODE` | 21,185 = 21,185 - **unique** |
| `HC_PERIOD_DIM_CLEAN` rank=1 classification, all 4 retailers | `MAT` / `12 WK` / `4 WK` as expected |
| `HC_MASTER` row count vs. sum of the 4 clean tables | 2,983,943 = 2,983,943 - **exact match, no fan-out** |
| `HC_MASTER.REFERENCE_MATCH_STATUS` | MATCHED 2,149,645 (72.04%) / UNMATCHED 834,298 (27.96%) |
| Pre-existing objects (before/after row-count + `SHOW TABLES/VIEWS` check) | **Unchanged** - all 6 `TRANSFORM` views and 5 `OUTPUT` views identical row counts, identical object lists; the 7 new tables are additive |

## Independent QA pass (2026-07-29): hallucination check + adversarial validation

Before this layer was declared ready for downstream visualization work, two independent subagents re-tested it - mirroring the Hallucination Detection Agent and Validation/Challenge Agent roles from the Interbev/Vithit exercise (`agents/hallucination_agent.md`, `agents/validation_agent.md`), which is the standard this framework holds itself to, not a formality skipped for a second client. Neither pass rubber-stamped the build; both found real problems.

**Hallucination check** (re-tested every quantitative claim in this doc and the raw assessment against live data, independently of the build's own `verify()` output): confirmed 16 of 18 tested claims exactly as stated, including the headline numbers (row counts, dedup counts, the `UPC12` zero-incremental-match finding, `HC_MASTER`'s exact-match row count). Found two real problems, both corrected above and in `goldenacre_raw_assessment.md`: the Tesco period-range claim was fabricated relative to live data, and the Morrisons duplicate-pattern narrative was overstated from a 2-3 example sample rather than measured across all 4,031 groups.

**Adversarial validation** (stress-tested the built tables for defects the build's own checks wouldn't catch): found one severe, real defect - `TRY_TO_NUMBER()` with no explicit scale defaults to `NUMBER(38,0)`, silently rounding `VALUE_SALES`, `PRICE_PER_UNIT`, `VALUE_SALES_PER_STORE`, and `UNIT_SALES_PER_STORE` to whole numbers. Confirmed damaging 53-68% of rows depending on retailer/column (any row whose raw value had a decimal component). **Fixed**: `numeric_cast()` in `build_goldenacre_hc.py` now casts to `NUMBER(38,4)` explicitly; all 7 tables rebuilt and re-verified (row counts unchanged, since the fix only changed scale, not row selection; spot-checked fractional `PRICE_PER_UNIT` values now survive, e.g. `1.7300` where they'd previously stored as `2`). Everything else this pass checked - date parsing, dedup completeness, join correctness (including confirming "unmatched" rows are genuinely absent from the reference table, not a join-key formatting bug), and period-window band boundaries beyond just rank=1 - held up with no defects found.

## Known limitations (not fixed by this build, flagged deliberately rather than silently)

1. **Reference coverage gap**: ~28% of `HC_MASTER` rows (by row count; ~1/3 by distinct barcode) have no `REFERENCE_DATABASE` match at all - confirmed not a matching-strategy problem (see `UPC12` diagnostic above), it's missing reference data. Only the client's reference team adding more product mappings can close this.
2. **Tesco period non-comparability**: because Tesco's week-ending date is offset by 1 day from the other three retailers' every week (not because of a date-range gap - see the QA correction above), any cross-retailer trend analysis using `PERIOD_MATX`/`PERIOD_12X`/`PERIOD_4X` should not assume the bands line up on the same real-world calendar weeks across retailers - each retailer's bands are relative to its own latest available period.
3. **Description tie-break heuristic**: where a duplicate key's two rows differ only in `PRODUCT_DESCRIPTION` (the ASDA pattern), the kept description is whichever sorts first alphabetically after the sales-based tie-break - not a business-validated "correct" description, just a deterministic choice.
4. **Morrisons dedup is lossy for ~348 keys**: found by the adversarial validation pass - where a duplicate group is genuinely two different real listings with materially different non-zero sales (not the identical-measures or zero-placeholder patterns), keeping only the higher-sales row discards a real, non-trivial sales record for that key.
5. **ASDA's existing `CLEANASDA` view removes 26.1% of rows vs. raw LANDING**; `HC_ASDA_CLEAN` only removes 0.1% (the confirmed duplicate keys). This difference is expected, not a discrepancy to reconcile - the existing view's extra filtering logic isn't visible via `GET_DDL` (it's inside an sqlmesh model), and this build deliberately only removes what's evidenced (duplicate keys), not an unexplained additional cut.
