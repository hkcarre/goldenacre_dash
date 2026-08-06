"""Bring the published static report into line with the Streamlit app.

Deliberately edits the PUBLISHED artifact's own HTML rather than re-rendering
from html_report/goldenacre_template.html. The committed template is OLDER than
what was published (it still says 45.2%/£1.14bn where the live report correctly
says 45.8%/£1.16bn) - the corrected template only ever existed in a previous
session's scratchpad and was never synced to the repo. Re-rendering from it
would have regressed the client-facing report.

Changes, all to match decisions already applied to the app:
  1. Category views restricted to Halal/Polish/Other, shares of the classified
     total, with the excluded unmatched share disclosed rather than charted as
     a fourth segment.
  2. The Hungry Boar and X Energy added to the manufacturer page.
"""
import json
import re
import sys
from pathlib import Path

SCRATCH = Path(__file__).resolve().parent
sys.path.insert(0, r"C:\Users\helen\Projects\snowflake\multi-agents\scripts")
sys.path.insert(0, r"C:\Users\helen\Projects\snowflake")
import goldenacre_analytics_engine as engine  # noqa: E402

src = (SCRATCH / "ga_report_src.html").read_text(encoding="utf-8")
before = src

# ---------------------------------------------------------------- live extras
conn = engine.connection()
mv = engine.load_manufacturer_view(conn)
conn.close()
extras = mv["portfolio_extras"]
assert extras["owned_extra"] and extras["distributed"], "expected both brand groups"

# ---------------------------------------------------------------- DATA blob
m = re.search(r"const DATA\s*=\s*(\{.*?\});", src, re.S)
data = json.loads(m.group(1))

# 1. category_share -> classified only, shares recomputed over the classified total
cats = [c for c in data["category_share"] if c["category"] != "UNCLASSIFIED"]
assert len(cats) == 3, cats
classified_total = sum(c["value_sales_mat"] for c in cats)
for c in cats:
    c["share_pct"] = round(c["value_sales_mat"] / classified_total * 100, 2)
assert abs(sum(c["share_pct"] for c in cats) - 100.0) < 0.02, "shares must sum to 100"
data["category_share"] = cats

# 2. treemap: drop the unclassified tiles from every retailer
dropped = 0
for ret, rows in data["treemap_by_retailer"].items():
    kept = [r for r in rows if r.get("category") != "UNCLASSIFIED"]
    dropped += len(rows) - len(kept)
    data["treemap_by_retailer"][ret] = kept
assert dropped == 30, f"expected 30 unclassified treemap tiles, dropped {dropped}"

# 3. predictions: drop the unclassified momentum series
preds = [p for p in data["predictions"] if "UNCLASSIF" not in str(p.get("series", "")).upper()]
assert len(preds) == len(data["predictions"]) - 1, "expected exactly one unclassified series"
data["predictions"] = preds

# 4. carry the two brands the app now shows
data["portfolio_extras"] = extras

src = src[:m.start(1)] + json.dumps(data) + src[m.end(1):]

# ---------------------------------------------------------------- JS config
src = src.replace("  UNCLASSIFIED: 'var(--unclassified)',\n", "")
src = src.replace("  UNCLASSIFIED: 'var(--unclassified-wash)',\n", "")
src = src.replace(
    "const CAT_LABEL = {HALAL:'Halal', POLISH:'Polish', OTHER:'Other', UNCLASSIFIED:'Unclassified'};",
    "const CAT_LABEL = {HALAL:'Halal', POLISH:'Polish', OTHER:'Other'};",
)
src = src.replace("const order = ['OTHER','HALAL','POLISH','UNCLASSIFIED']",
                  "const order = ['OTHER','HALAL','POLISH']")

# ---------------------------------------------------------------- prose
# No figures restated here: the unmatched share is already on the KPI tile, and
# duplicating a number into hand-written prose is exactly how this report drifted
# out of line with its own data before.
src = src.replace(
    'Categories come from Golden Acre\'s product reference data (Halal / Polish / Other). "Unclassified" is not a business category — it\'s the share of value sales with no reference-data match at all.',
    "Halal, Polish and Other only, from Golden Acre's product reference data. Shares are of the classified total, so they sum to 100%. Value with no product-reference match is excluded rather than shown as a fourth category - see the reference-match KPI on the Overview.",
)
src = src.replace(
    'This "Unclassified" bucket is also the <em>only</em> segment growing (+8.6%), while the reference-matched "Other" category shrank 15.1%',
    "That unmatched value is also the <em>only</em> part of the market growing (+8.6%), while the reference-matched \"Other\" category shrank 15.1%",
)
src = src.replace(
    '<li>"Unclassified" reflects products with no match in Golden Acre\'s product reference table as of its most recent snapshot — a data-coverage gap, not a business category. See the reference-match KPI above.</li>',
    "<li>Category charts cover Halal, Polish and Other only. Products with no match in Golden Acre's product reference table are a data-coverage gap rather than a business category, so they are excluded from category splits and reported separately via the reference-match KPI.</li>",
)

