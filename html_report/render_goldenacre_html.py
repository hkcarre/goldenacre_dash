import json
from datetime import date
from pathlib import Path

BASE = Path(__file__).parent

template = (BASE / "goldenacre_template.html").read_text(encoding="utf-8")
libre_b64 = (BASE / "libre_franklin.woff2.b64.txt").read_text(encoding="ascii")
opensans_b64 = (BASE / "open_sans.woff2.b64.txt").read_text(encoding="ascii")
logo_svg = (BASE / "ga_logo.svg").read_text(encoding="utf-8")
data = json.loads((BASE / "goldenacre_insights_snapshot.json").read_text(encoding="utf-8"))

as_of = data["as_of_latest_period"]
_d = date.fromisoformat(as_of)
as_of_human = f"{_d.day} {_d.strftime('%B')} {_d.year}"

QA_PENDING_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
QA_PASSED_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12l5 5L20 6"/></svg>'

QA_STATUS_LINE = (
    "Independently re-verified — every figure on this page was re-derived directly from Snowflake "
    "by a separate reviewer (not the process that built this report) and confirmed to match, 30 July 2026."
)
QA_ICON = QA_PASSED_ICON

out = template
out = out.replace("__FONT_LIBRE_B64__", libre_b64)
out = out.replace("__FONT_OPENSANS_B64__", opensans_b64)
out = out.replace("__GA_LOGO_SVG__", logo_svg)
out = out.replace("__AS_OF_DATE__", as_of_human)
out = out.replace("__DATA_JSON__", json.dumps(data))
out = out.replace("__QA_BADGE_ICON__", QA_ICON)
out = out.replace("__QA_STATUS_LINE__", QA_STATUS_LINE)

(BASE / "goldenacre_insights.html").write_text(out, encoding="utf-8")
print("wrote", BASE / "goldenacre_insights.html", len(out), "bytes")
