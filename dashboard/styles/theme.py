"""Lamplighter visual tokens."""

COLORS = {
    "primary": "#123B63", "accent": "#F3B61F", "success": "#13795B",
    "warning": "#A45A08", "danger": "#B42332", "muted": "#5F6F82",
    "surface": "#FFFFFF", "background": "#F3F6FA", "dark": "#111827",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap');
:root { --lamp-blue:#123B63; --lamp-ink:#172B42; --lamp-muted:#5F6F82; --lamp-line:#DFE6EE; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; }
.stApp { background:#F3F6FA; color:var(--lamp-ink); }
[data-testid="stAppViewContainer"] { background:#F3F6FA; }
[data-testid="stHeader"] { background:rgba(243,246,250,.92); }
[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid var(--lamp-line); }
[data-testid="stSidebar"] * { color:#263B52; }
.stApp h1,.stApp h2,.stApp h3,.stApp p,.stApp label,.stApp [data-testid="stCaptionContainer"] { color:var(--lamp-ink); }
.stApp [data-testid="stCaptionContainer"] { color:var(--lamp-muted); }
[data-testid="stMetric"] { background:#fff; border:1px solid var(--lamp-line); border-radius:14px; padding:16px 18px; box-shadow:0 3px 12px #1836530a; }
[data-testid="stMetricLabel"] { color:#526275; font-size:.76rem; font-weight:700; letter-spacing:.045em; text-transform:uppercase; }
[data-testid="stMetricValue"] { color:#123B63; font-weight:700; }
.eyebrow { color:#526275; font-size:.75rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; }
.note { background:#EAF2FA; border-left:4px solid #123B63; padding:16px 18px; border-radius:0 10px 10px 0; color:#1F2937; }
.preview { background:#FFF7E2; border:1px solid #F0CD72; padding:12px 16px; border-radius:10px; color:#634300; font-weight:600; }
.status { display:inline-block; padding:5px 10px; border-radius:999px; font-size:.82rem; font-weight:700; }
.status-live { color:#116149; background:#DDF4EA; }
.status-offline { color:#9F2632; background:#FCE8E8; }
.mono { font-family:'IBM Plex Mono',monospace; }
button:focus, a:focus, input:focus { outline:3px solid #F3B61F !important; outline-offset:2px; }
.stButton > button { min-height:2.65rem; border-radius:9px; font-weight:650; transition:background-color .16s ease,border-color .16s ease,box-shadow .16s ease,transform .16s ease; }
.stButton > button[kind="primary"], .stButton [data-testid="stBaseButton-primary"] { background:#D84046; border:1px solid #D84046; color:#fff; }
.stButton > button[kind="primary"]:hover, .stButton [data-testid="stBaseButton-primary"]:hover { background:#B92F38; border-color:#B92F38; color:#fff; box-shadow:0 4px 12px #B92F3833; transform:translateY(-1px); }
.stButton > button:not([kind="primary"]) { background:#fff; border:1px solid #CBD5E1; color:#263B52; }
.stButton > button:not([kind="primary"]):hover { background:#EDF3F8; border-color:#8295A9; color:#123B63; }
.stButton > button:active { transform:translateY(0); }
.stButton > button:disabled { background:#E8EDF2; border-color:#D8E0E8; color:#8693A1; box-shadow:none; transform:none; cursor:not-allowed; }
button:focus-visible, a:focus-visible, input:focus-visible { outline:3px solid #F3B61F !important; outline-offset:2px; }
</style>
"""

DARK_CSS = """
<style>
.stApp,[data-testid="stAppViewContainer"] { background:#111827 !important; color:#E5E7EB; }
[data-testid="stHeader"] { background:rgba(17,24,39,.94); }
[data-testid="stSidebar"] { background:#172033 !important; border-color:#374151; }
.stApp h1,.stApp h2,.stApp h3,.stApp p,.stApp label,
.stApp [data-testid="stCaptionContainer"], [data-testid="stSidebar"] * { color:#E5E7EB; }
.stApp [data-testid="stCaptionContainer"] { color:#AAB8C8; }
[data-testid="stMetric"] { background:#1F2937; border-color:#374151; }
[data-testid="stMetricLabel"] { color:#CBD5E1; }
[data-testid="stMetricValue"] { color:#F9FAFB; }
[data-baseweb="select"] > div, [data-baseweb="input"] > div,
[data-baseweb="textarea"] > div, [data-baseweb="popover"] [role="listbox"],
[data-testid="stMultiSelect"] [data-baseweb="tag"] { background-color:#263449; color:#F9FAFB; border-color:#4B5D73; }
[data-testid="stAlert"] { background-color:#253247; color:#F9FAFB; }
[data-testid="stAlert"] p,[data-testid="stAlert"] div { color:#F9FAFB; }
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]) { background:#202D40; border-color:#4B5D73; color:#E5E7EB; }
[data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover { background:#30425A; border-color:#7489A2; color:#fff; }
[data-testid="stSidebar"] .stButton > button:disabled { background:#263244; border-color:#35445A; color:#718198; }
.stButton > button[kind="primary"], .stButton [data-testid="stBaseButton-primary"] { background:#E34C53; border-color:#E34C53; color:#fff; }
.stButton > button[kind="primary"]:hover, .stButton [data-testid="stBaseButton-primary"]:hover { background:#F06B70; border-color:#F06B70; color:#111827; }
.stButton > button:disabled { background:#354154; border-color:#3E4A5D; color:#8995A6; }
.note { background:#172554; color:#F9FAFB; }
.preview { background:#3B2D12; color:#FEF3C7; border-color:#80651D; }
.status-live { background:#174C3C; color:#BBF7D0; }
.status-offline { background:#572A32; color:#FECACA; }
</style>
"""
