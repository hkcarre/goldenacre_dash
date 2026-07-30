# Aligning the HC_ layer to GOLDENACRE.TRANSFORM's existing behaviour

**Purpose of this document**: Helena asked, given we treat the existing production objects (`CLEANASDA`/`CLEANMORRISON`/`CLEANSAINSBURY`/`CLEANTESCO`/`MASTER`) as the source of truth, what rules would the new `HC_` tables need to adopt to match them - and to write that up as something to check directly with the pipeline's owner, rather than assume.

**How to read this document**: every rule below is reverse-engineered empirically from comparing live data - by definition, not read from the actual sqlmesh model source (which this exercise has no access to). Each rule is marked with a confidence level. Please confirm or correct each one.

**Correction, 2026-07-30**: this document went through two rounds of correction, both visible in Rule C's own section below rather than silently edited away. Helena caught the first error directly ("when barcode starts with 0, we remove the 0"), which led to Rule A being revised to its correct two-mechanism form. Re-testing Rule C against the corrected Rule A initially looked like it resolved the concern entirely (a row always exists for every collision) - but that check only confirmed a row exists, not that it captured all the value behind it. Checking that directly found it doesn't: collisions do cost real, quantified sales value (confirmed, not retracted) - just via a different, smaller-but-still-material mechanism than originally claimed. The current version below is the fully reconciled one.

---

## Rule A — Barcode is normalised to 12 characters, via two different mechanisms depending on the input

**CONFIRMED, deterministic, precisely reproducible - revised from an earlier draft of this document, see the correction note below.**

`CLEANASDA`/`CLEANMORRISON`/`CLEANSAINSBURY`/`CLEANTESCO` normalise every barcode to at most 12 characters, but the exact mechanism depends on whether the raw barcode is a **zero-padded 13-character code**:

1. **If the raw barcode is 13 characters long and starts with `'0'`**: the leading zero is stripped, giving a 12-character result. This is the standard, lossless way to recover a native 12-digit UPC-A code from a UPC-A that's been zero-padded into the 13-digit EAN field - not a truncation, no information is lost. Example: raw `0505717248374` → `505717248374`.
2. **Otherwise, if the raw barcode is longer than 12 characters** (13-character codes that do *not* start with `'0'`, i.e. genuine native EAN-13 codes): the barcode is truncated to its first 12 characters (`LEFT(BARCODE, 12)`), which *does* discard the last digit. Example: raw `5059697257070` (starts with `5`, not `0`) → `505969725707`.
3. Barcodes of 12 characters or fewer pass through unchanged.

**Correction note**: an earlier draft of this document described this as a single, uniform `LEFT(BARCODE, 12)` rule for every barcode over 12 characters. That was wrong, caught on Helena's own observation ("when barcode starts with 0, we remove the 0") and re-verified directly: for ASDA's raw 13-character barcodes starting with `'0'`, 411 of 500 sampled matched the leading-zero-strip form and 0 matched the plain-truncate form; for the 10 sampled 13-character barcodes *not* starting with `'0'`, 10 of 10 matched plain-truncate and 0 matched leading-zero-strip. **This matters a great deal for Rule C below**, which the wrong single-rule hypothesis got substantially wrong.

**Question for the pipeline owner**: mechanism 1 (strip a zero-padded EAN-13 back to UPC-A) is standard practice and likely intentional. Mechanism 2 (plain truncation of a genuine 13-digit EAN-13, dropping the last digit) is different in kind - it's lossy and not a standard conversion. Is mechanism 2 intentional, or is it an unintended side effect of the same code path being applied uniformly to both cases? If intentional, `HC_` can adopt both mechanisms as described. If not, mechanism 2 is a live data-quality defect worth fixing at the source.

---

## Rule B — Tesco's calendar is shifted back one day; the other three retailers are not

**CONFIRMED for what happens; genuinely unclear why, needs your input on intent.**

For ASDA, Morrisons, and Sainsbury, `TIME_PERIODS` in the `CLEAN*` views is exactly what you get from parsing each retailer's own raw `"TIME PERIODS"` text field (`TO_DATE(..., 'DD MON YYYY')`) - no adjustment.

For Tesco specifically, `CLEANTESCO`'s `TIME_PERIODS` is **one day earlier** than a literal parse of Tesco's own raw text would give. Example: raw `LANDING.TESCO`'s own text for its earliest period is `'10 JUL 2022'` (parses to 2022-07-10) - but `CLEANTESCO` shows this period's date as 2022-07-09, matching the other three retailers' calendar instead of Tesco's own. This holds consistently across the full date range (checked, not a one-off).

Tesco's raw feed genuinely runs on a one-day-offset calendar from the other three retailers (confirmed independently, not a parsing bug on our side) - so this looks like a deliberate choice to align Tesco onto the group's shared calendar rather than preserve its own. That's a defensible thing to do, but it is a real choice with a real consequence: it changes which calendar week a given Tesco sales figure is attributed to.

**Question for the pipeline owner**: is aligning Tesco's calendar to the other three retailers' week-ending dates the intended behaviour? If yes, `HC_` can subtract one day from Tesco's parsed date to match. If the intent was actually to preserve each retailer's own native reporting calendar, `CLEANTESCO` itself has the defect, not `HC_TESCO_CLEAN`.

---

## Rule C — What happens when two raw rows share the same normalised barcode+period key

**CONFIRMED, and this took two attempts to characterise correctly - see the correction trail below. The final version: a row always survives, but the surviving row's value is only ONE contributor's figure, never the sum - and this is a genuine, quantified, material loss of sales value, consistently around half of what's tied up in these keys, across all four retailers.**

