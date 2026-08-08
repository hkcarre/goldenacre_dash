# Golden Acre lineage audit — raw to client deliverable

**Date:** 8 August 2026
**Scope:** `LANDING` → `TRANSFORM` → `OUTPUT` → the three CSVs shared with the client
(`master_gol_new.halal / .other / .polish`, ~324MB).
**Method:** every figure below was re-derived directly from Snowflake and from the CSVs
themselves. Nothing is carried forward from earlier documents; where this audit
contradicts them, the contradiction is stated explicitly and the earlier conclusion
should be treated as withdrawn.

---

## The headline

The client's CSVs are **correct and reproducible from raw data**. Rebuilding the pipeline
from `LANDING` with three rules — deduplicate, normalise the barcode, join a deduplicated
reference — reproduces the client's Halal figure to within 0.02%:

| Halal MAT, 2025-08-09 → 2026-07-25 | Value |
|---|---|
| Rebuilt from raw | £225,553,253 |
| Client CSV | £225,599,328 |
| **Difference** | **−£46,075 (0.02%)** |

**Neither of our two Snowflake layers reproduces it.** Both are wrong, in opposite
directions and for different reasons.

| Halal MAT, same window | Value | vs client |
|---|---|---|
| Client CSV | £225.6m | — |
| Production `MASTER` | £389.1m | **+72.5%** |
| Optia `HC_MASTER` | £195.0m | **−13.6%** |
| Rebuilt correctly | £225.6m | −0.0% |

---

## Layer-by-layer reconciliation

### 1. `LANDING` contains large-scale duplication

The raw feeds carry the same product-week twice, under two barcode formats — a
13-character form with a leading zero and £-formatted value, and a 12-character form with
a plain numeric value:

```
0590055205644   £735.02   4MOVEACTIVEVIT 250ML
 590055205644    735.02   4MOVEACTIVEVIT NULL 250ML
```

Same product, same value, counted twice. For ASDA on 20 June 2026, 2,445 of 2,447
plain-format barcodes overlap the £-formatted feed once normalised.

| Retailer | Raw value | Of which duplicate | True raw |
|---|---|---|---|
| ASDA | £3,930.1m | £1,283.5m | £2,646.7m |
| Morrisons | £1,435.6m | £22.7m | £1,412.9m |
| Sainsbury | £2,089.9m | £403.3m | £1,686.6m |
| Tesco | £1,257.9m | £24.5m | £1,233.4m |
| **Total** | **£8,713.5m** | **£1,733.9m** | **£6,979.6m** |

**Roughly 20% of the raw data is a duplicate of itself.**

### 2. Production's clean layer handles this correctly

`CLEAN*` is exactly "raw minus duplicates". Tesco reconciles to the penny:

| Retailer | Raw − dup | prod `CLEAN*` | Residual |
|---|---|---|---|
| ASDA | £2,646.7m | £2,658.1m | +£11.4m |
| Morrisons | £1,412.9m | £1,417.0m | +£4.1m |
| Sainsbury | £1,686.6m | £1,686.7m | +£0.02m |
| Tesco | £1,233.4m | £1,233.4m | **£0** |

### 3. Production then inflates at the reference join

| | Rows | Value |
|---|---|---|
| Sum of four `CLEAN*` | 2,654,190 | £6,995.1m |
| `MASTER` | 4,161,773 | £10,426.2m |
| **Fan-out** | **×1.568** | **×1.491 (+£3,431.1m)** |

`REFERENCE` is not deduplicated before the join, so rows multiply and value with them.
`OUTPUT.DASHBOARD` equals `MASTER` exactly, and HALAL + POLISH + OTHER + EMPTY reconciles
to it (the 4,482-row gap is the EMPTY bucket). **The inflation is inherited by every
`OUTPUT` segment.**

### 4. The `HC_` layer avoids the fan-out but has two defects of its own

`HC_MASTER` is 3,000,385 rows against 3,000,385 in its four sources — fan-out ×1.000,
the problem it was built to solve. But:

