import streamlit as st
import pandas as pd
import hashlib
import html
import markdown as md_lib
from datetime import datetime
from database import get_schema, run_query
from claude_agent import generate_sql, repair_sql, explain_results, is_report_request, plan_report_sections, get_report_title
from report_generator import generate_report
from auth import require_auth
from logger import log_query
import cache as query_cache

st.set_page_config(
    page_title="InsightIQ",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

require_auth()
username = st.session_state.get("username", "user")

# ── CSS (single block, never repeated) ────────────────────────────────────────
st.markdown("""
<style>
    /* App background — deep gradient */
    .stApp {
        background: radial-gradient(ellipse at top, #141b2e 0%, #0a0e17 60%);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #161d33 0%, #0e1322 100%);
        border-right: 1px solid #2a3654;
    }
    [data-testid="stHeader"] { background: transparent; }

    /* ── HERO ── */
    .hero-banner {
        background: linear-gradient(120deg, #1d4ed8 0%, #2563eb 35%, #6d28d9 100%);
        border: none; border-radius: 20px;
        padding: 32px 40px; margin-bottom: 22px;
        box-shadow: 0 8px 32px rgba(37,99,235,0.35);
        position: relative; overflow: hidden;
    }
    .hero-banner::after {
        content:''; position:absolute; top:-60px; right:-40px;
        width:240px; height:240px; border-radius:50%;
        background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, transparent 70%);
    }
    .hero-title { font-size:2rem; font-weight:800; color:#ffffff; margin:0 0 8px 0; letter-spacing:-0.5px; }
    .hero-sub   { font-size:0.98rem; color:#dbeafe; margin:0 0 18px 0; font-weight:400; }
    .hero-badges { display:flex; gap:9px; flex-wrap:wrap; position:relative; z-index:1; }
    .badge {
        background:rgba(255,255,255,0.18); border:1px solid rgba(255,255,255,0.35);
        color:#ffffff; padding:5px 13px; border-radius:20px;
        font-size:0.74rem; font-weight:600; backdrop-filter:blur(4px);
    }

    /* ── STAT CARDS ── */
    .stats-row { display:flex; gap:16px; margin-bottom:24px; }
    .stat-card {
        flex:1; border-radius:16px; padding:20px 16px; text-align:center;
        border:1px solid rgba(255,255,255,0.08);
        box-shadow: 0 4px 16px rgba(0,0,0,0.25);
        transition: transform 0.15s, box-shadow 0.15s;
    }
    .stat-card:hover { transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
    .stat-card.c1 { background: linear-gradient(145deg,#1e3a8a,#1e40af); }
    .stat-card.c2 { background: linear-gradient(145deg,#5b21b6,#6d28d9); }
    .stat-card.c3 { background: linear-gradient(145deg,#0e7490,#0891b2); }
    .stat-card.c4 { background: linear-gradient(145deg,#065f46,#047857); }
    .stat-number { font-size:1.9rem; font-weight:800; color:#ffffff; display:block; line-height:1.1; }
    .stat-label  { font-size:0.68rem; color:rgba(255,255,255,0.8); text-transform:uppercase; letter-spacing:0.8px; font-weight:600; margin-top:4px; }

    /* ── USER BUBBLE ── */
    .user-bubble {
        background: linear-gradient(135deg,#2563eb,#1d4ed8);
        border:none; border-radius:18px 18px 4px 18px;
        padding:13px 18px; margin:10px 0 4px auto;
        color:#ffffff; max-width:74%; font-size:0.93rem; font-weight:500;
        display: table; margin-left: auto;
        box-shadow: 0 3px 12px rgba(37,99,235,0.4);
    }

    /* ── ASSISTANT BUBBLE ── */
    .ai-bubble-wrap {
        background: linear-gradient(160deg,#1a2238,#141b2e);
        border:1px solid #2a3654;
        border-left:4px solid #60a5fa; border-radius:4px 18px 18px 18px;
        padding:18px 22px; margin:4px 0 10px 0;
        max-width:92%; color:#f1f5f9; line-height:1.75;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .ai-bubble-wrap p  { margin:0 0 10px 0; color:#f1f5f9; font-size:0.94rem; }
    .ai-bubble-wrap h2,.ai-bubble-wrap h3 {
        color:#93c5fd; font-size:1.05rem; margin:16px 0 8px 0; font-weight:700;
    }
    .ai-bubble-wrap ul  { padding-left:20px; margin:8px 0; }
    .ai-bubble-wrap li  { color:#e2e8f0; font-size:0.92rem; margin-bottom:7px; }
    .ai-bubble-wrap strong { color:#ffffff; font-weight:700; }
    .ai-bubble-wrap em    { color:#cbd5e0; }

    .cache-badge {
        display:inline-block; font-size:0.7rem; color:#6ee7b7; font-weight:600;
        background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.4);
        border-radius:10px; padding:3px 10px; margin-bottom:6px;
    }

    /* ── RESULT TABLE ── */
    .result-wrap {
        background: linear-gradient(160deg,#1a2238,#141b2e);
        border:1px solid #2a3654;
        border-radius:16px; padding:18px; margin:4px 0 14px 0; overflow-x:auto;
        box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    }
    .result-meta { font-size:0.74rem; margin-bottom:12px; }
    .result-meta span {
        background:rgba(96,165,250,0.18); border:1px solid rgba(96,165,250,0.4);
        color:#93c5fd; padding:3px 10px; border-radius:10px;
        margin-right:7px; font-size:0.72rem; font-weight:600;
    }
    .result-table { width:100%; border-collapse:collapse; font-size:0.87rem; }
    .result-table th {
        background: linear-gradient(180deg,#2563eb,#1d4ed8); color:#ffffff; font-weight:700;
        text-align:left; padding:12px 16px;
        white-space:nowrap; font-size:0.74rem;
        text-transform:uppercase; letter-spacing:0.5px;
    }
    .result-table th:first-child { border-top-left-radius:10px; }
    .result-table th:last-child  { border-top-right-radius:10px; }
    .result-table td {
        padding:10px 16px; color:#f1f5f9;
        border-bottom:1px solid #2a3654; white-space:nowrap;
    }
    .result-table tr:last-child td { border-bottom:none; }
    .result-table tr:hover td { background:rgba(96,165,250,0.1); }
    .result-table tr:nth-child(even) td { background:rgba(255,255,255,0.03); }

    /* ── SIDEBAR ── */
    .sidebar-section {
        font-size:0.7rem; font-weight:700; color:#94a3b8;
        text-transform:uppercase; letter-spacing:1.2px; margin:18px 0 8px 0;
    }
    .status-pill {
        display:inline-flex; align-items:center; gap:6px;
        background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.45);
        color:#6ee7b7; padding:6px 14px; border-radius:20px;
        font-size:0.8rem; font-weight:600; margin-bottom:12px;
    }
    .table-pill {
        background: linear-gradient(135deg, rgba(96,165,250,0.12), rgba(139,92,246,0.12));
        border:1px solid rgba(96,165,250,0.3);
        border-radius:10px; padding:9px 12px; margin-bottom:7px;
        font-size:0.8rem; color:#bfdbfe; font-weight:500;
    }

    .stButton > button {
        background: linear-gradient(135deg, rgba(96,165,250,0.1), rgba(139,92,246,0.1)) !important;
        border:1px solid rgba(96,165,250,0.25) !important;
        color:#cbd5e1 !important; border-radius:10px !important;
        text-align:left !important; font-size:0.8rem !important;
        padding:9px 12px !important; width:100% !important; font-weight:500 !important;
        transition: all 0.15s !important;
    }
    .stButton > button:hover {
        border-color:#60a5fa !important; color:#ffffff !important;
        background: linear-gradient(135deg, rgba(96,165,250,0.25), rgba(139,92,246,0.25)) !important;
        transform: translateX(2px) !important;
    }
    [data-testid="stChatInput"] textarea {
        background:#1a2238 !important; border:1px solid #2a3654 !important;
        border-radius:14px !important; color:#f1f5f9 !important; font-size:0.92rem !important;
    }
    [data-testid="stChatInput"] textarea:focus {
        border-color:#60a5fa !important; box-shadow:0 0 0 2px rgba(96,165,250,0.2) !important;
    }
    [data-testid="stExpander"] {
        background:#141b2e !important; border:1px solid #2a3654 !important;
        border-radius:10px !important;
    }
    /* Sidebar metric values brighter */
    [data-testid="stMetricValue"] { color:#93c5fd !important; font-weight:700 !important; }
    [data-testid="stMetricLabel"] { color:#94a3b8 !important; }

    .empty-state { text-align:center; padding:50px 20px; }
    .empty-state-icon  { font-size:3rem; margin-bottom:12px; }
    .empty-state-title { font-size:1.1rem; color:#cbd5e1; margin-bottom:6px; font-weight:600; }
    .empty-state-sub   { font-size:0.86rem; color:#7c8aa5; }
</style>
""", unsafe_allow_html=True)


# ── Schema ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def load_schema():
    return get_schema()

try:
    schema = load_schema()
    schema_hash = hashlib.md5(schema.encode()).hexdigest()
except Exception as e:
    st.error("Could not connect to the database. Please check your DB_SERVER and DB_NAME settings.")
    st.stop()

# ── Session defaults ───────────────────────────────────────────────────────────
for key, default in [("messages", []), ("total_queries", 0), ("cache_hits", 0)]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🔍 InsightIQ")
    st.markdown(
        f"<div style='font-size:0.78rem;color:#718096;margin-bottom:12px'>"
        f"Signed in as <b style='color:#90cdf4'>{html.escape(username)}</b></div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown('<div class="status-pill">🟢 &nbsp; Database Connected</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section">Data Source</div>', unsafe_allow_html=True)
    st.markdown('<div class="table-pill">🗄️ &nbsp; DataWarehouseAnalytics</div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-section">Available Tables</div>', unsafe_allow_html=True)
    for table, icon in [("gold.dim_customers","👥"),("gold.dim_products","📦"),("gold.fact_sales","💰")]:
        st.markdown(f'<div class="table-pill">{icon} &nbsp; {table}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div class="sidebar-section">Session Stats</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    c1.metric("Queries", st.session_state.total_queries)
    c2.metric("Cache Hits", st.session_state.cache_hits)
    st.markdown("---")
    st.markdown('<div class="sidebar-section">Try asking</div>', unsafe_allow_html=True)
    for icon, text in [
        ("💰","Top 10 customers by total sales"),
        ("📦","Best-selling products"),
        ("📅","Monthly revenue trend"),
        ("🌍","Sales breakdown by country"),
        ("⚡","Average order value by category"),
        ("👥","Customer count by gender"),
    ]:
        if st.button(f"{icon} {text}", key=text):
            st.session_state["prefill"] = text
    st.markdown("---")
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.total_queries = 0
        st.session_state.cache_hits = 0
        st.rerun()
    if st.button("🚪 Sign Out", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
    st.markdown(
        '<div style="font-size:0.7rem;color:#4a5568;text-align:center;margin-top:10px">'
        'Powered by Claude AI · SQL Server</div>',
        unsafe_allow_html=True,
    )


# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="hero-banner">
    <div class="hero-title">🔍 InsightIQ</div>
    <div class="hero-sub">Ask your data, get instant answers — no SQL knowledge needed</div>
    <div class="hero-badges">
        <span class="badge">🤖 Claude AI</span>
        <span class="badge">🗄️ SQL Server</span>
        <span class="badge">⚡ Real-time</span>
        <span class="badge">💬 Natural Language</span>
        <span class="badge">📊 Smart Tables</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="stats-row">
    <div class="stat-card c1"><span class="stat-number">3</span><span class="stat-label">Tables</span></div>
    <div class="stat-card c2"><span class="stat-number">25+</span><span class="stat-label">Columns</span></div>
    <div class="stat-card c3"><span class="stat-number">{st.session_state.total_queries}</span><span class="stat-label">Queries Run</span></div>
    <div class="stat-card c4"><span class="stat-number">0</span><span class="stat-label">SQL Needed</span></div>
</div>
""", unsafe_allow_html=True)


# ── Utilities ──────────────────────────────────────────────────────────────────
def safe_str(val) -> str:
    """Convert any cell value to a safe, display-ready string."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return "—"
    if isinstance(val, (int,)) or (isinstance(val, float) and val == int(val)):
        return f"{int(val):,}"
    if isinstance(val, float):
        return f"{val:,.2f}"
    if hasattr(val, 'date'):          # datetime / date objects
        return str(val.date()) if hasattr(val, 'hour') else str(val)
    return html.escape(str(val))      # escape HTML special chars


_YEAR_COL_PATTERNS = ("year", "yr", "month", "mo", "quarter", "qtr", "rank", "age", "day")
_PCT_COL_PATTERNS  = ("pct", "percent", "growth", "rate", "ratio", "change")


def _is_year_col(col_name: str) -> bool:
    return any(p in col_name.lower() for p in _YEAR_COL_PATTERNS)


def _is_pct_col(col_name: str) -> bool:
    return any(p in col_name.lower() for p in _PCT_COL_PATTERNS)


def _is_whole_number_col(series: pd.Series) -> bool:
    non_null = series.dropna()
    if len(non_null) == 0:
        return True
    return bool((non_null % 1 == 0).all())


def _fmt_int(x):
    return f"{int(x):,}" if pd.notna(x) else "—"


def _fmt_year(x):
    """Year/rank/month numbers — no comma, no decimal."""
    return str(int(x)) if pd.notna(x) else "—"


def _fmt_pct(x):
    """Percentage values — always 2 decimals with % sign."""
    return f"{x:,.2f}%" if pd.notna(x) else "—"


def _fmt_float(x):
    return f"{x:,.2f}" if pd.notna(x) else "—"


def format_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return a display-safe copy with smart column-aware formatting."""
    display = df.copy()
    for col in display.columns:
        col_lower = col.lower()

        if pd.api.types.is_integer_dtype(display[col]):
            if _is_year_col(col_lower):
                display[col] = display[col].apply(_fmt_year)
            else:
                display[col] = display[col].apply(_fmt_int)

        elif pd.api.types.is_float_dtype(display[col]):
            if _is_pct_col(col_lower):
                # Always show as decimal% — never treat as whole number
                display[col] = display[col].apply(_fmt_pct)
            elif _is_year_col(col_lower):
                display[col] = display[col].apply(_fmt_year)
            elif _is_whole_number_col(display[col]):
                display[col] = display[col].apply(_fmt_int)
            else:
                display[col] = display[col].apply(_fmt_float)

        elif pd.api.types.is_datetime64_any_dtype(display[col]):
            display[col] = display[col].apply(
                lambda x: str(x.date()) if pd.notna(x) else "—"
            )
        else:
            display[col] = display[col].apply(
                lambda x: html.escape(str(x)) if pd.notna(x) else "—"
            )
    return display


def render_table(df: pd.DataFrame, key: str):
    """Render a styled HTML table + CSV download button."""
    if df is None or df.empty:
        st.info("The query returned no results.")
        return

    display = format_df(df)
    headers = "".join(f"<th>{html.escape(str(c))}</th>" for c in display.columns)
    rows_html = ""
    for _, row in display.iterrows():
        cells = "".join(f"<td>{v}</td>" for v in row)
        rows_html += f"<tr>{cells}</tr>"

    st.markdown(f"""
    <div class="result-wrap">
        <div class="result-meta">
            <span>📊 {len(df)} rows</span>
            <span>🗂 {len(df.columns)} columns</span>
        </div>
        <table class="result-table">
            <thead><tr>{headers}</tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

    ts_clean = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "⬇️ Export CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"insightiq_{ts_clean}.csv",
        mime="text/csv",
        key=f"csv_{key}",
    )


def render_ai_bubble(text: str):
    """Render Claude's markdown response inside a styled bubble."""
    html_content = md_lib.markdown(
        text,
        extensions=["nl2br"],
    )
    st.markdown(
        f'<div class="ai-bubble-wrap">🤖 &nbsp; {html_content}</div>',
        unsafe_allow_html=True,
    )


def render_user_bubble(text: str):
    st.markdown(
        f'<div class="user-bubble">🧑‍💼 &nbsp; {html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


# ── Chat history ───────────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-state-icon">💬</div>
        <div class="empty-state-title">Start a conversation with your data</div>
        <div class="empty-state-sub">Type a question below or pick an example from the sidebar</div>
    </div>
    """, unsafe_allow_html=True)

for i, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        render_user_bubble(msg["content"])
    else:
        if msg.get("from_cache"):
            st.markdown('<span class="cache-badge">⚡ Cached result</span>', unsafe_allow_html=True)
        render_ai_bubble(msg["content"])
        if "report_bytes" in msg:
            st.download_button(label="📄 Download Report (.docx)", data=msg["report_bytes"],
                               file_name=msg.get("report_filename", "report.docx"),
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               key=f"report_hist_{i}")
        if "dataframe" in msg:
            render_table(msg["dataframe"], key=f"hist_{i}")
        if "sql" in msg:
            with st.expander("🔍 View SQL Query"):
                st.code(msg["sql"], language="sql")


# ── Input & processing ─────────────────────────────────────────────────────────
prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Ask a question — e.g. 'What is total revenue by year?'")
question = (user_input or prefill or "").strip()

if question:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.session_state.messages.append({"role": "user", "content": question})
    render_user_bubble(question)
    st.session_state.total_queries += 1

    with st.spinner("Analyzing your question..."):
        sql = ""
        df = pd.DataFrame()
        error_msg = None

        try:
            # ── REPORT REQUEST ─────────────────────────────────────────────────
            if is_report_request(question):
                sections_plan = plan_report_sections(question)
                report_title  = get_report_title(question)
                sections      = []
                summary_stats = {}
                total         = len(sections_plan)
                progress      = st.progress(0, text="Building report...")

                for idx, sec in enumerate(sections_plan):
                    progress.progress(idx / total, text=f"Section {idx+1}/{total}: {sec['heading']}...")
                    try:
                        sec_sql = generate_sql(sec["question"], schema)
                        try:
                            sec_df = run_query(sec_sql)
                        except Exception as db_err:
                            sec_sql = repair_sql(sec_sql, str(db_err), schema)
                            sec_df  = run_query(sec_sql)
                        sec_explanation = explain_results(sec["question"], sec_sql, sec_df)
                        log_query(username, sec["question"], sec_sql, len(sec_df))
                        sections.append({"heading": sec["heading"], "explanation": sec_explanation,
                                         "df": sec_df if not sec_df.empty else None, "sql": sec_sql})
                        if idx == 0 and not sec_df.empty:
                            for col in sec_df.select_dtypes(include="number").columns[:4]:
                                val = sec_df[col].sum()
                                label = col.replace("_", " ").title()
                                summary_stats[label] = f"{int(val):,}" if pd.api.types.is_integer_dtype(sec_df[col]) else f"{val:,.0f}"
                    except Exception as sec_err:
                        sections.append({"heading": sec["heading"],
                                         "explanation": f"Could not generate this section: {sec_err}",
                                         "df": None, "sql": ""})

                progress.progress(1.0, text="Finalising...")
                doc_bytes = generate_report(title=report_title, sections=sections,
                                            summary_stats=summary_stats, username=username)
                progress.empty()

                reply = f"Your **{report_title}** is ready with **{len(sections)} sections**."
                render_ai_bubble(reply)
                fn = report_title.replace(" ", "_")[:40] + f"_{ts}.docx"
                st.download_button(label="📄 Download Report (.docx)", data=doc_bytes,
                                   file_name=fn, mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   key=f"report_{ts}")
                st.session_state.messages.append({"role": "assistant", "content": reply,
                                                   "report_bytes": doc_bytes, "report_filename": fn, "ts": ts})

            # ── NORMAL QUESTION ────────────────────────────────────────────────
            else:
                cached_sql, cached_df = query_cache.get(question, schema_hash)
                from_cache = cached_sql is not None

                if from_cache:
                    sql, df = cached_sql, cached_df
                    st.session_state.cache_hits += 1
                else:
                    sql = generate_sql(question, schema)
                    try:
                        df = run_query(sql)
                    except Exception as db_err:
                        repaired = repair_sql(sql, str(db_err), schema)
                        if repaired != sql:
                            sql = repaired
                            df  = run_query(sql)
                        else:
                            raise
                    query_cache.set(question, schema_hash, sql, df)

                explanation = explain_results(question, sql, df)

                if from_cache:
                    st.markdown('<span class="cache-badge">⚡ Cached result</span>', unsafe_allow_html=True)

                render_ai_bubble(explanation)
                if not df.empty:
                    render_table(df, key=f"new_{ts}")
                with st.expander("🔍 View SQL Query"):
                    st.code(sql, language="sql")

                log_query(username, question, sql, len(df))
                saved = {"role": "assistant", "content": explanation, "sql": sql, "ts": ts, "from_cache": from_cache}
                if not df.empty:
                    saved["dataframe"] = df
                st.session_state.messages.append(saved)

        except ValueError as ve:
            error_msg = str(ve)
            st.warning(f"⚠️ {error_msg}")
            log_query(username, question, sql, 0, error_msg)
            st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {error_msg}"})

        except Exception as e:
            # Show user-friendly message, log the real error
            error_msg = str(e)
            friendly = error_msg if error_msg else "An unexpected error occurred. Please try rephrasing your question."
            st.error(f"❌ {friendly}")
            log_query(username, question, sql, 0, error_msg)
            st.session_state.messages.append({"role": "assistant", "content": f"❌ {friendly}"})