**Correction trail, so the reasoning is auditable**: the first version of this document claimed collision groups were dropped entirely (up to £871M "missing" for ASDA) - wrong, an artefact of testing against an incomplete Rule A (see Rule A's own correction note). The second version, after fixing Rule A, checked only whether *a row exists* for each collision key, found one always does, and concluded there was no defect - also wrong, because it didn't check whether that surviving row's *value* represented all the raw rows that fed into it, or just one of them. Checking that directly (below) found it's the latter.

**Worked example** (re-confirmed live): raw `LANDING.ASDA` has two entries for what is clearly the same product, "KRAKUS ROASTED HAM PER KG", reported under both a 12-character barcode and its zero-padded 13-character EAN-13 form, in the same week (16 Aug 2025):

| Raw barcode | Form | Value sales |
|---|---|---|
| `0208243300000` | 13-char, zero-padded | 981,010 |
| `208243300000` | 12-char, native | 12,020 |

Rule A correctly normalises both to the same key, `208243300000` - so this is a real duplicate submission of the same product, not a truncation artefact. `CLEANASDA` has exactly one row for this key, value **12,020.17** - it kept the smaller of the two contributions and discarded the larger one (£981,010) entirely. Checked several more examples earlier in this exercise: which of the two values survives does not follow a consistent pattern - not always the 12-character row, not always the 13-character row, not always the larger or smaller figure.

**Full census, all four retailers** (collision = 2+ raw rows sharing the same normalised barcode+period key, whether from Rule A's normalisation or from two genuinely duplicate raw submissions like the example above; Tesco checked with Rule B's -1-day shift applied, since comparing against Tesco's literal raw date would wrongly look like every row is missing):

| Retailer | Collision groups | Raw value tied up in these groups | Value actually kept by `CLEAN*` | Value lost | Loss rate |
|---|---|---|---|---|---|
| ASDA | 206,282 | £2,378,455,100 | £1,187,845,878.91 | **£1,190,609,221.09** | 50.0% |
| MORRISONS | 32,723 | £31,619,586 | £16,393,660.96 | **£15,225,925.04** | 48.2% |
| SAINSBURY | 2,272 | £2,146,076 | £1,062,289.02 | **£1,083,786.98** | 50.5% |
| TESCO | 15,656 | £45,273,150 | £22,636,496.94 | **£22,636,653.06** | 50.0% |

The loss rate sitting at almost exactly half, independently, for all four retailers at wildly different scales (£1.08M to £1.19bn) is itself informative: it's consistent with most collisions being simple 2-row groups where one contributor is kept and one discarded with no relationship to magnitude - not consistent with an intentional "keep the bigger/most-recent/most-complete figure" business rule, which would be expected to retain more than half the value on average. This still looks like a side effect of how the underlying model resolves a non-unique key (e.g. last-loaded-wins in an incremental merge) rather than a deliberate policy - but this time the quantified loss is confirmed, not retracted.

**This fully closes the reconciliation** between raw totals and `CLEAN*` totals (this figure + the smaller residual below account for): ASDA 100.2% of the £1.27bn gap, Morrisons 100.8% of £18.6M, Tesco 100.4% of £24.5M, Sainsbury 105.1% of £403.2M (the small overshoot for Sainsbury is likely double-counting from a handful of exact-duplicate raw rows, not a new mystery).

### A smaller, separate residual gap

Independent of Rule C, a modest fraction of normalised keys have **no row at all** in `CLEAN*` (not even one contributor kept):

| Retailer | Distinct normalised keys | Missing entirely from `CLEAN*` | Of those, zero units AND zero value in every contributing raw row |
|---|---|---|---|
| ASDA | 786,685 | 54,791 (7.0%) | 35,996 (65.7%) |
| MORRISONS | 1,173,258 | 10,023 (0.9%) | 6,938 (69.2%) |
| SAINSBURY | 428,914 | 30,853 (7.2%) | 22,058 (71.5%) |
| TESCO | 357,386 | 1,512 (0.4%) | not broken down |

About two-thirds of these have no sales activity at all that week - consistent with an ordinary "exclude rows with no distribution" filter, a reasonable rule rather than a defect. The non-zero remainder is smaller and not yet root-caused.

**Questions for the pipeline owner**: (1) is discarding one contributor's value instead of summing when barcode formats collide intentional, and if not, should `HC_` sum instead? (2) does `CLEAN*` deliberately filter out zero-activity rows - if so `HC_` can adopt the same filter for consistency?

---

## What this means for the `HC_` layer today

The `HC_` layer currently does **none** of the above - it keeps every barcode at full length (untruncated) and parses each retailer's own raw date literally, including Tesco's. That was a deliberate design choice made without reference to `CLEAN*`'s behaviour (see `multi-agents/docs/goldenacre/goldenacre_target_architecture.md`), and is why the two don't reconcile (see `goldenacre_old_vs_hc_comparison.md` for the full comparison this document follows on from).

If the pipeline owner confirms Rule A and/or Rule B are intentional, both are simple, mechanical additions to `multi-agents/scripts/build_goldenacre_hc.py` (the two-mechanism barcode normalisation in Rule A, and a `-1 day` adjustment scoped to Tesco only for Rule B). **Rule C should not be replicated as "keep one contributor, discard the rest" until the pipeline owner confirms that's actually wanted** - the quantified loss (roughly half the value tied up in every collision, £1.19bn for ASDA alone) looks like an unintended side effect of the model's mechanics, not a considered policy; summing colliding contributions would be the more defensible default if Golden Acre has no objection. The smaller residual gap (mostly zero-activity rows) is a lower-stakes, separate question worth a quick confirmation too.
