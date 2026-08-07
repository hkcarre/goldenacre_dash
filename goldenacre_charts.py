"""d3 chart components for the Golden Acre dashboard.

Renders assets/goldenacre_charts.js inside a Streamlit component iframe, with
d3 7.9.0 vendored locally rather than pulled from a CDN - a client dashboard
should not go blank because someone else's CDN is having a bad afternoon, and
the deployed container has no guarantee of outbound access to one.

d3 build note: assets/vendor/d3.v7.9.0.min.js is the official d3 7.9.0
distribution. hkcarre/d3 is a fork of d3/d3 sitting exactly level with upstream
(ahead 0, behind 0 - checked), so building the fork would produce this same
file. If the fork later gains its own commits, rebuild from it instead of
bumping this.

Each chart is its own iframe. Streamlit gives components a fixed height, so
heights are explicit and generous - a scrollbar inside a chart looks broken.
"""
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from goldenacre_theme import COLORS

_ASSETS = Path(__file__).resolve().parent / "assets"


@st.cache_resource(show_spinner=False)
def _payload():
    """d3 and the chart library, read once per session rather than per chart."""
    return (
        (_ASSETS / "vendor" / "d3.v7.9.0.min.js").read_text(encoding="utf-8"),
        (_ASSETS / "goldenacre_charts.js").read_text(encoding="utf-8"),
    )


def _palette():
    c = COLORS
    return {
        "card": c["card"], "grid": c["border"], "text": c["text"],
        "textMuted": c["text_muted"], "textFaint": c["text_faint"],
        "primary": c["primary"], "gold": c["gold"], "teal": c["teal"],
        "positive": c["positive"], "negative": c["negative"], "surface2": c["surface_2"],
    }


def render(spec, height=340):
    """Draw one chart. spec['type'] selects the mark; see the JS for each."""
    d3_js, charts_js = _payload()
    spec = dict(spec)
    spec.setdefault("colors", _palette())
    spec.setdefault("height", height - 10)
    c = COLORS
    html = f"""
<!doctype html><html><head><meta charset="utf-8"><style>
  html,body {{ margin:0; padding:0; background:{c['card']};
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; }}
  #chart {{ position:relative; width:100%; }}
  .ga-tip {{ position:absolute; pointer-events:none; background:{c['text']}; color:#fff;
    padding:7px 9px; border-radius:6px; font-size:11.5px; line-height:1.45;
    box-shadow:0 4px 14px rgba(0,0,0,0.18); transition:opacity .12s; z-index:10; white-space:nowrap; }}
  text {{ -webkit-font-smoothing:antialiased; }}
</style></head><body>
<div id="chart"></div>
<script>{d3_js}</script>
<script>{charts_js}</script>
<script>
  const SPEC = {json.dumps(spec, default=str)};
  function draw() {{ window.renderGoldenAcreChart(SPEC); }}
  draw();
  // Streamlit fixes the iframe height but the width follows the layout, so a
  // sidebar toggle or window resize must redraw or the chart is left cropped.
  let t; window.addEventListener('resize', () => {{ clearTimeout(t); t = setTimeout(draw, 120); }});
</script>
</body></html>"""
    components.html(html, height=height, scrolling=False)


def dumbbell(data, height=300, **kw):
    """data: [{label, now, before, delta}] - level and change in one row."""
    render({"type": "dumbbell", "data": data, **kw}, height=height)


def lollipop(data, height=380, **kw):
    """data: [{label, value, delta?, highlight?, note?}] - a ranking."""
    render({"type": "lollipop", "data": data, **kw}, height=height)


def treemap(data, height=430, **kw):
    """data: [{label, value, growth?, group?}] - size by value, colour by growth."""
    render({"type": "treemap", "data": data, **kw}, height=height)


def multiline(series, height=360, **kw):
    """series: [{name, color, emphasis?, points:[{x: 'YYYY-MM-DD', y}]}]"""
    render({"type": "multiline", "series": series, **kw}, height=height)
