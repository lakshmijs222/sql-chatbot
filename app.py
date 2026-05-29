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
    .stApp { background-color: #0f1117; }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #151821 100%);
        border-right: 1px solid #2d3748;
    }
    [data-testid="stHeader"] { background: transparent; }

    .hero-banner {
        background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 50%, #1a1040 100%);
        border: 1px solid #2d4a6e; border-radius: 16px;
        padding: 28px 36px; margin-bottom: 20px;
    }
    .hero-title { font-size:1.8rem; font-weight:700; color:#e2e8f0; margin:0 0 6px 0; }
    .hero-sub   { font-size:0.9rem; color:#718096; margin:0 0 16px 0; }
    .hero-badges { display:flex; gap:8px; flex-wrap:wrap; }
    .badge {
        background:rgba(99,179,237,0.1); border:1px solid rgba(99,179,237,0.3);
        color:#63b3ed; padding:3px 10px; border-radius:20px;
        font-size:0.72rem; font-weight:500;
    }

    .stats-row { display:flex; gap:14px; margin-bottom:20px; }
    .stat-card {
        flex:1; background:#1a1f2e; border:1px solid #2d3748;
        border-radius:12px; padding:16px; text-align:center;
    }
    .stat-number { font-size:1.6rem; font-weight:700; color:#63b3ed; display:block; }
    .stat-label  { font-size:0.7rem; color:#718096; text-transform:uppercase; letter-spacing:0.5px; }

    /* User bubble */
    .user-bubble {
        background: linear-gradient(135deg,#2b4c7e,#1e3a5f);
        border:1px solid #2d4a6e; border-radius:16px 16px 4px 16px;
        padding:12px 18px; margin:8px 0 4px auto;
        color:#e2e8f0; max-width:72%; font-size:0.92rem;
        display: table; margin-left: auto;
    }

    /* Assistant bubble wraps Streamlit markdown */
    .ai-bubble-wrap {
        background:#1a1f2e; border:1px solid #2d3748;
        border-left:3px solid #63b3ed; border-radius:4px 16px 16px 16px;
        padding:16px 20px; margin:4px 0 8px 0;
        max-width:92%; color:#e2e8f0; line-height:1.7;
    }
    .ai-bubble-wrap p  { margin:0 0 8px 0; color:#e2e8f0; font-size:0.92rem; }
    .ai-bubble-wrap h2,.ai-bubble-wrap h3 {
        color:#90cdf4; font-size:1rem; margin:14px 0 6px 0;
    }
    .ai-bubble-wrap ul  { padding-left:18px; margin:6px 0; }
    .ai-bubble-wrap li  { color:#cbd5e0; font-size:0.9rem; margin-bottom:5px; }
    .ai-bubble-wrap strong { color:#e2e8f0; }
    .ai-bubble-wrap em    { color:#a0aec0; }

    .cache-badge {
        display:inline-block; font-size:0.68rem; color:#68d391;
        background:rgba(104,211,145,0.1); border:1px solid rgba(104,211,145,0.3);
        border-radius:10px; padding:2px 8px; margin-bottom:6px;
    }

    /* Result table */
    .result-wrap {
        background:#1a1f2e; border:1px solid #2d3748;
        border-radius:12px; padding:16px; margin:4px 0 12px 0; overflow-x:auto;
    }
    .result-meta { font-size:0.72rem; color:#718096; margin-bottom:10px; }
    .result-meta span {
        background:rgba(99,179,237,0.1); border:1px solid rgba(99,179,237,0.2);
        color:#63b3ed; padding:2px 8px; border-radius:10px;
        margin-right:6px; font-size:0.7rem;
    }
    .result-table { width:100%; border-collapse:collapse; font-size:0.85rem; }
    .result-table th {
        background:#0d1117; color:#90cdf4; font-weight:600;
        text-align:left; padding:10px 14px;
        border-bottom:2px solid #2d4a6e;
        white-space:nowrap; font-size:0.76rem;
        text-transform:uppercase; letter-spacing:0.4px;
    }
    .result-table td {
        padding:9px 14px; color:#e2e8f0;
        border-bottom:1px solid #1e2535; white-space:nowrap;
    }
    .result-table tr:last-child td { border-bottom:none; }
    .result-table tr:hover td { background:rgba(99,179,237,0.05); }
    .result-table tr:nth-child(even) td { background:rgba(255,255,255,0.02); }

    /* Sidebar */
    .sidebar-section {
        font-size:0.68rem; font-weight:600; color:#4a5568;
        text-transform:uppercase; letter-spacing:1px; margin:16px 0 6px 0;
    }
    .status-pill {
        display:inline-flex; align-items:center; gap:6px;
        background:rgba(72,187,120,0.1); border:1px solid rgba(72,187,120,0.3);
        color:#48bb78; padding:5px 12px; border-radius:20px;
        font-size:0.78rem; font-weight:500; margin-bottom:12px;
    }
    .table-pill {
        background:rgba(99,179,237,0.08); border:1px solid rgba(99,179,237,0.2);
        border-radius:8px; padding:7px 10px; margin-bottom:5px;
        font-size:0.78rem; color:#90cdf4;
    }

    .stButton > button {
        background:#1a1f2e !important; border:1px solid #2d3748 !important;
        color:#a0aec0 !important; border-radius:8px !important;
        text-align:left !important; font-size:0.78rem !important;
        padding:7px 10px !important; width:100% !important;
    }
    .stButton > button:hover {
        border-color:#63b3ed !important; color:#63b3ed !important;
        background:rgba(99,179,237,0.05) !important;
    }
    [data-testid="stChatInput"] textarea {
        background:#1a1f2e !important; border:1px solid #2d3748 !important;
        border-radius:12px !important; color:#e2e8f0 !important;
    }
    [data-testid="stExpander"] {
        background:#0d1117 !important; border:1px solid #2d3748 !important;
        border-radius:8px !important;
    }
    .empty-state { text-align:center; padding:50px 20px; }
    .empty-state-icon  { font-size:2.8rem; margin-bottom:10px; }
    .empty-state-title { font-size:1rem; color:#718096; margin-bottom:6px; }
    .empty-state-sub   { font-size:0.82rem; color:#4a5568; }
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
    <div class="stat-card"><span class="stat-number">3</span><span class="stat-label">Tables</span></div>
    <div class="stat-card"><span class="stat-number">25+</span><span class="stat-label">Columns</span></div>
    <div class="stat-card"><span class="stat-number">{st.session_state.total_queries}</span><span class="stat-label">Queries Run</span></div>
    <div class="stat-card"><span class="stat-number">0</span><span class="stat-label">SQL Needed</span></div>
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


def _is_whole_number_col(series: pd.Series) -> bool:
    """True if every non-null float value is actually a whole number."""
    non_null = series.dropna()
    if len(non_null) == 0:
        return True
    return (non_null == non_null.apply(lambda x: round(x))).all()


def format_df(df: pd.DataFrame) -> pd.DataFrame:
    """Return a display-safe copy with all values formatted correctly."""
    display = df.copy()
    for col in display.columns:
        if pd.api.types.is_integer_dtype(display[col]):
            display[col] = display[col].apply(
                lambda x: f"{int(x):,}" if pd.notna(x) else "—"
            )
        elif pd.api.types.is_float_dtype(display[col]):
            # If all values are whole numbers (e.g. 2010.0, 4992.0) → show as int
            if _is_whole_number_col(display[col]):
                display[col] = display[col].apply(
                    lambda x: f"{int(x):,}" if pd.notna(x) else "—"
                )
            else:
                display[col] = display[col].apply(
                    lambda x: f"{x:,.2f}" if pd.notna(x) else "—"
                )
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