**(a) It never deduplicates the raw feeds.** It carries the £1.73bn of duplication
through, so it overstates ASDA by ~£1.27bn and Sainsbury by ~£0.40bn.

**(b) It never normalises the barcode before the reference join.** Every one of the
846,077 unmatched rows has a 13-character barcode; every barcode of 12 characters or
fewer matches. Applying production's two rules recovers essentially all of it:

| | Value | Share |
|---|---|---|
| Unmatched MAT value | £1,155,536,351 | 100% |
| Recovered by stripping a leading zero | £857,102,450 | 74.2% |
| Recovered by `LEFT(barcode,12)` | £298,342,705 | 25.8% |
| **Recovered by either** | **£1,155,445,156** | **100.0%** |
| Genuinely absent from reference | £91,195 | 0.008% |

---

## Corrections to earlier conclusions

Two findings previously recorded on this project are **wrong** and should not be repeated
to the client or to the pipeline owner.

**1. "Production loses £1.19bn of ASDA value to barcode collisions."** It does not. That
£1.27bn is production correctly collapsing a double-loaded feed. The duplicate value
measured in `LANDING.ASDA` (£1,257.9m) matches the `HC_`-minus-production difference
(£1,267.9m) to 0.8%. `goldenacre_alignment_rules_for_pipeline_owner.md` states this as a
defect; that section is withdrawn.

**2. "The 45.8% unmatched share is a reference-data coverage gap, not a matching-strategy
problem."** The opposite is true. 99.992% of it is a matching-strategy problem, fixed by
normalising the barcode. The earlier check — that the reference's `UPC12` column adds no
incremental matches — was correct in itself but tested the wrong hypothesis.

Both errors share a cause: a difference between two layers was attributed to the other
layer being wrong, without going back to the raw data to establish which was right.

---

## What this means for the dashboard

The dashboard reads `HC_MASTER`, so it inherits both defects. Against the client's own
delivered numbers it understates every category and **reverses the direction of travel**
on two of three:

| Category MAT | Client CSV | Dashboard | CSV YoY | Dashboard YoY |
|---|---|---|---|---|
| Halal | £229.8m | £199.9m | **+5.9%** | **−3.6%** |
| Polish | £241.8m | £199.0m | **+7.6%** | **−2.5%** |
| Other | £1,255.0m | £966.1m | −2.9% | −15.1% |

The reversal is a direct artefact of defect (b): the unclassified bucket grows +8.6% year
on year, draining growth out of the classified categories. The Insights page's line that
"the unclassified bucket is the only segment growing" is that artefact described from the
wrong end.

Metrics not split by `GA_BUYER` — total value, units, price per unit — are unaffected by
the classification defect, though still affected by the duplication.

---

## Recommended fixes, in order

1. **Deduplicate on ingest**, keying on (normalised barcode, retailer, week). Removes
   £1.73bn of phantom value from `HC_`. Production already does this.
2. **Normalise the barcode before the reference join** in `HC_`: strip a leading zero from
   13-character barcodes beginning `0`, otherwise `LEFT(...,12)`. Takes the unclassified
   share from 45.8% to ~0.008%.
3. **Deduplicate `REFERENCE` before the join in production.** This is the real production
   bug and the only one of the three that is genuinely theirs: ×1.568 row fan-out,
   +£3.43bn. Worth raising with Pankaj.
4. **Re-promote `OUTPUT.EMPTY`**, still stale at 43 rows and one column.

Rebuilt with rules 1 and 2, the numbers land on the client's within 0.02% for Halal.
Polish (−6.0%) and Other (+2.5%) remain a few percent out, most likely reference-vintage:
ours was last loaded 2026-07-22 and the client's export post-dates it.

---

## Data-freshness note

The CSVs run to **2026-08-01**. `LANDING` currently holds nothing after 2026-07-25/26, so
the client is working from an extract that does not exist anywhere in this Snowflake
account. That week accounts for £4.2m of Halal (1.8%) and is not a material part of the
discrepancy, but it does mean **Snowflake is not currently the system of record for what
the client has been given.**
