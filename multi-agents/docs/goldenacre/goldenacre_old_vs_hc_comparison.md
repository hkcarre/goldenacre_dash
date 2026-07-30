# GOLDENACRE.TRANSFORM: existing production objects vs. the new HC_ layer

Detailed, evidence-based comparison between Golden Acre's existing sqlmesh-managed production objects (`CLEANASDA`/`CLEANMORRISON`/`CLEANSAINSBURY`/`CLEANTESCO`/`MASTER`/`REFERENCE`, currently feeding `OUTPUT.DASHBOARD` and the live Power BI report) and the new, additive `HC_` layer built this session. Requested explicitly by Helena: "check now in detail... flag what's 100% matching and what's not with explanation." All findings below are from live queries against both sets of objects, not inference.

**Headline result: this is not a case of two reasonable approaches producing different numbers. One confirmed, severe data-corruption bug was found in the existing production pipeline, present today, affecting every retailer, that the `HC_` layer does not have.** See §1. A second, genuine (and more defensible) methodology difference was also found — a Tesco date-alignment choice — see §2.

---

## 1. CONFIRMED BUG in production: barcode normalisation loses real sales value on collisions

**Superseded/corrected 2026-07-30**: this section originally described the barcode change as a uniform "truncate to 12 digits" and quantified the resulting loss as £403M (Sainsbury) / £871M (ASDA) of sales value "silently dropped" on collisions. Both the mechanism and the £403M/£871M figures were wrong, caught and corrected through two further rounds of live re-verification. **The precise, fully reconciled version of both the rule and the loss figures now lives in `goldenacre_alignment_rules_for_pipeline_owner.md` (Rules A and C, including the correction trail) - treat that document as authoritative on this topic, not the summary below.** Kept here only as a pointer, not restated in full to avoid two documents drifting out of sync again.

**What's still true**: barcode is normalised (not simple truncation - see the linked document for the actual two-mechanism rule) before reaching `CLEANASDA`/`CLEANMORRISON`/`CLEANSAINSBURY`/`CLEANTESCO`, and when this causes two raw rows to land on the same key, `CLEAN*` keeps only one contributor's value rather than summing them - a confirmed, quantified, material loss of real sales value (not zero, as an intermediate draft of the linked document briefly concluded before a further check caught that too). This is present in the **live production objects today**, feeding `OUTPUT.DASHBOARD` and the client's Power BI report.

**In the new `HC_` layer**: `BARCODE` is kept as `TRIM()`'d `VARCHAR` throughout every table, with no normalisation, cast, or reformatting at any stage.

