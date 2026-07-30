"""Visual design system for the Golden Acre Foods analytics app - colors, type, and
component patterns only, mirroring the split in vithit_theme.py (styling here,
data logic in multi-agents/scripts/goldenacre_analytics_engine.py).

Design tokens are read from goldenacrefoods.com's own served assets, not invented:
  - Navy #001A70 and gold #F4CF00/#F2AF00 come directly from the logo SVG
    (assets/goldenacre_logo.svg) and its swoosh graphic - sampled from the real
    fill/stroke hex values in the SVG source, not guessed from a page screenshot.
  - The wider brand palette (navy #001A70/#364574/#363E6C, gold #FEE002/#F2AF00,
    teal #19AACC) comes from the site's own Elementor CSS
    (post-4266.css, fetched directly, not from an AI summary of the page - a
    first-pass page-content summary guessed "orange" as the primary colour,
    which the raw CSS showed was wrong).
  - Fonts: Libre Franklin (headings) + Open Sans (body), both served locally by
    the site's own Elementor build, self-hosted here as base64 (Streamlit serves
    over plain HTTP locally and a live app shouldn't depend on Google Fonts'
    CDN being reachable at demo time).
  - The categorical 4-colour set (navy/gold/teal/magenta) was run through the
    dataviz skill's palette validator (light L 0.43-0.77 / dark L 0.48-0.67,
    CVD floor, contrast) before being adopted - see
    multi-agents/docs/goldenacre/ for the validated hex values; magenta
    (#B23A56 light / #C96580 dark) was added as a 4th categorical slot since the
    brand itself only supplies three distinct hues and four retailers need
    four distinguishable colours.
"""

import base64
from pathlib import Path

_ASSETS = Path(__file__).parent / "assets"
_LOGO_SVG = (_ASSETS / "goldenacre_logo.svg").read_text(encoding="utf-8") if (_ASSETS / "goldenacre_logo.svg").exists() else ""


def _font_b64(name):
    path = _ASSETS / "goldenacre_fonts" / name
    return base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else ""


_LIBRE_FRANKLIN_B64 = _font_b64("libre_franklin.woff2")
_OPEN_SANS_B64 = _font_b64("open_sans.woff2")

COLORS = {
    "bg": "#FAF9F6",
    "card": "#FFFFFF",
    "surface_2": "#F2F0EA",
    "border": "rgba(20,20,26,0.10)",
    "border_soft": "rgba(20,20,26,0.06)",
    "text": "#14141A",
    "text_muted": "#52514E",
    "text_faint": "#898781",
    "primary": "#2A4FA0",       # navy, from the logo wordmark (#001A70) stepped for chart-lightness compliance
    "primary_dark": "#001A70",  # exact logo hex, used for solid brand elements (header, logo itself)
    "primary_bg": "#E8EDF9",
    "gold": "#D99A00",          # site CTA/swoosh gold (#FEE002/#F2AF00), stepped for text/UI contrast
    "gold_bg": "#FBF0D9",
    "teal": "#19AACC",
    "teal_bg": "#E1F4F9",
    "magenta": "#B23A56",
    "magenta_bg": "#F8E6EA",
    "positive": "#1F7A45",
    "positive_bg": "#E7F5E4",
    "positive_border": "#C3E6BE",
    "negative": "#B23A3A",
    "negative_bg": "#FDEAEA",
    "negative_border": "#F8C4C4",
}

# Categorical assignment, fixed order - never re-cycled across charts. Validated
# via the dataviz skill's validate_palette.js (both light and dark modes).
RETAILER_COLOR = {"ASDA": COLORS["primary"], "MORRISONS": COLORS["gold"], "SAINSBURY": COLORS["teal"], "TESCO": COLORS["magenta"]}
RETAILER_LABEL = {"ASDA": "ASDA", "MORRISONS": "Morrisons", "SAINSBURY": "Sainsbury's", "TESCO": "Tesco"}
CATEGORY_COLOR = {"HALAL": COLORS["primary"], "POLISH": COLORS["gold"], "OTHER": COLORS["teal"], "UNCLASSIFIED": COLORS["text_faint"]}
CATEGORY_LABEL = {"HALAL": "Halal", "POLISH": "Polish", "OTHER": "Other", "UNCLASSIFIED": "Unclassified"}

FONT_STACK = "'Libre Franklin', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
BODY_FONT_STACK = "'Open Sans', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"

_FONT_FACES_CSS = f"""
@font-face {{
    font-family: 'Libre Franklin';
    src: url(data:font/woff2;base64,{_LIBRE_FRANKLIN_B64}) format('woff2');
    font-weight: 100 900;
    font-style: normal;
    font-display: swap;
}}
@font-face {{
    font-family: 'Open Sans';
    src: url(data:font/woff2;base64,{_OPEN_SANS_B64}) format('woff2');
    font-weight: 100 900;
    font-style: normal;
    font-display: swap;
}}
""" if _LIBRE_FRANKLIN_B64 and _OPEN_SANS_B64 else ""


