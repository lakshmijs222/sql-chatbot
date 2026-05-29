import streamlit as st
import pandas as pd
from database import get_schema, run_query
from claude_agent import generate_sql, explain_results

st.set_page_config(
    page_title="DataWarehouse Analytics Chatbot",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Main background */
    .stApp { background-color: #0f1117; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1f2e 0%, #151821 100%);
        border-right: 1px solid #2d3748;
    }

    /* Hide default header */
    [data-testid="stHeader"] { background: transparent; }

    /* Hero banner */
    .hero-banner {
        background: linear-gradient(135deg, #1e3a5f 0%, #0d2137 50%, #1a1040 100%);
        border: 1px solid #2d4a6e;
        border-radius: 16px;
        padding: 32px 40px;
        margin-bottom: 24px;
        position: relative;
        overflow: hidden;
    }
    .hero-banner::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -10%;
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(99,179,237,0.08) 0%, transparent 70%);
        border-radius: 50%;
    }
    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        color: #e2e8f0;
        margin: 0 0 8px 0;
        letter-spacing: -0.5px;
    }
    .hero-subtitle {
        font-size: 1rem;
        color: #718096;
        margin: 0 0 20px 0;
    }
    .hero-badges {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
    }
    .badge {
        background: rgba(99,179,237,0.1);
        border: 1px solid rgba(99,179,237,0.3);
        color: #63b3ed;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 500;
    }

    /* Stat cards */
    .stats-row {
        display: flex;
        gap: 16px;
        margin-bottom: 24px;
    }
    .stat-card {
        flex: 1;
        background: #1a1f2e;
        border: 1px solid #2d3748;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        transition: border-color 0.2s;
    }
    .stat-card:hover { border-color: #4a90d9; }
    .stat-number {
        font-size: 1.8rem;
        font-weight: 700;
        color: #63b3ed;
        display: block;
    }
    .stat-label {
        font-size: 0.75rem;
        color: #718096;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* Chat messages */
    .user-bubble {
        background: linear-gradient(135deg, #2b4c7e, #1e3a5f);
        border: 1px solid #2d4a6e;
        border-radius: 16px 16px 4px 16px;
        padding: 14px 18px;
        margin: 8px 0;
        color: #e2e8f0;
        font-size: 0.95rem;
        max-width: 80%;
        margin-left: auto;
    }
    .assistant-bubble {
        background: #1a1f2e;
        border: 1px solid #2d3748;
        border-left: 3px solid #63b3ed;
        border-radius: 4px 16px 16px 16px;
        padding: 14px 18px;
        margin: 8px 0;
        color: #e2e8f0;
        font-size: 0.95rem;
        max-width: 90%;
    }

    /* Example question buttons */
    .stButton > button {
        background: #1a1f2e !important;
        border: 1px solid #2d3748 !important;
        color: #a0aec0 !important;
        border-radius: 8px !important;
        text-align: left !important;
        font-size: 0.8rem !important;
        padding: 8px 12px !important;
        width: 100% !important;
        transition: all 0.2s !important;
    }
    .stButton > button:hover {
        border-color: #63b3ed !important;
        color: #63b3ed !important;
        background: rgba(99,179,237,0.05) !important;
    }

    /* Chat input */
    [data-testid="stChatInput"] textarea {
        background: #1a1f2e !important;
        border: 1px solid #2d3748 !important;
        border-radius: 12px !important;
        color: #e2e8f0 !important;
    }

    /* Dataframe */
    [data-testid="stDataFrame"] {
        border: 1px solid #2d3748;
        border-radius: 8px;
        overflow: hidden;
    }

    /* Expander */
    [data-testid="stExpander"] {
        background: #0d1117 !important;
        border: 1px solid #2d3748 !important;
        border-radius: 8px !important;
    }

    /* Sidebar section headers */
    .sidebar-section {
        font-size: 0.7rem;
        font-weight: 600;
        color: #4a5568;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 20px 0 8px 0;
    }

    /* Status pill */
    .status-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(72,187,120,0.1);
        border: 1px solid rgba(72,187,120,0.3);
        color: #48bb78;
        padding: 6px 14px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 500;
        margin-bottom: 16px;
    }

    /* Schema table pill */
    .table-pill {
        background: rgba(99,179,237,0.08);
        border: 1px solid rgba(99,179,237,0.2);
        border-radius: 8px;
        padding: 8px 12px;
        margin-bottom: 6px;
        font-size: 0.8rem;
        color: #90cdf4;
    }

    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 60px 20px;
        color: #4a5568;
    }
    .empty-state-icon { font-size: 3rem; margin-bottom: 12px; }
    .empty-state-title { font-size: 1.1rem; color: #718096; margin-bottom: 8px; }
    .empty-state-sub { font-size: 0.85rem; color: #4a5568; }
</style>
""", unsafe_allow_html=True)


# ── Load schema ────────────────────────────────────────────────────────────────
@st.cache_resource
def load_schema():
    return get_schema()

db_connected = False
schema = ""
try:
    schema = load_schema()
    db_connected = True
except Exception as e:
    st.error(f"Database connection failed: {e}")
    st.stop()


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Analytics Assistant")
    st.markdown("---")

    # Status
    if db_connected:
        st.markdown('<div class="status-pill">🟢 &nbsp; Database Connected</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#fc8181">🔴 &nbsp; Disconnected</div>', unsafe_allow_html=True)

    # DB info
    st.markdown('<div class="sidebar-section">Data Source</div>', unsafe_allow_html=True)
    st.markdown('<div class="table-pill">🗄️ &nbsp; DataWarehouseAnalytics</div>', unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section">Available Tables</div>', unsafe_allow_html=True)
    for table, icon in [("gold.dim_customers", "👥"), ("gold.dim_products", "📦"), ("gold.fact_sales", "💰")]:
        st.markdown(f'<div class="table-pill">{icon} &nbsp; {table}</div>', unsafe_allow_html=True)

    st.markdown("---")

    # Example questions
    st.markdown('<div class="sidebar-section">Try asking</div>', unsafe_allow_html=True)
    examples = [
        "💰 Top 10 customers by total sales",
        "📦 Best-selling products this year",
        "📅 Monthly revenue trend",
        "🌍 Sales breakdown by country",
        "⚡ Average order value by category",
        "👥 Customer count by gender",
    ]
    for ex in examples:
        if st.button(ex, key=ex):
            st.session_state["prefill"] = ex.split(" ", 1)[1]

    st.markdown("---")
    st.markdown('<div style="font-size:0.72rem; color:#4a5568; text-align:center;">Powered by Claude AI · SQL Server</div>', unsafe_allow_html=True)


# ── Hero Banner ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
    <div class="hero-title">📊 DataWarehouse Analytics Chatbot</div>
    <div class="hero-subtitle">Ask any business question in plain English — get instant insights from your data</div>
    <div class="hero-badges">
        <span class="badge">🤖 Claude AI</span>
        <span class="badge">🗄️ SQL Server</span>
        <span class="badge">⚡ Real-time Query</span>
        <span class="badge">💬 Natural Language</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Stat cards ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="stats-row">
    <div class="stat-card">
        <span class="stat-number">3</span>
        <span class="stat-label">Tables Available</span>
    </div>
    <div class="stat-card">
        <span class="stat-number">25+</span>
        <span class="stat-label">Columns Mapped</span>
    </div>
    <div class="stat-card">
        <span class="stat-number">∞</span>
        <span class="stat-label">Questions You Can Ask</span>
    </div>
    <div class="stat-card">
        <span class="stat-number">0</span>
        <span class="stat-label">SQL Knowledge Needed</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Chat history ───────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# Empty state
if not st.session_state.messages:
    st.markdown("""
    <div class="empty-state">
        <div class="empty-state-icon">💬</div>
        <div class="empty-state-title">Start a conversation with your data</div>
        <div class="empty-state-sub">Type a question below or pick an example from the sidebar</div>
    </div>
    """, unsafe_allow_html=True)

# Render messages
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f'<div class="user-bubble">🧑‍💼 &nbsp; {msg["content"]}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="assistant-bubble">🤖 &nbsp; {msg["content"]}</div>', unsafe_allow_html=True)
        if "sql" in msg:
            with st.expander("🔍 View Generated SQL Query"):
                st.code(msg["sql"], language="sql")
        if "dataframe" in msg:
            df = msg["dataframe"]
            st.dataframe(df, use_container_width=True, height=min(400, 60 + len(df) * 35))

# ── Input ──────────────────────────────────────────────────────────────────────
prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Ask a question about your data — e.g. 'What is total revenue this year?'")
question = user_input or prefill

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    st.markdown(f'<div class="user-bubble">🧑‍💼 &nbsp; {question}</div>', unsafe_allow_html=True)

    with st.spinner("🤖 Analyzing your question..."):
        try:
            sql = generate_sql(question, schema)
            df = run_query(sql)
            results_str = "No rows returned." if df.empty else df.head(20).to_string(index=False)
            explanation = explain_results(question, sql, results_str)

            st.markdown(f'<div class="assistant-bubble">🤖 &nbsp; {explanation}</div>', unsafe_allow_html=True)
            with st.expander("🔍 View Generated SQL Query"):
                st.code(sql, language="sql")
            if not df.empty:
                st.dataframe(df, use_container_width=True, height=min(400, 60 + len(df) * 35))

            msg = {"role": "assistant", "content": explanation, "sql": sql}
            if not df.empty:
                msg["dataframe"] = df
            st.session_state.messages.append(msg)

        except ValueError as ve:
            st.warning(f"⚠️ {ve}")
            st.session_state.messages.append({"role": "assistant", "content": f"⚠️ {ve}"})
        except Exception as e:
            st.error(f"❌ Something went wrong: {e}")
            st.session_state.messages.append({"role": "assistant", "content": f"❌ Error: {e}"})
