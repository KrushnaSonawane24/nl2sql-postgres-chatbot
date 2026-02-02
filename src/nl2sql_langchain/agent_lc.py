"""
LangChain-based NL2SQL Agent with Memory Support
This module replaces the custom llm_client.py with LangChain's built-in LLM integrations
"""
from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from nl2sql.db import PostgresDB
from nl2sql.sql_safety import SQLMode, validate_sql, classify_statement, apply_limit, UnsafeSQLError
from dataclasses import dataclass


class NL2SQLError(RuntimeError):
    pass


@dataclass(frozen=True)
class NL2SQLResponse:
    kind: Literal["chat", "clarify", "sql"]
    sql: str
    sql_statements: list[str]
    results: list | None
    answer: str


class LangChainAgent:
    """
    LangChain-based NL2SQL Agent with Built-in Memory
    """
    
    def __init__(
        self,
        provider: Literal["gemini", "groq"],
        api_key: str,
        model: str,
        sql_mode: SQLMode = "read_only",
        max_sql_statements: int = 4,
        temperature: float = 0.2,
    ):
        self.provider = provider
        self.sql_mode = sql_mode
        self.max_sql_statements = max_sql_statements
        
        # Initialize LLM based on provider
        if provider == "gemini":
            self.llm = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=api_key,
                temperature=temperature,
                max_output_tokens=1000,
            )
        elif provider == "groq":
            self.llm = ChatGroq(
                model=model,
                groq_api_key=api_key,
                temperature=temperature,
                max_tokens=1000,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        # Memory: Store conversation history
        self.memory: list[dict[str, str]] = []
        
        # Create prompt template with memory placeholder
        self.prompt = self._create_prompt_template()
        
        # Create chain with JSON output parser
        self.json_parser = JsonOutputParser()
        self.chain = self.prompt | self.llm | self.json_parser
    
    def _create_prompt_template(self) -> ChatPromptTemplate:
        """Create LangChain prompt with memory support"""
        
        system_instructions = """You are a PostgreSQL query assistant that converts natural language to SQL.
You must ALWAYS return valid JSON.
Output schema:
- kind: one of "chat" | "clarify" | "sql"
- message: string (concise response or clarification question)
- sql: string (only when kind="sql", otherwise empty)

Decision logic:
- If the user provides a greeting (e.g., hi/hello), acknowledge briefly with kind="chat".
- If the user requests database query, output kind="sql" with valid PostgreSQL statement(s).
- If the user requests INSERT/UPDATE/DELETE but provides incomplete info, request clarification with kind="clarify".
- If the user refers to non-existent tables/columns, respond with kind="clarify" and suggest corrections.
- Always respond in English, regardless of input language.

SQL rules:
{mode_rules}

General rules:
- Accept input in English, Hindi, or Hinglish. Respond in English.
- Use only tables/columns from the provided schema with exact names.
- Infer intended table/column names from typos using schema context.
- Use explicit table qualifiers for potentially ambiguous columns.
- For text filters, use case-insensitive matching: LOWER(TRIM(col)).
- Supported operations: +, -, *, /, %, SUM/AVG/MIN/MAX, COUNT, CASE, COALESCE.
- Ensure numeric types before arithmetic operations.
- Prevent division by zero: use NULLIF(denominator, 0).
- Use PostgreSQL syntax: LIMIT (not SQL Server's TOP).
- For INSERT/UPDATE/DELETE: include RETURNING * to show affected rows.
- Add LIMIT to list queries for efficiency."""
        
        return ChatPromptTemplate.from_messages([
            ("system", system_instructions),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "SCHEMA:\n{schema}\n\nQUESTION:\n{question}"),
        ])
    
    def _get_mode_rules(self) -> str:
        """Get SQL mode rules based on current mode"""
        if self.sql_mode == "read_only":
            return f"""SQL mode: READ ONLY.
- Output up to {self.max_sql_statements} statement(s), separated by semicolons.
- Allowed: SELECT or WITH.
- Forbidden: any write/delete/ddl operations."""
        elif self.sql_mode == "write_no_delete":
            return f"""SQL mode: WRITE (NO DELETE).
- Output up to {self.max_sql_statements} statement(s), separated by semicolons.
- Allowed: SELECT/WITH, INSERT, UPDATE, and CREATE TABLE/VIEW/INDEX.
- Forbidden: DELETE, DROP, ALTER, TRUNCATE, GRANT/REVOKE, COPY, VACUUM, functions/procedures.
- Prefer safe changes: use WHERE clauses for UPDATE; use RETURNING * when helpful."""
        else:  # write_full
            return f"""SQL mode: WRITE (FULL CRUD).
- Output up to {self.max_sql_statements} statement(s), separated by semicolons.
- Allowed: SELECT/WITH, INSERT, UPDATE, DELETE, and CREATE TABLE/VIEW/INDEX.
- Forbidden: DROP, ALTER, TRUNCATE, GRANT/REVOKE, COPY, VACUUM, functions/procedures.
- Prefer safe changes: use WHERE clauses for UPDATE/DELETE; use RETURNING * when helpful."""
    
    def _format_chat_history(self) -> list:
        """Convert memory to LangChain message format"""
        messages = []
        for msg in self.memory[-10:]:  # Last 10 messages
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        return messages
    
    def add_to_memory(self, role: str, content: str):
        """Add message to conversation memory"""
        self.memory.append({"role": role, "content": content})
    
    def answer_question(
        self,
        db: PostgresDB,
        question: str,
        execute: bool = True,
        sql_override: str | None = None,
        statement_timeout_ms: int = 8000,
        max_rows: int = 200,
    ) -> NL2SQLResponse:
        """
        Main entry point: Answer user question using LangChain
        """
        # Fetch database schema
        schema_text = db.fetch_schema()
        
        # If SQL override provided, skip LLM
        raw_sql = (sql_override or "").strip()
        kind: Literal["chat", "clarify", "sql"] = "sql"
        message = ""
        
        if not raw_sql:
            # Prepare inputs for LangChain chain
            mode_rules = self._get_mode_rules()
            chat_history = self._format_chat_history()
            
            try:
                # Invoke LangChain chain with memory
                result = self.chain.invoke({
                    "schema": schema_text,
                    "question": question,
                    "chat_history": chat_history,
                    "mode_rules": mode_rules,
                    "max_statements": self.max_sql_statements,
                })
                
                kind = result.get("kind", "sql")
                message = result.get("message", "").strip()
                raw_sql = result.get("sql", "").strip()
                
            except Exception as e:
                raise NL2SQLError(f"LLM error: {e}") from e
            
            # Handle non-SQL responses
            if kind in ("chat", "clarify"):
                return NL2SQLResponse(
                    kind=kind,
                    sql="",
                    sql_statements=[],
                    results=None,
                    answer=message or "Acknowledged."
                )
            
            if not raw_sql:
                return NL2SQLResponse(
                    kind="clarify",
                    sql="",
                    sql_statements=[],
                    results=None,
                    answer=message or "Please provide additional details to proceed."
                )
        
        # Validate SQL
        try:
            statements = validate_sql(
                raw_sql,
                sql_mode=self.sql_mode,
                max_statements=self.max_sql_statements
            )
            
            normalized_statements = []
            for s in statements:
                stmt = classify_statement(s)
                if self.sql_mode == "read_only" and stmt in ("select", "with"):
                    s = apply_limit(s, max_rows=max_rows)
                if self.sql_mode != "read_only" and stmt == "select":
                    s = apply_limit(s, max_rows=max_rows)
                normalized_statements.append(s)
                
        except UnsafeSQLError as e:
            raise NL2SQLError(str(e)) from e
        
        # Execute SQL if requested
        results = None
        if execute:
            if len(normalized_statements) == 1:
                results = [db.execute_sql(
                    normalized_statements[0],
                    statement_timeout_ms=statement_timeout_ms
                )]
            else:
                results = db.execute_sql_batch(
                    normalized_statements,
                    statement_timeout_ms=statement_timeout_ms
                )
        
        # Format answer
        stmt = classify_statement(normalized_statements[-1])
        if not execute:
            answer = message or "SQL generated. Review before execution."
        elif stmt in ("select", "with"):
            last_rows = results[-1].rows if results else []
            answer = message or f"Query returned {len(last_rows)} row(s)."
        else:
            last = results[-1] if results else None
            rc = last.rowcount if last is not None else 0
            returned = len(last.rows) if last is not None else 0
            answer = message or f"{stmt.upper()} executed (affected rows: {rc})."
            if returned:
                answer = f"{answer} Returned {returned} row(s)."
        
        full_sql = ";\n\n".join(normalized_statements)
        if full_sql:
            full_sql = f"{full_sql};"
        
        return NL2SQLResponse(
            kind="sql",
            sql=full_sql,
            sql_statements=normalized_statements,
            results=results,
            answer=answer
        )
