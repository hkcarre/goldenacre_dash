# Rules to rebuild the client CSVs from raw — reverse engineered

**Date:** 8 August 2026
**Target:** `master_gol_new.halal / .other / .polish` as delivered to Golden Acre
**Source:** `GOLDENACRE.LANDING.{ASDA, MORRISONS, SAINSBURY, TESCO}` + `HC_REFERENCE_CLEAN`

Every rule below was established by tracing individual rows from the CSV back to raw and
verifying the value survives unchanged, then confirmed by rebuilding the whole dataset and
comparing totals. Companion to `goldenacre_lineage_audit.md`.

## Accuracy achieved

Rebuilding raw with rules 1–8, over the 51-week window both sides share
(2025-08-09 → 2026-07-25):

| Category | Rebuilt | Client CSV | Difference |
|---|---|---|---|
| Halal | £227,018,371 | £225,599,328 | +0.63% |
| Polish | £238,022,963 | £237,506,221 | **+0.22%** |
| Other | £1,267,350,357 | £1,232,373,894 | +2.84% |
| Unclassified left over | £138,050 | — | 0.008% |

On the 4,773 product-keys that appear in both, the values differ by £998,799 in total —
**0.08%**. The recipe is right; the residual is a population difference, not a calculation
difference (see "Unresolved" below).

---

## The rules

### 1. Parse the value — it is a formatted string, not a number
`LANDING."VALUE SALES"` is text: `'£10,351.34'`. `TRY_TO_NUMBER` on it returns NULL
silently, so a naive sum reports zero for whole weeks.
```sql
TRY_TO_NUMBER(REPLACE(REPLACE("VALUE SALES",'£',''),',',''), 38, 4)
```
`"UNIT SALES"` is likewise comma-formatted (`'1,309'`).

### 2. Normalise the barcode
```sql
CASE WHEN LENGTH(BARCODE)=13 AND LEFT(BARCODE,1)='0' THEN LTRIM(BARCODE,'0')
     WHEN LENGTH(BARCODE)>12                         THEN LEFT(BARCODE,12)
     ELSE BARCODE END
```
Confirmed against the CSV, whose barcodes are at most 12 characters and never carry a
leading zero. This is also the join key to the reference — every unmatched row in
`HC_MASTER` has a 13-character barcode, and every barcode of 12 or fewer matches.

### 3. Deduplicate, keeping the £-formatted copy
Each feed carries the same product-week twice, under both barcode forms:
```
0590055205644   £735.02   4MOVEACTIVEVIT 250ML
 590055205644    735.02   4MOVEACTIVEVIT NULL 250ML
```
Keep **one row per (retailer, normalised barcode, week)**, and where the two copies
disagree keep the **`£`-formatted** one. This is not cosmetic: 27,945 ASDA keys carry
different values across the two copies, £23.8m of spread. Traced product 1601 across six
consecutive weeks — the CSV holds 787.73 / 630.47 / 667.90 / 665.35 / 627.48 / 549.52,
the £-copy every time. The plain copy is a stale partial load and stops after
2026-06-20 altogether.
```sql
ROW_NUMBER() OVER (PARTITION BY <normalised_barcode>, <week>
                   ORDER BY CASE WHEN "VALUE SALES" LIKE '£%' THEN 0 ELSE 1 END) = 1
```

### 4. Shift Tesco back one day
`LANDING.TESCO`'s week ends a day later than the other three (2026-07-26 against 2026-07-25).
The CSV puts all four retailers on identical week-ending dates, so Tesco is shifted −1 day.
Omitting this misaligns every Tesco week and drops its most recent one — it was worth
−6.0% on Polish in an earlier attempt.

### 5. Use one shared calendar
All four retailers share identical period boundaries in the output — verified: the min,
max and week-count of every band are the same across retailers. This follows from rule 4.

### 6. Four fixed 52-week bands
`Period-MATx` takes exactly `MAT`, `MAT YA`, `MAT 2YA`, `MAT 3YA`, each exactly 52 weeks,
counted back from the latest week present:

| Band | Window |
|---|---|
| MAT | 2025-08-09 → 2026-08-01 |
| MAT YA | 2024-08-10 → 2025-08-02 |
| MAT 2YA | 2023-08-12 → 2024-08-03 |
| MAT 3YA | 2022-08-13 → 2023-08-05 |

208 weeks in total, so the oldest 4 of the 212 weeks in `LANDING` are dropped.

### 7. Classify from the reference on the normalised barcode
Join a **deduplicated** reference (`GROUP BY BARCODE`) to pick up `BUYER`, `BRAND`,
`UNIFIED PRODUCT NAME`, `GA CATEGORY`, `SUBCAT`, `SUBCAT2`. Deduplicating the reference
first is what production fails to do, and is the cause of its ×1.568 row fan-out.
Classification agreement between our reference and the CSV is **8,694 of 8,721 barcodes
(99.7%)**, £533k in dispute.

### 8. Split one file per `BUYER`
Three files: `halal`, `polish`, `other`. Rows with no classification are **not** shared
with the client, so their unclassified bucket is invisible in what we received.

### 9. Keep zero and negative rows
Zero-value rows are retained — 48,105 of 106,796 Halal MAT rows (45%), plus 42 negative
values. Do not filter them; the client's row counts depend on them.

### 10. Output formatting
- Retailers are title case, `Sainsburys` **without** an apostrophe
- Dates are `DD-MMM-YYYY` (`01-Aug-2026`)
- Values are plain numerics, £ symbol stripped
- 21 columns, but the unit column is named **`UNITS` in halal and `UNIT` in other/polish**
  — read the header, do not assume
- Column *order* also differs between the three files

---

## Unresolved: the Other residual (+2.84%, £35.0m)

525 barcodes are in our rebuild and absent from the client's file entirely — not under a
different barcode, not in another category file. £36.5m, spread across all four retailers
(Morrisons £17.7m, ASDA £11.7m, Sainsbury £5.8m, Tesco £1.3m).

They are not excluded by category (kept rates are 55–60% across every `GA_CATEGORY`) and
only £2.6m is explained by whole brands being absent. The rest is SKU-level. Samples:

| Barcode | Product |
|---|---|
| 506371720703 | ASDA BEEF TOPSIDE 90G |
| 501052544448 | MORRISONS 6 BEEF & PORK SMASH BURGERS 510G |
| 506333404050 | JS SPICY CHICKEN CLUB SW |
| 501007674323 | MYPROTEIN FIRECRACKER CHICKEN WRAP |

Mainstream British meat and food-to-go — including pork — which arguably has no place in a
Halal/Polish/World Foods report. **Most likely our reference snapshot (`072026`) is older
than the client's and still carries SKUs theirs has dropped or reclassified.** That cannot
be confirmed without their reference extract; it is the leading hypothesis, not a result.

To close it, ask the pipeline owner for the reference snapshot used to build
`master_gol_new` and re-run rule 7 against it.

---

## Also worth knowing

- The CSVs run to **2026-08-01**; `LANDING` holds nothing after 2026-07-25/26. Snowflake
  is not the system of record for what the client has.
- `ROWS` is reserved in Snowflake — alias it in any audit query.
- `LANDING` dates parse as `'DD MON YYYY'` (spaces); `OUTPUT.Periods` is `'DD-MON-YYYY'`.
