# Static report — read this before re-rendering

`goldenacre_insights.html` in this folder is the **authoritative** copy: it is
byte-for-byte what is published to the client-facing artifact at

    https://claude.ai/code/artifact/d3d8a799-784e-43c4-95e0-9c1e20c8bced

## `goldenacre_template.html` is STALE — do not render from it

It is older than what was published. It still carries `45.2%` / `£1.14bn` where
the live report correctly says `45.8%` / `£1.16bn`, and it defines
`UNCLASSIFIED` as a fourth chart category, which the report no longer shows.
The corrected template only ever existed in a previous session's temp
scratchpad and was never synced here.

Running `render_goldenacre_html.py` against it would **regress** the published
report. That script is also currently unrunnable as committed: it expects
`libre_franklin.woff2.b64.txt`, `open_sans.woff2.b64.txt`, `ga_logo.svg` and
`goldenacre_insights_snapshot.json`, none of which are in this repo (the fonts
and logo exist as binaries under `assets/`, and the snapshot is produced by
`multi-agents/scripts/build_goldenacre_insights_data.py`).

## To change the report

Edit `goldenacre_insights.html` directly, or script the edit against it — it is
self-contained, with fonts, logo and its data blob all inlined. Then republish
to the **same URL above** so anyone holding the existing link gets the update.
Verify by executing it (jsdom or equivalent) rather than reading it: a previous
version of this report shipped with a JavaScript error that silently blanked
the treemap, trend and prediction charts, and a numbers-only review missed it.

## Keep it in step with the Streamlit app

The app is the live surface and this is a point-in-time snapshot, so they will
drift unless changed together. Two things they must agree on:

- **Categories are Halal, Polish and Other only.** Shares are of the classified
  total. Value with no product-reference match is disclosed via the
  reference-match KPI, never charted as a fourth category.
- **Golden Acre's own brands are Najma, Jaldee Eats and The Hungry Boar.**
  X Energy is distributed, not owned, and is excluded from own-brand share.

If the two surfaces are ever expensive to keep aligned, retiring this one and
letting the app be the single deliverable is the cheaper answer.
