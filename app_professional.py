from __future__ import annotations

import os
import sys

import streamlit as st
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nl2sql.agent import NL2SQLError, answer_question
from nl2sql.config import load_settings
from nl2sql.db import DatabaseError, PostgresDB
from nl2sql.llm_client import LLMError
from nl2sql.sql_safety import SQLMode, classify_statement

load_dotenv()

# Professional page configuration
st.set_page_config(
    page_title="NL2SQL - PostgreSQL Query Assistant",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Minimal, professional CSS
st.markdown("""
<style>
    /* Professional font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    
    .stApp {
        font-family: 'Inter', sans-serif;
    }
    
    /* Clean header */
    h1 {
        color: #1f2937;
        font-weight: 600;
        font-size: 1.8rem !important;
        margin-bottom: 0.3rem;
        border-bottom: 2px solid #e5e7eb;
        padding-bottom: 0.5rem;
    }
    
    /* SQL code blocks - make them prominent */
    .stCodeBlock {
        border-left: 3px solid #3b82f6;
        background-color: #f8fafc;
        border-radius: 4px;
    }
    
    /* Clean dataframes */
    .stDataFrame {
        border: 1px solid #e5e7eb;
        border-radius: 4px;
    }
    
    /* Professional buttons */
    .stButton button {
        background-color: #3b82f6;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 0.5rem 1.5rem;
        font-weight: 500;
    }
    
    .stButton button:hover {
        background-color: #2563eb;
    }
    
    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background-color: #f9fafb;
        border-right: 1px solid #e5e7eb;
    }
    
    /* Info boxes */
    .stInfo {
        background-color: #eff6ff;
        border-left: 3px solid #3b82f6;
    }
    
    .stSuccess {
        background-color: #f0fdf4;
        border-left: 3px solid #10b981;
    }
    
    .stWarning {
        background-color: #fffbeb;
        border-left: 3px solid #f59e0b;
    }
    
    .stError {
        background-color: #fef2f2;
        border-left: 3px solid #ef4444;
    }
    
    /* Chat messages - minimal */
    .stChatMessage {
        border-left: 3px solid #e5e7eb;
        padding: 0.8rem;
        margin: 0.5rem 0;
    }
    
    /* Remove excessive padding */
    .main .block-container {
        max-width: 1200px;
        padding-top: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# Clean header
st.title("Natural Language to SQL Query Assistant")
st.caption("PostgreSQL Database Interaction Tool")

settings = load_settings()

# Professional sidebar
with st.sidebar:
    st.subheader("Configuration")
    
    st.markdown("**Database Connection**")
    database_url = st.text_input(
        "PostgreSQL URL", 
        value=settings.database_url, 
        type="password",
        help="Connection string format: postgresql://user:pass@host:port/db"
    )

    st.markdown("**LLM Configuration**")
    provider = settings.provider
    api_key = settings.api_key
    model = settings.model
    
    if api_key:
        st.success(f"Connected: {provider.upper()}")
        st.caption(f"Model: {model}")
    else:
        st.warning("No API key configured")

    st.divider()
    
    st.markdown("**Query Safety Settings**")
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
        "Query Timeout (ms)", 
        min_value=1000, 
        max_value=60000, 
        value=settings.statement_timeout_ms, 
        step=1000
    )
    
    max_rows = st.number_input(
        "Result Limit", 
        min_value=1, 
        max_value=2000, 
        value=settings.max_rows, 
        step=50
    )
    
    st.divider()
    st.caption(f"Memory: {settings.memory_user_turns} user turns")
    st.caption(f"Max statements: {settings.max_sql_statements}")

# Session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending" not in st.session_state:
    st.session_state.pending = None
if "sql_mode" not in st.session_state:
    st.session_state.sql_mode = "write_full"

# Display query history
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        
        # Show SQL prominently
        if m.get("sql"):
            st.markdown("**Generated SQL:**")
            st.code(m["sql"], language="sql")
        
        # Show results in structured format
        if m.get("results"):
            for i, r in enumerate(m["results"], start=1):
                if len(m["results"]) > 1:
                    st.markdown(f"**Result Set {i}:**")
                if r.get("meta"):
                    st.caption(r["meta"])
                if r.get("rows") is not None:
                    st.dataframe(r["rows"], use_container_width=True)


def _run_pending(db: PostgresDB):
    """Execute pending write query after user confirmation"""
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
            results_payload.append({"rows": r.rows, "meta": f"Affected rows: {r.rowcount}"})
        
        st.session_state.messages.append({
            "role": "assistant", 
            "content": resp.answer, 
            "sql": resp.sql, 
            "results": results_payload
        })
        st.session_state.pending = None
        st.success("Query executed successfully")
        st.rerun()
        
    except (NL2SQLError, LLMError, DatabaseError) as e:
        st.session_state.messages.append({
            "role": "assistant", 
            "content": f"Execution error: {e}"
        })
        st.session_state.pending = None
        st.rerun()


# Query input
prompt = st.chat_input("Enter your database query in natural language...")

if prompt:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # Validation checks
        if not database_url:
            st.error("Database connection not configured. Please provide DATABASE_URL in sidebar.")
            st.stop()
        
        if not api_key:
            st.error("LLM API key not configured. Set GEMINI_API_KEY or GROQ_API_KEY in environment.")
            st.stop()

        try:
            db = PostgresDB(database_url)
            
            # Generate SQL (without execution)
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
            
            # Handle non-SQL responses (clarifications, chat)
            if resp.kind != "sql" or not resp.sql:
                st.markdown(resp.answer)
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": resp.answer
                })
            else:
                # Show generated SQL
                st.markdown("**Generated SQL:**")
                st.code(resp.sql, language="sql")
                
                # Determine if query can be auto-executed
                stmts = resp.sql_statements or []
                all_read = all(
                    classify_statement(s) in ("select", "with") 
                    for s in stmts
                ) if stmts else False
                
                if all_read:
                    # Auto-execute read queries
                    st.info("Executing read query...")
                    
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
                    
                    # Display results
                    results_payload = []
                    for r in exec_resp.results or []:
                        results_payload.append({
                            "rows": r.rows, 
                            "meta": f"Rows returned: {r.rowcount}"
                        })
                        st.caption(f"Rows returned: {r.rowcount}")
                        st.dataframe(r.rows, use_container_width=True)
                    
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": exec_resp.answer, 
                        "sql": exec_resp.sql, 
                        "results": results_payload
                    })
                else:
                    # Write query - require confirmation
                    if sql_mode == "read_only":
                        st.error(
                            "Write operation detected but system is in read-only mode. "
                            "Change operation mode in sidebar to allow modifications."
                        )
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "Write operation blocked by read-only mode.",
                            "sql": resp.sql,
                        })
                    else:
                        st.warning(
                            "This query will modify data. "
                            "Review the SQL statement above and confirm execution."
                        )
                        st.session_state.pending = {"sql": resp.sql, "question": prompt}
                        
                        if st.button("Execute Query", type="primary"):
                            _run_pending(db)
                            
        except (NL2SQLError, LLMError, DatabaseError) as e:
            st.error(f"Error: {str(e)}")
            st.session_state.messages.append({
                "role": "assistant", 
                "content": f"Error: {e}"
            })

# Show pending query in sidebar
if st.session_state.pending and database_url and api_key:
    with st.sidebar:
        st.divider()
        st.warning("**Pending Execution**")
        st.code(st.session_state.pending["sql"], language="sql")
        st.caption("Return to chat to execute")