def inject_global_css():
    """One CSS block, injected once near the top of the app - restyles Streamlit's
    own widgets (buttons, dataframes, metrics, chat input) to the Golden Acre
    navy/gold identity rather than Streamlit's default red accent."""
    c = COLORS
    return f"""
    <style>
    {_FONT_FACES_CSS}
    html, body, [class*="css"] {{ font-family: {BODY_FONT_STACK}; }}
    .stApp {{ background: {c['bg']}; }}
    h1, h2, h3, h4 {{ font-family: {FONT_STACK}; font-weight: 800; letter-spacing: -0.01em; color: {c['text']}; }}
    [data-testid="stMetricValue"] {{ font-family: {FONT_STACK}; font-weight: 800; color: {c['text']}; }}
    [data-testid="stMetricDelta"] svg {{ display: none; }}
    .stButton > button, .stDownloadButton > button {{
        background: {c['primary_dark']}; color: #fff; border: none; border-radius: 999px;
        font-weight: 600; font-family: {BODY_FONT_STACK};
    }}
    .stButton > button:hover {{ background: {c['primary']}; color: #fff; }}
    [data-testid="stChatInput"] textarea {{ font-family: {BODY_FONT_STACK}; }}
    .ga-card {{
        background: {c['card']}; border: 1px solid {c['border']}; border-radius: 14px;
        padding: 18px 20px; margin-bottom: 12px;
    }}
    .ga-eyebrow {{
        font-size: 11.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
        color: {c['primary']}; margin-bottom: 4px; font-family: {BODY_FONT_STACK};
    }}

    /* ---- left-nav sidebar: navy shell, gold active item, matching the HTML report's shell ---- */
    [data-testid="stSidebar"] {{
        background: {c['primary_dark']};
        min-width: 230px !important;
    }}
    [data-testid="stSidebar"] * {{ color: rgba(255,255,255,0.82); }}
    [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: #fff; }}
    [data-testid="stSidebar"] [data-testid="stImage"] img {{ filter: brightness(0) invert(1); }}
    [data-testid="stSidebar"] .stRadio > div {{ gap: 2px; }}
    [data-testid="stSidebar"] .stRadio label {{
        border-radius: 9px; padding: 8px 10px; width: 100%; font-weight: 600; font-size: 13.5px;
    }}
    [data-testid="stSidebar"] .stRadio label:hover {{ background: rgba(255,255,255,0.08); }}
    [data-testid="stSidebar"] .stRadio input:checked + div {{ color: #1a1400 !important; }}
    [data-testid="stSidebar"] .stRadio label[data-checked="true"],
    [data-testid="stSidebar"] .stRadio [aria-checked="true"] {{ background: {c['gold']}; }}
    [data-testid="stSidebarNav"] {{ display: none; }}
    </style>
    """


def render_sidebar_brand():
    """Logo + wordmark for the top of the sidebar nav, mirroring the HTML report's
    sidebar-brand block so the two surfaces read as the same product."""
    return f"""
    <div style="padding:6px 4px 18px;display:flex;align-items:center;gap:8px;">
        {_LOGO_SVG}
    </div>
    """


def render_header(scope_note=None):
    c = COLORS
    scope_html = f'<div style="font-size:0.78rem;color:{c["text_muted"]};margin-top:4px;">{scope_note}</div>' if scope_note else ""
    return f"""
    <div style="display:flex;align-items:center;justify-content:space-between;gap:24px;
                padding:20px 0;border-bottom:1px solid {c['border']};margin-bottom:24px;">
        <div style="height:42px;">{_LOGO_SVG}</div>
        <div style="text-align:right;">
            <div style="font-family:{FONT_STACK};font-weight:800;font-size:1.1rem;color:{c['text']};">
                Retail Performance Analytics
            </div>
            {scope_html}
        </div>
    </div>
    """


def render_hero(headline, subtext):
    c = COLORS
    return f"""
    <div style="background:linear-gradient(180deg,{c['primary_bg']},{c['bg']} 70%);
                border-radius:16px;padding:28px 28px 24px;margin-bottom:24px;">
        <div style="font-family:{FONT_STACK};font-weight:800;font-size:clamp(24px,3vw,34px);
                    letter-spacing:-0.01em;color:{c['text']};">{headline}</div>
        <div style="color:{c['text_muted']};font-size:15px;margin-top:8px;max-width:640px;">{subtext}</div>
    </div>
    """


def render_metric_tile(label, value, delta_text=None, is_positive=None, sub=None):
    c = COLORS
    delta_html = ""
    if delta_text is not None:
        color = c["text_faint"] if is_positive is None else (c["positive"] if is_positive else c["negative"])
        arrow = "" if is_positive is None else ("↑ " if is_positive else "↓ ")
        delta_html = f'<div style="font-size:12.5px;font-weight:600;color:{color};margin-top:4px;">{arrow}{delta_text}</div>'
    sub_html = f'<div style="font-size:11.5px;color:{c["text_faint"]};margin-top:4px;">{sub}</div>' if sub else ""
    return f"""
    <div class="ga-card" style="padding:16px 18px;">
        <div style="font-size:12px;font-weight:600;color:{c['text_muted']};">{label}</div>
        <div style="font-family:{FONT_STACK};font-weight:800;font-size:24px;letter-spacing:-0.01em;
                    color:{c['text']};margin-top:4px;">{value}</div>
        {delta_html}
        {sub_html}
    </div>
    """


def render_badge(text, kind="neutral"):
    c = COLORS
    palette = {
        "neutral": (c["surface_2"], c["text_muted"], c["border"]),
        "positive": (c["positive_bg"], c["positive"], c["positive_border"]),
        "negative": (c["negative_bg"], c["negative"], c["negative_border"]),
    }
    bg, fg, border = palette.get(kind, palette["neutral"])
    return (f'<span style="background:{bg};color:{fg};border:1px solid {border};'
            f'border-radius:999px;padding:2px 10px;font-size:11.5px;font-weight:700;">{text}</span>')


def render_insight_card(number, html_text):
    c = COLORS
    return f"""
    <div class="ga-card" style="display:flex;gap:14px;align-items:flex-start;">
        <div style="font-family:{FONT_STACK};font-weight:800;font-size:20px;color:{c['primary']};width:26px;flex:none;">{number}</div>
        <div style="font-size:14px;color:{c['text_muted']};">{html_text}</div>
    </div>
    """
