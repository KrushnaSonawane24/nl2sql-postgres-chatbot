from __future__ import annotations

import os
import sys

import streamlit as st
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nl2sql.agent import NL2SQLError, answer_question  # noqa: E402
from nl2sql.config import load_settings  # noqa: E402
from nl2sql.db import DatabaseError, PostgresDB  # noqa: E402
from nl2sql.llm_client import LLMError  # noqa: E402
from nl2sql.sql_safety import SQLMode, classify_statement  # noqa: E402

load_dotenv()

# Professional page configuration
st.set_page_config(
    page_title="NL2SQL - PostgreSQL Query Assistant",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ChatGPT-inspired dark theme CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Söhne:wght@400;500;600&family=Inter:wght@400;500;600&display=swap');
    
    /* Global dark theme */
    .stApp {
        background-color: #030303;
        color: #ececf1;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* Main container */
    .main .block-container {
        padding: 3rem 1rem 1rem;
        max-width: 48rem;
        margin: 0 auto;
    }
    
    /* Title styling */
    h1 {
        color: #ececf1;
        font-weight: 600;
        font-size: 1.5rem !important;
        margin-bottom: 0.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #161718;
    }
    
    /* Caption */
    .stApp p {
        color: #b4b4b4;
    }
    
    /* Sidebar - ChatGPT style */
    [data-testid="stSidebar"] {
        background-color: #202123;
        border-right: 1px solid #565869;
    }
    
    [data-testid="stSidebar"] * {
        color: #ececf1 !important;
    }
    
    [data-testid="stSidebar"] .stMarkdown {
        color: #ececf1;
    }
    
    /* Sidebar inputs */
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] select {
        background-color: #161618 !important;
        border: 1px solid #161718 !important;
        color: #ececf1 !important;
        border-radius: 6px;
    }
    
    [data-testid="stSidebar"] input:focus,
    [data-testid="stSidebar"] select:focus {
        border-color: #10a37f !important;
        box-shadow: 0 0 0 1px #10a37f !important;
    }
    
    /* Chat messages */
    .stChatMessage {
        background-color: transparent;
        padding: 1.5rem 0;
        border-bottom: 1px solid #161718;
    }
    
    [data-testid="stChatMessageContent"] {
        background-color: transparent !important;
        color: #ececf1;
    }
    
    /* User message */
    .stChatMessage[data-testid="user"] {
        background-color: #030303;
    }
    
    /* Assistant message */
    .stChatMessage[data-testid="assistant"] {
        background-color: #000000;
    }
    
    /* Code blocks - GitHub dark style */
    .stCodeBlock {
        background-color: #0d1117 !important;
        border: 1px solid #000000;
        border-radius: 6px;
        border-left: 3px solid #10a37f;
    }
    
    .stCodeBlock code {
        color: #c9d1d9 !important;
    }
    
    /* Dataframes */
    .stDataFrame {
        background-color: #161618;
        border: 1px solid #161718;
        border-radius: 6px;
    }
    
    .stDataFrame table {
        color: #ececf1;
    }
    
    /* Buttons - ChatGPT style */
    .stButton button {
        background-color: #10a37f;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 0.5rem 1rem;
        font-weight: 500;
        transition: background-color 0.2s;
    }
    
    .stButton button:hover {
        background-color: #1a7f64;
    }
    
    /* Success/Error/Warning messages */
    .stSuccess {
        background-color: #1a472a;
        border-left: 3px solid #10a37f;
        color: #ececf1;
    }
    
    .stError {
        background-color: #4a1a1a;
        border-left: 3px solid #ef4444;
        color: #ececf1;
    }
    
    .stWarning {
        background-color: #4a3a1a;
        border-left: 3px solid #f59e0b;
        color: #ececf1;
    }
    
    .stInfo {
        background-color: #1a3a4a;
        border-left: 3px solid #3b82f6;
        color: #ececf1;
    }
    
    /* Chat input */
    .stChatInput {
        background-color: #161618;
        border-radius: 12px;
    }
    
    .stChatInput input {
        background-color: #161618 !important;
        border: 1px solid #161718 !important;
        color: #ececf1 !important;
    }
    
    /* Expanders */
    .streamlit-expanderHeader {
        background-color: #161618;
        color: #ececf1;
        border-radius: 6px;
    }
    
    /* Captions */
    .stCaption {
        color: #b4b4b4 !important;
    }
    
    /* Dividers */
    hr {
        border-color: #161718;
    }
</style>
""", unsafe_allow_html=True)

st.title("Natural Language to SQL Query Assistant")
st.caption("PostgreSQL Database Interaction Tool")

settings = load_settings()

with st.sidebar:
    st.subheader("Database Configuration")
    database_url = st.text_input("PostgreSQL URL", value=settings.database_url, type="password", help="Connection string format: postgresql://user:pass@host:port/db")

    st.subheader("LLM Configuration")
    provider = settings.provider
    api_key = settings.api_key
    model = settings.model
    if api_key:
        st.success(f"Provider: {provider.upper()} | Model: {model}")
    else:
        st.warning("API key not configured in environment")

    st.subheader("Query Safety")
    _sql_mode_options = ["read_only", "write_no_delete", "write_full"]
    _default_sql_mode = st.session_state.get("sql_mode") or "write_full"
    if _default_sql_mode not in _sql_mode_options:
        _default_sql_mode = "write_full"
    sql_mode: SQLMode = st.selectbox(
        "Operation Mode",
        options=_sql_mode_options,
        index=_sql_mode_options.index(_default_sql_mode),
        key="sql_mode",
        help="read_only: SELECT only | write_no_delete: INSERT/UPDATE | write_full: Full CRUD"
    )
    statement_timeout_ms = st.number_input(
        "Query Timeout (ms)", min_value=1000, max_value=60000, value=settings.statement_timeout_ms, step=1000
    )
    max_rows = st.number_input("Result Limit", min_value=1, max_value=2000, value=settings.max_rows, step=50)
    st.caption(f"Short memory: last {settings.memory_user_turns} user prompt(s).")
    st.caption(f"Max SQL statements per request: {settings.max_sql_statements}.")

    st.caption("Tip: keep your API key in a local .env file (never commit it).")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" not in st.session_state:
    st.session_state.pending = None
if "sql_mode" not in st.session_state:
    st.session_state.sql_mode = "write_full"

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sql"):
            st.markdown("**Generated SQL:**")
            st.code(m["sql"], language="sql")
        if m.get("results"):
            for i, r in enumerate(m["results"], start=1):
                if len(m["results"]) > 1:
                    st.caption(f"statement #{i}")
                if r.get("meta"):
                    st.caption(r["meta"])
                if r.get("rows") is not None:
                    st.dataframe(r["rows"], use_container_width=True)
        else:
            if m.get("rows") is not None:
                st.dataframe(m["rows"], use_container_width=True)
            if m.get("meta"):
                st.caption(m["meta"])


def _run_pending(db: PostgresDB):
    pending = st.session_state.pending
    if not pending:
        return
    sql = pending["sql"]
    question = pending["question"]
    try:
        resp = answer_question(
            provider=provider,
            api_key=api_key,
            model=model,
            db=db,
            question=question,
            chat_history=st.session_state.messages,
            statement_timeout_ms=int(statement_timeout_ms),
            max_rows=int(max_rows),
            sql_mode=sql_mode,
            execute=True,
            sql_override=sql,
            memory_user_turns=settings.memory_user_turns,
            max_sql_statements=settings.max_sql_statements,
        )
        results_payload = []
        for r in resp.results or []:
            results_payload.append({"rows": r.rows, "meta": f"rowcount: {r.rowcount}"})
        st.session_state.messages.append({"role": "assistant", "content": resp.answer, "sql": resp.sql, "results": results_payload})
        st.session_state.pending = None
        st.rerun()
    except (NL2SQLError, LLMError, DatabaseError) as e:
        st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
        st.session_state.pending = None
        st.rerun()

prompt = st.chat_input("Ask a question about your database… (e.g., 'top 10 customers by revenue')")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not database_url:
            st.error("Database connection not configured. Please provide DATABASE_URL in sidebar.")
        elif not api_key:
            st.error("LLM API key not configured. Set GEMINI_API_KEY or GROQ_API_KEY in environment.")
        else:
            try:
                db = PostgresDB(database_url)
                resp = answer_question(
                    provider=provider,
                    api_key=api_key,
                    model=model,
                    db=db,
                    question=prompt,
                    chat_history=st.session_state.messages,
                    statement_timeout_ms=int(statement_timeout_ms),
                    max_rows=int(max_rows),
                    sql_mode=sql_mode,
                    execute=False,
                    memory_user_turns=settings.memory_user_turns,
                    max_sql_statements=settings.max_sql_statements,
                )
                if resp.kind != "sql" or not resp.sql:
                    st.markdown(resp.answer)
                    st.session_state.messages.append({"role": "assistant", "content": resp.answer})
                else:
                    with st.expander("SQL", expanded=True):
                        st.code(resp.sql, language="sql")
                    stmts = resp.sql_statements or []
                    all_read = all(classify_statement(s) in ("select", "with") for s in stmts) if stmts else False
                    if all_read:
                        exec_resp = answer_question(
                            provider=provider,
                            api_key=api_key,
                            model=model,
                            db=db,
                            question=prompt,
                            chat_history=st.session_state.messages,
                            statement_timeout_ms=int(statement_timeout_ms),
                            max_rows=int(max_rows),
                            sql_mode=sql_mode,
                            execute=True,
                            sql_override=resp.sql,
                            memory_user_turns=settings.memory_user_turns,
                            max_sql_statements=settings.max_sql_statements,
                        )
                        st.markdown(exec_resp.answer)
                        results_payload = []
                        for r in exec_resp.results or []:
                            results_payload.append({"rows": r.rows, "meta": f"rowcount: {r.rowcount}"})
                            st.caption(f"rowcount: {r.rowcount}")
                            st.dataframe(r.rows, use_container_width=True)
                        st.session_state.messages.append(
                            {"role": "assistant", "content": exec_resp.answer, "sql": exec_resp.sql, "results": results_payload}
                        )
                    else:
                        if sql_mode == "read_only":
                            st.error("Write SQL generated but SQL mode is read_only. Switch SQL mode to write_full for CRUD.")
                            st.session_state.messages.append(
                                {
                                    "role": "assistant",
                                    "content": "Error: write SQL blocked by read_only mode. Switch SQL mode to write_full.",
                                    "sql": resp.sql,
                                }
                            )
                        else:
                            st.warning("This looks like a WRITE query. Review the SQL, then click Execute.")
                            st.session_state.pending = {"sql": resp.sql, "question": prompt}
                            if st.button("Execute SQL", type="primary"):
                                _run_pending(db)
            except (NL2SQLError, LLMError, DatabaseError) as e:
                st.error(str(e))
                st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})

if st.session_state.pending and database_url and api_key:
    with st.sidebar:
        st.subheader("Pending SQL")
        st.code(st.session_state.pending["sql"], language="sql")
