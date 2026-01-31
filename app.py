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

st.set_page_config(page_title="NL → SQL (PostgreSQL)", layout="wide")
st.title("Natural Language → SQL Chatbot (PostgreSQL)")

settings = load_settings()

with st.sidebar:
    st.subheader("Connection")
    database_url = st.text_input("DATABASE_URL", value=settings.database_url, type="password")

    st.subheader("LLM")
    provider = settings.provider
    api_key = settings.api_key
    model = settings.model
    st.caption(f"Using: {provider} ({model}). Set GEMINI_API_KEY or GROQ_API_KEY in .env.")

    st.subheader("Safety")
    _sql_mode_options = ["read_only", "write_no_delete", "write_full"]
    _default_sql_mode = st.session_state.get("sql_mode") or "write_full"
    if _default_sql_mode not in _sql_mode_options:
        _default_sql_mode = "write_full"
    sql_mode: SQLMode = st.selectbox(
        "SQL mode",
        options=_sql_mode_options,
        index=_sql_mode_options.index(_default_sql_mode),
        key="sql_mode",
    )
    statement_timeout_ms = st.number_input(
        "Statement timeout (ms)", min_value=1000, max_value=60000, value=settings.statement_timeout_ms, step=500
    )
    max_rows = st.number_input("Max rows", min_value=1, max_value=2000, value=settings.max_rows, step=10)
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
            with st.expander("SQL", expanded=False):
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
            st.error("Missing DATABASE_URL")
        elif not api_key:
            st.error("Missing API key (set GEMINI_API_KEY or GROQ_API_KEY in .env)")
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
