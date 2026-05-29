import streamlit as st
import pandas as pd
from database import get_schema, run_query
from claude_agent import generate_sql, explain_results

st.set_page_config(
    page_title="DataWarehouse Chatbot",
    page_icon="🏢",
    layout="wide",
)

st.title("🏢 DataWarehouse Analytics Chatbot")
st.caption("Ask any business question in plain English — no SQL knowledge needed!")

# ── Load schema once per session ──────────────────────────────────────────────
@st.cache_resource
def load_schema():
    return get_schema()

try:
    schema = load_schema()
    st.sidebar.success("✅ Connected to DataWarehouseAnalytics")
except Exception as e:
    st.sidebar.error(f"❌ DB Connection failed: {e}")
    st.stop()

# ── Show schema in sidebar ─────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("📋 Available Tables")
    st.code(schema, language="text")
    st.divider()
    st.markdown("**Example questions you can ask:**")
    examples = [
        "Who are the top 10 customers by total sales?",
        "What are the best-selling products this year?",
        "Show me total revenue by month",
        "Which customers haven't bought anything in 6 months?",
        "What is the average order value per product category?",
    ]
    for ex in examples:
        if st.button(ex, key=ex):
            st.session_state["prefill"] = ex

# ── Chat history ───────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(msg["content"])
            if "sql" in msg:
                with st.expander("🔍 View SQL Query"):
                    st.code(msg["sql"], language="sql")
            if "dataframe" in msg:
                st.dataframe(msg["dataframe"], use_container_width=True)
        else:
            st.markdown(msg["content"])

# ── Input ──────────────────────────────────────────────────────────────────────
prefill = st.session_state.pop("prefill", "")
user_input = st.chat_input("Ask a question about your data...", key="chat_input")
question = user_input or prefill

if question:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Step 1: Generate SQL
                sql = generate_sql(question, schema)

                # Step 2: Run query
                df = run_query(sql)

                # Step 3: Explain results
                if df.empty:
                    results_str = "No rows returned."
                else:
                    results_str = df.head(20).to_string(index=False)

                explanation = explain_results(question, sql, results_str)

                # Display
                st.markdown(explanation)
                with st.expander("🔍 View SQL Query"):
                    st.code(sql, language="sql")
                if not df.empty:
                    st.dataframe(df, use_container_width=True)

                # Save to history
                msg = {
                    "role": "assistant",
                    "content": explanation,
                    "sql": sql,
                }
                if not df.empty:
                    msg["dataframe"] = df
                st.session_state.messages.append(msg)

            except ValueError as ve:
                error_msg = f"⚠️ {ve}"
                st.warning(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
            except Exception as e:
                error_msg = f"❌ Something went wrong: {e}"
                st.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
