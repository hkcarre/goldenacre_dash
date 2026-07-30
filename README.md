# Golden Acre `HC_` harmonisation layer + multi-agent QA framework

An additive, `HC_`-prefixed harmonisation layer for Golden Acre Foods' `GOLDENACRE` Snowflake database, built alongside a QA-verified analytics report and a live Q&A assistant ("Sprout"). Additive only - nothing here reads from or writes to the client's existing production sqlmesh pipeline (`CLEANASDA`/`CLEANMORRISON`/`CLEANSAINSBURY`/`CLEANTESCO`/`MASTER`/`REFERENCE`, in the separate `optiadata/goldenacre` repo, which this project does not have write access to and never touches).

## Start here

- **`multi-agents/docs/goldenacre/goldenacre_alignment_rules_for_pipeline_owner.md`** - if you own the production sqlmesh pipeline, read this first. Reverse-engineered, empirically-verified rules describing exactly what the existing `CLEAN*` views do to barcodes and dates, including a confirmed, quantified data-loss bug (barcode-collision values not summed) - written as questions for you to confirm or correct, not assumptions.
- **`multi-agents/docs/goldenacre/goldenacre_old_vs_hc_comparison.md`** - detailed comparison between the existing production objects and this project's `HC_` tables: what matches, what doesn't, and why.
- **`multi-agents/docs/goldenacre/goldenacre_target_architecture.md`** - the `HC_` layer's own design decisions and verification results.
- **`multi-agents/docs/goldenacre/goldenacre_raw_assessment.md`** - raw data profiling that everything else is built on.

## What's here

| Path | What it is |
|---|---|
| `multi-agents/scripts/build_goldenacre_hc.py` | Builds the 7 `HC_` tables in `GOLDENACRE.TRANSFORM` from raw `LANDING` data. Idempotent (`CREATE OR REPLACE`), safe to re-run. |
| `multi-agents/scripts/goldenacre_analytics_engine.py` | Live Snowflake query layer (KPIs, market share, treemap, trend, trailing-12-week directional trend) - no UI code. |
| `multi-agents/scripts/build_goldenacre_insights_data.py` | Snapshots every figure the HTML report shows to a single JSON file - the report's audit trail. |
| `html_report/goldenacre_template.html` + `render_goldenacre_html.py` | Source for the static, left-nav analytics report (self-contained HTML, Golden Acre branded). `render_goldenacre_html.py` fills in the template with a snapshot JSON, base64 fonts, and the logo SVG. |
| `goldenacre_theme.py` | Brand design system (navy `#001A70`/gold `#F2AF00`, Libre Franklin + Open Sans) shared by the HTML report and the Streamlit app. |
| `goldenacre_analytics_engine.py`'s consumer, `goldenacre_insights_app.py` | The live Streamlit app - left-nav pages (Overview / Market Share / Top Brands / Brand Map / Trend / Predictions / Insights / Ask Sprout). |
| `goldenacre_pulp.py` | "Sprout" - the live, Claude-API-backed Q&A assistant. Answers only from data the app computed itself; refuses prompt-injection attempts; discloses known data caveats (reference-match coverage gap, Tesco's calendar offset) unprompted when relevant. |
| `run_goldenacre_app.ps1` | Launches the Streamlit app. |
| `multi-agents/config/*.yaml` | Cross-client safety boundaries (which objects are read-only vs. write-approved) - Golden Acre's entries live alongside other Optia clients' here since this is the shared safety-boundary mechanism, not client-specific config. |

## Running it

Requires a `.env` (not committed - see `.gitignore`) with `SNOWFLAKE_*` connection vars, `ANTHROPIC_API_KEY`, and `DASHBOARD_PASSWORD`. Then:

```powershell
.\run_goldenacre_app.ps1
```

To refresh the `HC_` tables against current `LANDING` data:

```powershell
python multi-agents/scripts/build_goldenacre_hc.py
python multi-agents/scripts/build_goldenacre_insights_data.py
```

## Methodology

Every number in the delivered analytics was independently re-derived from live Snowflake by a separate reviewer before delivery (not the process that computed it originally) - see the QA notes in `goldenacre_target_architecture.md`. The alignment-rules document went through two rounds of self-correction, both left visible in the document's own text rather than silently edited away, after an initial finding turned out to be based on an incomplete rule.