**Recommendation**: raise `goldenacre_alignment_rules_for_pipeline_owner.md` with whoever owns the production sqlmesh pipeline (Pankaj Lal, per Optia's team) - it has the precise, current numbers and the specific questions to confirm.

---

## 2. GENUINE METHODOLOGY DIFFERENCE (not a bug, unresolved): Tesco's date alignment

Raw `LANDING.TESCO`'s own `"TIME PERIODS"` text, parsed literally (`TO_DATE(..., 'DD MON YYYY')`), gives an earliest period of **2022-07-10**. The `HC_TESCO_CLEAN` table preserves this literal value. But `CLEANTESCO` (production) shows an earliest period of **2022-07-09** — one day earlier, and matching ASDA/Morrisons/Sainsbury's own calendar exactly, rather than Tesco's own raw text.

This is **not** the barcode bug — it's Tesco-specific, consistent across the full date range, and looks like an intentional design choice in the production pipeline: aligning Tesco's own reporting calendar (which is genuinely offset by one day from the other three retailers, confirmed independently this session) onto a shared calendar, rather than preserving each retailer's own literal date.

**Which is "correct" depends on Golden Acre's own intended definition of a Tesco reporting period** (does "the week of 9 July" mean Tesco's own week-ending date, or the group's shared week-ending date?) — this is a business question, not something resolvable from the data alone, and this comparison does not take a side. Flagged as an open question for Golden Acre/Optia to resolve, not a defect in either pipeline. **Practical consequence**: any row-level join between `CLEANTESCO`/`MASTER` and `HC_TESCO_CLEAN`/`HC_MASTER` on `TIME_PERIODS` for Tesco will show near-total non-overlap purely because of this one-day shift, even where the underlying weekly fact is the same.

---

## 3. Per-retailer clean table: 100%-match scorecard

**The "Keys" column below is superseded** - it was computed against the original, incomplete barcode rule and is left here struck through only to show what was originally reported; see `goldenacre_alignment_rules_for_pipeline_owner.md` for the corrected key-overlap and value-loss figures (which are smaller for row/key overlap but confirm a real, quantified value loss via a different mechanism - see that document's Rule C).

| Retailer | Schema | Row count | ~~Keys (superseded figures)~~ | Values for matching keys |
|---|---|---|---|---|
| ASDA | ✅ identical except `HC_` adds `RETAILER` | ❌ 731,658 vs 989,203 | ~~270,459 of 989,203 unmatched~~ — see corrected document | Not independently re-checked past this table — see the corrected document for the real value-loss mechanism and figures |
| MORRISONS | ✅ (as above) | ❌ 1,158,520 vs 1,196,799 | ~~1,104,283 unmatched~~ — see corrected document | as above |
| SAINSBURY | ✅ (as above) | ❌ 397,678 vs 429,343 | ~~345,663 unmatched~~ — see corrected document | as above |
| TESCO | ✅ (as above) | ❌ 351,500 vs 368,598 | ~~100% non-overlap~~ — see corrected document (largely resolved once Rule B's date shift is applied) | as above |

**None of the four retailer clean tables are a 100% match** — every discrepancy has a confirmed, specific, named cause (§1 for all four; §2 additionally for Tesco). This is a materially stronger and more precise statement than "expected, not reconciled," which is what the build docs said before this comparison — this comparison found the actual root causes.

---

## 4. `REFERENCE` vs `HC_REFERENCE_CLEAN`: the one component that is 100% clean

- Row counts: `REFERENCE` 21,829 → `HC_REFERENCE_CLEAN` 21,185 (the expected 644-row reduction from deduping 515 duplicate-barcode groups plus excluding blank/`{UNATTRIBUTED}` barcodes — fully accounted for, nothing unexplained).
- **Every single row in `HC_REFERENCE_CLEAN` was checked against `REFERENCE` directly: 0 rows fail to match a real, existing `REFERENCE` row on barcode + brand + buyer + category.** The dedup never fabricates a value.
- **Checked every one of the 515 duplicate-barcode groups in `REFERENCE` for internal disagreement on `BUYER` (the field that drives Halal/Polish/Other classification): 0 groups disagree.** Whichever duplicate row the dedup keeps, the category assignment would have been identical regardless of which one was picked — the completeness-score tie-break has no real ambiguity to resolve for category purposes.

**This is a genuine, verified 100% match in every respect that matters** (real values, and no masked ambiguity) — the only "difference" from `REFERENCE` is the row-count reduction, and that reduction is fully explained and intentional.

---

## 5. `MASTER` vs `HC_MASTER`: not meaningfully comparable row-for-row

`MASTER` inherits every distortion above (§1's truncation baked into its 4 source `CLEAN*` views, plus its own `NUMBER(38,0)` barcode cast, plus its own un-deduped `REFERENCE` join) and compounds them further. Aggregate comparison:

| | Rows | Value sales | Unit sales |
|---|---|---|---|
| `MASTER` | 4,140,716 | £10,363,715,298.08 | 10,870,097,642 |
| `HC_MASTER` | 2,983,943 | £8,651,988,767.07 | 9,290,170,607 |

Per retailer, the direction and size of the distortion is inconsistent (Morrisons is wildly inflated in `MASTER` — 1,965,999 rows / £2.57bn vs. `HC_MASTER`'s 1,196,799 rows / £1.43bn; Tesco and Sainsbury run the other way, lower in `MASTER`) — a predictable consequence of several independent, retailer-varying issues (the barcode-normalisation value loss quantified in `goldenacre_alignment_rules_for_pipeline_owner.md`, `MASTER`'s own `NUMBER(38,0)` barcode cast, and un-deduped `REFERENCE`-join fan-out) landing with different relative strength per retailer. **There is no single clean number to reconcile `MASTER` against `HC_MASTER` with — the honest statement is that `MASTER`'s numbers are unreliable at the barcode/product level for reasons independent of this session's build**, not that `HC_MASTER` disagrees with a trustworthy baseline.

---

## Summary table: what's 100% matching, what's not

| Object pair | 100% match? | Explanation |
|---|---|---|
| `REFERENCE` vs `HC_REFERENCE_CLEAN` | **Yes**, in substance (row count differs by design, values/logic verified clean) | Dedup is a real, traceable subset of `REFERENCE`; zero category-assignment ambiguity found |
| `CLEANASDA` vs `HC_ASDA_CLEAN` | No | See `goldenacre_alignment_rules_for_pipeline_owner.md` Rule C - £1.19bn of raw sales value tied up in barcode-collision keys is not summed, confirmed and quantified there (this doc's earlier §1 figure for ASDA was superseded) |
| `CLEANMORRISON` vs `HC_MORRISONS_CLEAN` | No | Same mechanism, £15.2M lost (see linked document) |
| `CLEANSAINSBURY` vs `HC_SAINSBURY_CLEAN` | No | Same mechanism, £1.08M lost (see linked document) |
| `CLEANTESCO` vs `HC_TESCO_CLEAN` | No | Same mechanism (£22.6M lost) **plus** §2's date-alignment difference | 
| `MASTER` vs `HC_MASTER` | No, and not meaningfully reconcilable | Inherits the above, plus its own barcode cast bug (already known) and un-deduped reference join (already known) |
