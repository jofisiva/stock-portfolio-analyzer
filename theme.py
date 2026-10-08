"""Broadsheet theme for the Stock Portfolio Analyzer (Layout A).

One CSS block injected by apply_theme(), a Plotly template set as default, and the
gain/loss colours used by the charts and table. Selectors target Streamlit 1.37
test ids; re-check them when upgrading Streamlit.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

INK, PAPER, SURFACE, SIDEBAR = "#201e1d", "#f3f2f2", "#eae9e9", "#f8f4f4"
ACCENT, ACCENT_100, ACCENT_600, ACCENT_700, ACCENT_800 = "#0088b0", "#e9f8ff", "#1186ac", "#006786", "#004961"
MAGENTA, MAGENTA_100, MAGENTA_200, MAGENTA_700, MAGENTA_800 = "#d6006c", "#fff1f4", "#ffdee6", "#aa0b56", "#790e3d"
GAIN, LOSS, FLAT = ACCENT, MAGENTA, "#bab6b6"        # bar fills (neutral-400 for unchanged)
GAIN_TEXT, LOSS_TEXT = ACCENT_700, MAGENTA_700       # text-size use, 4.5:1 on paper
# Sector bars are one measure, so one hue: blue (categorical slot 1). Sectors picked
# in the filter (by clicking a bar) turn a darker blue from the same ramp.
SECTOR_BAR, SECTOR_BAR_SELECTED = "#2a78d6", "#184f95"
DONUT_SHADES = ["#2d2b2b", "#444141", "#605d5d", "#7d7979", "#9b9797", "#bab6b6", "#d7d3d3"]
# Categorical slots for the stock donut, in this fixed order (the order is what keeps
# neighbours colour-blind safe). Checked on PAPER with the dataviz palette validator:
# CVD ΔE 9.1, normal-vision ΔE 19.6. Four slots are under 3:1 contrast, so the donut
# always has a legend and the holdings table. Holdings past 8 fold into OTHER.
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7",
               "#e34948"]
OTHER = "#bab6b6"
FONT = '"Source Serif 4", Georgia, serif'
MUTED = f"color-mix(in srgb, {INK} 70%, transparent)"
DIVIDER = f"color-mix(in srgb, {INK} 16%, transparent)"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap');
html, body, [class*="st-"], .stMarkdown, button, input, textarea, select, [data-testid="stSidebar"] * {{
  font-family: {FONT} !important; font-feature-settings: "tnum" 1;
}}
/* Paint the page ourselves so it stays light even when the viewer's Streamlit theme is dark. */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"], .main {{ background: {PAPER} !important; color: {INK}; }}
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp p, .stApp li, .stApp label,
[data-testid="stMetricValue"], [data-testid="stMarkdownContainer"] {{ color: {INK}; }}
[data-baseweb="input"] input, [data-baseweb="select"] *, [data-testid="stDateInput"] input {{ color: {INK} !important; }}
[data-testid="stFileUploaderDropzone"] *, [data-testid="stFileUploadDropzone"] * {{ color: {INK}; }}
[data-testid="stFileUploaderDropzone"] button {{ background: transparent; border: 1px solid {DIVIDER}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding: 40px 56px 96px !important; max-width: none; }}
h1 {{ font-size: 42px !important; font-weight: 600 !important; letter-spacing: -0.015em; padding: 0 0 6px !important; }}
/* each section opens on a thin rule, so the page reads as distinct bands */
.block-container h3 {{ font-size: 28px !important; font-weight: 600 !important; letter-spacing: -0.01em;
  margin-top: 40px; padding: 20px 0 2px !important; border-top: 1px solid {DIVIDER}; }}
.block-container [data-testid="stCaptionContainer"] {{ font-size: 13px; color: {MUTED}; max-width: 120ch; }}
.block-container [data-testid="stCaptionContainer"] p {{ font-size: 13px; }}
a {{ color: {ACCENT_700}; }} a:hover {{ color: {ACCENT_600}; }}
::selection {{ background: color-mix(in srgb, {ACCENT} 30%, transparent); }}

/* sidebar */
[data-testid="stSidebar"] {{ background: {SIDEBAR}; }}
[data-testid="stSidebar"] > div:first-child {{ background: {SIDEBAR}; }}
[data-testid="stSidebarUserContent"] {{ padding: 32px 30px 40px; }}
[data-testid="stSidebar"] h2 {{
  font-size: 13px !important; font-weight: 400 !important; letter-spacing: 0; color: {MUTED}; padding: 18px 0 4px !important;
}}
[data-testid="stWidgetLabel"] p {{ font-size: 12px !important; color: color-mix(in srgb, {INK} 70%, transparent); }}

/* metrics: kicker / figure / sub */
[data-testid="stMetricLabel"] p {{
  font-size: 13px !important; letter-spacing: 0; color: {MUTED};
}}
[data-testid="stMetricValue"] {{ font-size: 26px !important; font-weight: 600; line-height: 1.15; }}
/* the headline: current value, the one figure the page is about */
.bs-hero {{ display: none; }}
[data-testid="column"]:has(.bs-hero) [data-testid="stMetricValue"] {{
  font-size: 56px !important; letter-spacing: -0.02em; line-height: 1.05; }}

[data-testid="stMetricValue"] > div {{ white-space: normal !important; overflow-wrap: anywhere; }}
[data-testid="stMetricDelta"] {{ font-size: 14px; color: {INK} !important; background: transparent !important; }}
[data-testid="stMetricDelta"] > div {{ white-space: normal !important; overflow: visible !important; }}
[data-testid="stMetricDelta"] svg {{ display: none; }}
[data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Up"]) {{ color: {GAIN_TEXT} !important; }}
[data-testid="stMetricDelta"]:has([data-testid="stMetricDeltaIcon-Down"]) {{ color: {LOSS_TEXT} !important; }}

/* buttons */
.stButton button, .stDownloadButton button {{
  border-radius: 2px; font-weight: 600; font-size: 14px; color: {INK};
  border: 1px solid {DIVIDER}; background: transparent;
}}
.stButton button:hover, .stDownloadButton button:hover {{
  background: color-mix(in srgb, {INK} 7%, transparent); border-color: {DIVIDER}; color: {INK};
}}
.stButton button:active, .stDownloadButton button:active {{ background: color-mix(in srgb, {INK} 14%, transparent); color: {INK}; }}
.stButton button[kind="primary"] {{ background: {ACCENT}; color: {PAPER}; border-color: {ACCENT}; }}
.stButton button[kind="primary"]:hover {{ background: {ACCENT_600}; border-color: {ACCENT_600}; color: {PAPER}; }}
.stButton button[kind="primary"]:active {{ background: {ACCENT_700}; }}
/* download buttons read as ghost links (cyan text, tint on hover) */
.stDownloadButton button {{ border-color: transparent; color: {ACCENT_700}; padding-inline: 5px; }}
.stDownloadButton button:hover {{ background: color-mix(in srgb, {ACCENT} 10%, transparent); border-color: transparent; color: {ACCENT_700}; }}
button:focus-visible, input:focus-visible, [role="radio"]:focus-visible {{
  outline: 2px solid {ACCENT} !important; outline-offset: 2px; box-shadow: none !important;
}}
button:focus:not(:focus-visible) {{ box-shadow: none !important; }}

/* inputs */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="select"] > div {{
  background: {SURFACE} !important; border-radius: 2px !important; border-color: {DIVIDER} !important;
}}
[data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {{ border-color: {ACCENT} !important; }}
[data-baseweb="tag"] {{ background: {ACCENT_100} !important; color: {ACCENT_800} !important; border-radius: 1.5px !important; border: 1px solid {ACCENT}; }}
[data-baseweb="tag"] span {{ color: {ACCENT_800} !important; }}

/* radios as the segmented control */
[data-testid="stRadio"] [role="radiogroup"] {{
  display: inline-flex; flex-wrap: nowrap; gap: 0; border: 1px solid {DIVIDER}; border-radius: 2px; overflow: hidden;
}}
[data-testid="stRadio"] label[data-baseweb="radio"] {{ margin: 0; padding: 7px 12px; cursor: pointer; }}
[data-testid="stRadio"] label[data-baseweb="radio"] + label[data-baseweb="radio"] {{ border-left: 1px solid {DIVIDER}; }}
[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {{ display: none; }}
[data-testid="stRadio"] label[data-baseweb="radio"] p {{ font-size: 13px; }}
[data-testid="stRadio"] label[data-baseweb="radio"]:hover {{ background: color-mix(in srgb, {INK} 7%, transparent); }}
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {{ background: {ACCENT}; }}
[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p {{ color: {PAPER}; }}

/* uploader: dashed dropzone */
[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploadDropzone"] {{
  background: transparent; border: 1px dashed color-mix(in srgb, {INK} 40%, transparent); border-radius: 2px;
}}
[data-testid="stFileUploaderDropzone"]:hover, [data-testid="stFileUploadDropzone"]:hover {{ background: {ACCENT_100}; border-color: {ACCENT}; }}

/* callouts print as plain text: the page draws no boxes */
[data-testid="stAlert"] > div {{ background: transparent !important; border: 0 !important; padding: 0 !important; color: {INK} !important; }}
[data-testid="stAlert"] svg {{ display: none; }}
[data-testid="stAlert"] p {{ font-size: 13px; font-style: italic; color: {MUTED}; }}
/* the health summary: the info box placed right after a .bs-quote-next marker is a pull quote */
.element-container:has(.bs-quote-next) + .element-container [data-testid="stAlert"] p,
[data-testid="stElementContainer"]:has(.bs-quote-next) + [data-testid="stElementContainer"] [data-testid="stAlert"] p {{
  font-size: 21px; line-height: 1.55; color: {INK}; max-width: 64ch;
}}
/* the empty-state warning reads as the section headline */
.element-container:has(.bs-empty-next) + .element-container [data-testid="stAlert"] p,
[data-testid="stElementContainer"]:has(.bs-empty-next) + [data-testid="stElementContainer"] [data-testid="stAlert"] p {{
  font-size: 32px; line-height: 1.15; font-style: normal; font-weight: 600; color: {INK};
}}

/* html helpers */
.bs-kicker {{ font-size: 13px; letter-spacing: 0; color: {MUTED}; }}
.bs-gain {{ color: {GAIN_TEXT}; }} .bs-loss {{ color: {LOSS_TEXT}; }}
.bs-note {{ font-size: 14px; color: color-mix(in srgb, {INK} 75%, transparent); margin: 0 0 8px; }}
.bs-warn {{ font-size: 14px; color: {MAGENTA_700}; margin: 0; }}
.bs-small {{ font-size: 12px; color: color-mix(in srgb, {INK} 65%, transparent); }}

/* upload-error screen */
.bs-err {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr)); gap: 40px 56px; align-items: start; }}
.bs-err-kicker {{ font-size: 13px; letter-spacing: 0; color: {MAGENTA_700}; }}
.bs-err-title {{ font-size: 52px; line-height: 1.08; letter-spacing: -0.02em; font-weight: 600; margin: 14px 0 18px; }}
.bs-err-lede {{ font-size: 18px; line-height: 1.6; max-width: 62ch; margin: 0 0 40px; }}
.bs-err-item {{ display: grid; grid-template-columns: 84px 1fr; gap: 14px; padding: 12px 14px; margin-left: -14px; border-radius: 2px; cursor: default; }}
.bs-err-item:hover {{ background: {MAGENTA_100}; }}
.bs-err-where {{ font-size: 13px; letter-spacing: 0; color: {MAGENTA_700}; padding-top: 3px; }}
.bs-err-msg {{ font-size: 16px; line-height: 1.5; }}
.bs-raw {{ overflow-x: auto; }}
.bs-raw table {{ border-collapse: collapse; font-size: 13px; width: 100%; }}
.bs-raw th {{ text-align: left; font-size: 11px; letter-spacing: 0; color: color-mix(in srgb, {INK} 60%, transparent); padding: 10px; border-bottom: 1px solid {DIVIDER}; }}
.bs-raw td {{ padding: 10px; border-bottom: 1px solid color-mix(in srgb, {INK} 8%, transparent); white-space: nowrap; }}
.bs-raw td.line {{ color: color-mix(in srgb, {INK} 60%, transparent); }}
.bs-raw td.bad {{ background: {MAGENTA_200}; color: {MAGENTA_800}; font-weight: 600; }}
</style>
"""

pio.templates["broadsheet"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, color=INK, size=13),
    title=dict(font=dict(size=20, family=FONT, color=INK), x=0, xanchor="left"),
    paper_bgcolor=PAPER, plot_bgcolor=PAPER, colorway=DONUT_SHADES,
    # automargin: grow the margin to fit tick labels (e.g. sector names), since margin l=0.
    xaxis=dict(showgrid=False, zeroline=False, showline=False, automargin=True,
               tickfont=dict(size=11), title=dict(font=dict(size=12))),
    yaxis=dict(showgrid=False, zerolinecolor=INK, zerolinewidth=1, automargin=True,
               tickfont=dict(size=11), title=dict(font=dict(size=12))),
    hoverlabel=dict(bgcolor=SURFACE, bordercolor=SURFACE, font=dict(family=FONT, color=INK)),
    margin=dict(l=0, r=0, t=56, b=0),
    legend=dict(font=dict(size=13)),
))
pio.templates.default = "broadsheet"


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)
