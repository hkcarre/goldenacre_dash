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
_OPTIA_LOGO_PATH = _ASSETS / "optia_logo_white.svg"
_OPTIA_LOGO_SVG = _OPTIA_LOGO_PATH.read_text(encoding="utf-8") if _OPTIA_LOGO_PATH.exists() else ""


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

    /* ---- "Powered by Optia" credit, bottom of sidebar ---- */
    .op-credit {{
        display: flex; align-items: center; gap: 8px; margin-top: 14px; padding-top: 14px;
        border-top: 1px solid rgba(255,255,255,0.14); text-decoration: none !important;
    }}
    .op-credit .op-label {{
        font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase;
        color: rgba(255,255,255,0.5); white-space: nowrap;
    }}
    .op-credit .op-logo-wrap {{ display: block; opacity: 0.85; transition: opacity 0.15s ease; }}
    .op-credit:hover .op-logo-wrap {{ opacity: 1; }}
    .op-credit .op-logo-wrap svg {{ height: 12px; width: auto; display: block; }}

    /* --- Listen control (Insights page voice) ----------------------------
       Scoped via st.container(key="ga-listen-...") which Streamlit renders as
       a "st-key-<key>" CSS class - the documented way to target one widget
       rather than every button in the app.

       Deliberately quiet styling: this is a secondary affordance sitting under
       an insight card, so it must not inherit the full-size navy pill used for
       primary actions. !important is needed because Streamlit's own emotion
       styles are generated at a higher specificity than a plain class rule. */
    [class*="st-key-ga-listen-"] {{ margin: -8px 0 16px; }}
    [class*="st-key-ga-listen-"] button {{
        background: transparent !important;
        border: 1px solid {c['border']} !important;
        color: {c['text_muted']} !important;
        border-radius: 999px !important;
        padding: 0 12px !important;
        min-height: 0 !important;
        height: 28px !important;
        font-size: 11.5px !important;
        font-weight: 600 !important;
        box-shadow: none !important;
    }}
    [class*="st-key-ga-listen-"] button:hover {{
        border-color: {c['primary']} !important;
        color: {c['primary']} !important;
        background: {c['primary_bg']} !important;
    }}
    /* A native <audio> element can only be restyled this far. Size it down and
       repaint Chrome's control panel so it stops reading as a foreign widget
       dropped between two cards; other browsers keep their own player. */
    [class*="st-key-ga-listen-"] [data-testid="stAudio"] {{ margin-top: 6px; }}
    [class*="st-key-ga-listen-"] audio {{
        height: 34px; width: 100%; max-width: 360px; display: block;
    }}
    [class*="st-key-ga-listen-"] audio::-webkit-media-controls-panel {{
        background: {c['surface_2']};
    }}
    [class*="st-key-ga-listen-"] audio::-webkit-media-controls-current-time-display,
    [class*="st-key-ga-listen-"] audio::-webkit-media-controls-time-remaining-display {{
        font-size: 11px; color: {c['text_muted']};
    }}
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


def render_powered_by_credit():
    """"Powered by Optia" credit for the bottom of the sidebar, below the retailer-scope
    line - not a fixed floating badge like vithit's (this sidebar already pins an "as of"
    footer to the same corner via margin-top:auto, so a fixed overlay would sit on top of
    it); sits in normal flow instead. Uses Optia's new white lockup, which is why this
    reads as a plain mark rather than vithit's coloured animated-circle treatment - that
    circle's indigo brand colour doesn't exist in this asset."""
    if not _OPTIA_LOGO_SVG:
        return ""
    return f"""
    <a class="op-credit" href="https://optiadata.com" target="_blank" rel="noopener noreferrer">
        <span class="op-label">Powered by</span>
        <span class="op-logo-wrap">{_OPTIA_LOGO_SVG}</span>
    </a>
    """


def render_header(scope_note=None):
    c = COLORS
    # Built as one continuous line, deliberately - a multi-line f-string here
    # produces a whitespace-only line whenever scope_note is falsy, which
    # Markdown treats as the end of the raw-HTML block; whatever follows then
    # renders as a literal indented code block instead of HTML. Same fix as
    # render_metric_tile below - see its comment for the full mechanism and
    # the real bug this caused there.
    scope_html = f'<div style="font-size:0.78rem;color:{c["text_muted"]};margin-top:4px;">{scope_note}</div>' if scope_note else ""
    return (
        f'<div style="display:flex;align-items:center;justify-content:space-between;gap:24px;'
        f'padding:20px 0;border-bottom:1px solid {c["border"]};margin-bottom:24px;">'
        f'<div style="height:42px;">{_LOGO_SVG}</div>'
        f'<div style="text-align:right;">'
        f'<div style="font-family:{FONT_STACK};font-weight:800;font-size:1.1rem;color:{c["text"]};">'
        f'Retail Performance Analytics</div>{scope_html}</div></div>'
    )


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
    """Built as one continuous line, deliberately, not a multi-line f-string.
    Real bug found and fixed 2026-08-06: the previous multi-line version left
    a whitespace-only line wherever {delta_html} or {sub_html} was empty (e.g.
    any tile with no delta_text - Avg price per unit, Distinct products,
    Distinct brands, Reference match all hit this). Markdown treats a blank
    line as the end of a raw-HTML block; the indented line immediately after
    it then gets parsed as a NEW block and, being indented >=4 spaces, renders
    as a literal code block instead of HTML - which is exactly what showed up
    in production as visible `<div style="...` text instead of the styled sub
    line. Tiles that pass delta_text never had an empty line, so they never
    showed the bug - which is why it looked tile-specific rather than a
    systemic template issue. Single-line output has no blank line to trigger
    this regardless of which optional args are supplied, for any future caller."""
    c = COLORS
    delta_html = ""
    if delta_text is not None:
        color = c["text_faint"] if is_positive is None else (c["positive"] if is_positive else c["negative"])
        arrow = "" if is_positive is None else ("↑ " if is_positive else "↓ ")
        delta_html = f'<div style="font-size:12.5px;font-weight:600;color:{color};margin-top:4px;">{arrow}{delta_text}</div>'
    sub_html = f'<div style="font-size:11.5px;color:{c["text_faint"]};margin-top:4px;">{sub}</div>' if sub else ""
    return (
        f'<div class="ga-card" style="padding:16px 18px;">'
        f'<div style="font-size:12px;font-weight:600;color:{c["text_muted"]};">{label}</div>'
        f'<div style="font-family:{FONT_STACK};font-weight:800;font-size:24px;letter-spacing:-0.01em;'
        f'color:{c["text"]};margin-top:4px;">{value}</div>{delta_html}{sub_html}</div>'
    )


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