# ---------------------------------------------------------------- new section
PORTFOLIO_SECTION = """
        <section id="mfg-portfolio">
          <div class="section-head">
            <h2>The rest of the portfolio</h2>
            <div class="section-note">Golden Acre lines outside the Halal category, so they do not appear in the competitive set above.</div>
          </div>
          <div class="card"><div class="kpi-grid" id="mfg-portfolio-cards"></div></div>
          <div class="insight"><div class="n">&#8594;</div><p id="mfg-portfolio-text"></p></div>
        </section>
"""
anchor = '<div class="card" id="mfg-price-card"></div>\n        </section>'
assert anchor in src, "price-card anchor not found"
src = src.replace(anchor, anchor + PORTFOLIO_SECTION, 1)

PORTFOLIO_JS = """
/* ---------------- the rest of the portfolio ---------------- */
(function renderPortfolioExtras(){
  const ex = DATA.portfolio_extras;
  if (!ex) return;
  const grid = document.getElementById('mfg-portfolio-cards');
  const rows = (ex.owned_extra || []).map(r => ({...r, kind: 'Own brand'}))
    .concat((ex.distributed || []).map(r => ({...r, kind: 'Distributed, not owned'})));
  if (!grid || !rows.length) return;
  rows.forEach(r => {
    const el = document.createElement('div');
    el.className = 'kpi';
    const up = r.value_yoy_pct > 0;
    el.innerHTML = `
      <div class="kpi-label">${r.brand.toLowerCase().replace(/\\b\\w/g, c => c.toUpperCase())}</div>
      <div class="kpi-value">${fmtGBPCompact(r.value_sales_mat)}</div>
      <div class="kpi-delta ${up ? 'up' : 'down'}">${up ? '\\u2191' : '\\u2193'} ${Math.abs(r.value_yoy_pct).toFixed(1)}%</div>
      <div class="kpi-sub">${r.kind} \\u00b7 ${(r.retailers || []).map(x => RETAILER_LABEL[x] || x).join(', ')}</div>`;
    grid.appendChild(el);
  });
  const total = (ex.owned_extra_total_mat || 0) + (ex.distributed_total_mat || 0);
  const p = document.getElementById('mfg-portfolio-text');
  if (p) p.innerHTML = `<strong>These are the fastest-growing lines in the portfolio.</strong> Together they are `
    + `${fmtGBPCompact(total)} MAT, and because both sit outside Halal, Polish and Other, neither shows up in any `
    + `category view. X Energy is deliberately excluded from Golden Acre's combined share above: Golden Acre `
    + `distributes it rather than owning it, so counting it would overstate own-brand share.`;
})();
"""
tail = "</script>"
idx = src.rfind(tail)
assert idx > 0, "no closing script tag"
src = src[:idx] + PORTFOLIO_JS + src[idx:]

# ---------------------------------------------------------------- verify
out = SCRATCH / "ga_report_fixed.html"
out.write_text(src, encoding="utf-8")

d2 = json.loads(re.search(r"const DATA\s*=\s*(\{.*?\});", src, re.S).group(1))
print("categories now      :", [c["category"] for c in d2["category_share"]])
print("shares              :", [c["share_pct"] for c in d2["category_share"]], "sum:", round(sum(c['share_pct'] for c in d2['category_share']), 2))
print("treemap UNCLASSIFIED:", sum(1 for rows in d2["treemap_by_retailer"].values() for r in rows if r.get("category") == "UNCLASSIFIED"))
print("prediction series   :", len(d2["predictions"]))
print("portfolio_extras    :", [r["brand"] for r in d2["portfolio_extras"]["owned_extra"] + d2["portfolio_extras"]["distributed"]])
print("UNCLASSIFIED in JS config:", "UNCLASSIFIED:" in src)
print("'Unclassified' remaining in prose:", len(re.findall(r"Unclassified", src)))
print(f"\nsize {len(before):,} -> {len(src):,} bytes -> {out}")
