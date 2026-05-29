import streamlit as st
import pandas as pd
import plotly.express as px
import hashlib
import io
from datetime import datetime
from database import get_schema, run_query
from claude_agent import generate_sql, explain_results
from auth import require_auth
from logger import log_query
import cache as query_cache

st.set_page_config(
    page_title="DataWarehouse Analytics Chatbot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Auth gate ──────────────────────────────────────────────────────────────────
require_auth()
username = st.session_state.get("username", "user")

# ── CSS ────────────────────────────────────────────────────────────────────────
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
        border: 1px solid #2d4a6e;
        border-radius: 16px;
        padding: 28px 36px;
        margin-bottom: 20px;
    }
    .hero-title { font-size:1.8rem; font-weight:700; color:#e2e8f0; margin:0 0 6px 0; }
    .hero-sub { font-size:0.9rem; color:#718096; margin:0 0 16px 0; }
    .hero-badges { display:flex; gap:8px; flex-wrap:wrap; }
    .badge {
        background: rgba(99,179,237,0.1); border:1px solid rgba(99,179,237,0.3);
        color:#63b3ed; padding:3px 10px; border-radius:20px; font-size:0.72rem; font-weight:500;
    }

    .stats-row { display:flex; gap:14px; margin-bottom:20px; }
    .stat-card {
        flex:1; background:#1a1f2e; border:1px solid #2d3748;
        border-radius:12px; padding:16px; text-align:center;
    }
    .stat-number { font-size:1.6rem; font-weight:700; color:#63b3ed; display:block; }
    .stat-label { font-size:0.7rem; color:#718096; text-transform:uppercase; letter-spacing:0.5px; }

    .user-bubble {
        background: linear-gradient(135deg,#2b4c7e,#1e3a5f);
        border:1px solid #2d4a6e; border-radius:16px 16px 4px 16px;
        padding:12px 16px; margin:6px 0; color:#e2e8f0;
        max-width:75%; margin-left:auto; font-size:0.92rem;
    }
    .assistant-bubble {
        background:#1a1f2e; border:1px solid #2d3748;
        border-left:3px solid #63b3ed; border-radius:4px 16px 16px 16px;
        padding:14px 18px; margin:6px 0; color:#e2e8f0;
        max-width:90%; font-size:0.92rem; line-height:1.6;
    }
    .cache-hit {
        display:inline-block; font-size:0.7rem; color:#68d391;
        background:rgba(104,211,145,0.1); border:1px solid rgba(104,211,145,0.3);
        border-radius:10px; padding:2px 8px; margin-bottom:6px;
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
    .empty-state { text-align:center; padding:50px 20px; color:#4a5568; }
    .empty-state-icon { font-size:2.8rem; margin-bottom:10px; }
    .empty-state-title { font-size:1rem; color:#718096; margin-bottom:6px; }
    .empty-state-sub { font-size:0.82rem; color:#4a5568; }
</style>
""", unsafe_allow_html=True)


# ── Schema ─────────────────────────────────────────────────────────────────────
@st.cache_resource
def load_schema():
    return get_schema()

try:
    schema = load_schema()
    schema_hash = hashlib.md5(schema.encode()).hexdigest()
    db_connected = True
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()


# ── Session state defaults ─────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "total_queries" not in st.session_state:
    st.session_state.total_queries = 0
if "cache_hits" not in st.session_state:
    st.session_state.cache_hits = 0


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## 📊 Analytics Assistant")
    st.markdown(f"<div style='font-size:0.78rem;color:#718096;margin-bottom:12px'>Signed in as <b style='color:#90cdf4'>{username}</b></div>", unsafe_allow_html=True)
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
    examples = [
        ("💰", "Top 10 customers by total sales"),
        ("📦", "Best-selling products this year"),
        ("📅", "Monthly revenue trend"),
        ("🌍", "Sales breakdown by country"),
        ("⚡", "Average order value by category"),
        ("👥", "Customer count by gender"),
    ]
    for icon, text in examples:
        if st.button(f"{icon} {text}", key=text):
            st.session_state["prefill"] = text

    st.markdown("---")

    # Clear chat
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.total_queries = 0
        st.session_state.cache_hits = 0
        st.rerun()

    # Logout
    if st.button("🚪 Sign Out", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.markdown('<div style="font-size:0.7rem;color:#4a5568;text-align:center;margin-top:10px">Powered by Claude AI · SQL Server</div>', unsafe_allow_html=True)


# ── Hero ───────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="hero-banner">
    <div class="hero-title">📊 DataWarehouse Analytics Chatbot</div>
    <div class="hero-sub">Ask any business question in plain English — get instant insights from your data warehouse</div>
    <div class="hero-badges">
        <span class="badge">🤖 Claude AI</span>
        <span class="badge">🗄️ SQL Server</span>
        <span class="badge">⚡ Real-time</span>
        <span class="badge">💬 Natural Language</span>
        <span class="badge">📊 Auto Charts</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Stat cards ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="stats-row">
    <div class="stat-card"><span class="stat-number">3</span><span class="stat-label">Tables</span></div>
    <div class="stat-card"><span class="stat-number">25+</span><span class="stat-label">Columns</span></div>
    <div class="stat-card"><span class="stat-number">{st.session_state.total_queries}</span><span class="stat-label">Queries Run</span></div>
    <div class="stat-card"><span class="stat-number">0</span><span class="stat-label">SQL Needed</span></div>
</div>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def try_auto_chart(df: pd.DataFrame):
    """Render a chart if the dataframe looks chartable."""
    if df is None or df.empty or len(df.columns) < 2:
        return
    num_cols = df.select_dtypes(include="number").columns.tolist()
    cat_cols = df.select_dtypes(exclude="number").columns.tolist()
    if not num_cols:
        return

    try:
        if cat_cols and len(df) <= 30:
            fig = px.bar(
                df, x=cat_cols[0], y=num_cols[0],
                color_discrete_sequence=["#63b3ed"],
                template="plotly_dark",
                title=f"{num_cols[0]} by {cat_cols[0]}",
            )
            fig.update_layout(
                plot_bgcolor="#1a1f2e", paper_bgcolor="#1a1f2e",
                font_color="#e2e8f0", margin=dict(t=40, b=20, l=20, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)
        elif len(num_cols) >= 1 and len(df) > 1:
            fig = px.line(
                df, y=num_cols[0],
                color_discrete_sequence=["#63b3ed"],
                template="plotly_dark",
                title=num_cols[0],
            )
            fig.update_layout(
                plot_bgcolor="#1a1f2e", paper_bgcolor="#1a1f2e",
                font_color="#e2e8f0", margin=dict(t=40, b=20, l=20, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass


def export_csv(df: pd.DataFrame, label: str = "results") -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# ── Chat history ───────────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-state-icon">💬</div>
        <div class="empty-state-title">Start a conversation with your data</div>
        <div class="empty-state-sub">Type a question below or pick an example from the sidebar</div>
    </div>
    """, unsafe_allow_html=True)

for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="user-bubble">🧑‍💼 &nbsp; {msg["content"]}</div>', unsafe_allow_html=True)
    else:
        if msg.get("from_cache"):
            st.markdown('<span class="cache-hit">⚡ Cached result</span>', unsafe_allow_html=True)
        st.markdown(f'<div class="assistant-bubble">🤖 &nbsp; {msg["content"]}</div>', unsafe_allow_html=True)
        if "sql" in msg or "dataframe" in msg:
            with st.expander("🔍 View SQL & Full Data"):
                if "sql" in msg:
                    st.code(msg["sql"], language="sql")
                if "dataframe" in msg:
                    df_stored = msg["dataframe"]
                    st.dataframe(df_stored, use_container_width=True)
                    st.download_button(
                        "⬇️ Export CSV",
                        data=export_csv(df_stored),
                        file_name=f"query_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        key=f"dl_{msg.get('ts','')}",
                    )
        if "dataframe" in msg:
            try_auto_chart(msg["dataframe"])


# ── Input ──────────────────────────────────────────────────────────────────────
prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Ask a question — e.g. 'What is total revenue by year?'")
question = user_input or prefill

if question:
    ts = datetime.now().isoformat()
    st.session_state.messages.append({"role": "user", "content": question})
    st.markdown(f'<div class="user-bubble">🧑‍💼 &nbsp; {question}</div>', unsafe_allow_html=True)
    st.session_state.total_queries += 1

    with st.spinner("🤖 Analyzing your question..."):
        try:
            # Check cache first
            cached_sql, cached_df = query_cache.get(question, schema_hash)
            from_cache = cached_sql is not None

            if from_cache:
                sql, df = cached_sql, cached_df
                st.session_state.cache_hits += 1
            else:
                sql = generate_sql(question, schema)
                df = run_query(sql)
                query_cache.set(question, schema_hash, sql, df)

            explanation = explain_results(question, sql, df)

            if from_cache:
                st.markdown('<span class="cache-hit">⚡ Cached result</span>', unsafe_allow_html=True)

            st.markdown(f'<div class="assistant-bubble">🤖 &nbsp; {explanation}</div>', unsafe_allow_html=True)

            if sql or not df.empty:
                with st.expander("🔍 View SQL & Full Data"):
                    st.code(sql, language="sql")
                    if not df.empty:
                        st.dataframe(df, use_container_width=True)
                        st.download_button(
                            "⬇️ Export CSV",
                            data=export_csv(df),
                            file_name=f"query_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                            key=f"dl_new_{ts}",
                        )

            if not df.empty:
                try_auto_chart(df)

            log_query(username, question, sql, len(df))

            msg = {"role": "assistant", "content": explanation, "sql": sql, "ts": ts, "from_cache": from_cache}
            if not df.empty:
                msg["dataframe"] = df
            st.session_state.messages.append(msg)

        except ValueError as ve:
            err = f"⚠️ {ve}"
            st.warning(err)
            log_query(username, question, "", 0, str(ve))
            st.session_state.messages.append({"role": "assistant", "content": err})
        except Exception as e:
            err = f"❌ Something went wrong: {e}"
            st.error(err)
            log_query(username, question, "", 0, str(e))
            st.session_state.messages.append({"role": "assistant", "content": err})
