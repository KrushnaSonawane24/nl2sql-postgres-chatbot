from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass
from typing import Any, Literal

import sqlparse

from .db import PostgresDB, QueryResult
from .llm_client import LLMChatMessage, chat_completion
from .sql_safety import (
    SQLMode,
    UnsafeSQLError,
    apply_limit,
    classify_statement,
    validate_sql,
)


class NL2SQLError(RuntimeError):
    pass


@dataclass(frozen=True)
class NL2SQLResponse:
    kind: Literal["chat", "clarify", "sql"]
    sql: str
    sql_statements: list[str]
    results: list[QueryResult] | None
    answer: str


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_SQL_BLOCK = re.compile(r"```sql\s*([\s\S]*?)\s*```", re.IGNORECASE)


def _format_short_history(chat_history: list[dict[str, str]] | None, *, max_user_prompts: int = 5) -> str:
    if not chat_history:
        return ""

    pairs: list[tuple[str, str | None]] = []
    last_assistant: str | None = None
    for t in reversed(chat_history):
        role = (t.get("role") or "").strip().lower()
        content = (t.get("content") or "").strip()
        if not role or not content:
            continue
        if role == "assistant" and last_assistant is None:
            last_assistant = content
            continue
        if role == "user":
            pairs.append((content, last_assistant))
            last_assistant = None
            if len(pairs) >= max_user_prompts:
                break

    pairs.reverse()
    lines: list[str] = []
    for u, a in pairs:
        lines.append(f"USER: {u}")
        if a:
            lines.append(f"ASSISTANT: {a}")
    return "\n".join(lines).strip()


def _schema_identifiers(schema_text: str) -> list[str]:
    out: list[str] = []
    for line in (schema_text or "").splitlines():
        s = line.strip()
        if s.startswith("TABLE "):
            out.append(s.replace("TABLE ", "").strip())
        elif s.startswith("- ") or s.startswith("  - "):
            m = re.search(r"-\s*([A-Za-z_][A-Za-z_0-9]*)\s*\(", s)
            if m:
                out.append(m.group(1))
    return sorted(set(out))


def _parse_schema(schema_text: str) -> tuple[set[str], dict[str, set[str]], dict[str, str]]:
    tables: set[str] = set()
    table_cols: dict[str, set[str]] = {}
    basename_map: dict[str, str] = {}
    basename_counts: dict[str, int] = {}

    current_table: str | None = None
    for line in (schema_text or "").splitlines():
        s = line.strip()
        if s.startswith("TABLE "):
            current_table = s.replace("TABLE ", "").strip()
            if current_table:
                tables.add(current_table)
                table_cols.setdefault(current_table, set())
                base = current_table.split(".")[-1]
                basename_counts[base] = basename_counts.get(base, 0) + 1
        elif current_table and (s.startswith("- ") or s.startswith("  - ")):
            m = re.search(r"-\s*([A-Za-z_][A-Za-z_0-9]*)\s*\(", s)
            if m:
                table_cols.setdefault(current_table, set()).add(m.group(1))

    for t in tables:
        base = t.split(".")[-1]
        if basename_counts.get(base) == 1:
            basename_map[base] = t

    return tables, table_cols, basename_map


_SQL_STRING = re.compile(r"(?:E)?'(?:[^']|'')*'")


def _mask_sql_for_scan(sql: str) -> str:
    s = sqlparse.format(sql or "", strip_comments=True)
    s = _SQL_STRING.sub("''", s)
    return s


_AFTER_FROM_JOIN = re.compile(r"\b(from|join)\s+([A-Za-z_][A-Za-z_0-9\.]*)", re.IGNORECASE)
_AFTER_TABLE_ALIAS = re.compile(r"^\s+(?:as\s+)?([A-Za-z_][A-Za-z_0-9]*)\b", re.IGNORECASE)
_ALIAS_COL = re.compile(r"\b([A-Za-z_][A-Za-z_0-9]*)\.([A-Za-z_][A-Za-z_0-9]*)\b")


def _is_system_relation(name: str) -> bool:
    n = (name or "").strip().strip('"').lower()
    return n.startswith("information_schema.") or n.startswith("pg_catalog.")


def _resolve_table_name(name: str, tables: set[str], basename_map: dict[str, str]) -> str | None:
    raw = (name or "").strip().strip('"')
    if not raw:
        return None
    if _is_system_relation(raw):
        return raw
    if raw in tables:
        return raw
    if raw.count(".") == 1:
        if raw in tables:
            return raw
    if "." not in raw and raw in basename_map:
        return basename_map[raw]
    return None


def _identifier_suggestions(name: str, candidates: list[str], *, n: int = 3) -> list[str]:
    return difflib.get_close_matches((name or "").strip(), candidates, n=n, cutoff=0.72)


def _validate_schema_usage(sql: str, schema_text: str) -> str | None:
    tables, table_cols, basename_map = _parse_schema(schema_text)
    masked = _mask_sql_for_scan(sql)

    reserved = {
        "on",
        "using",
        "where",
        "join",
        "left",
        "right",
        "inner",
        "full",
        "cross",
        "group",
        "order",
        "limit",
        "union",
        "intersect",
        "except",
        "having",
        "window",
    }

    alias_map: dict[str, str] = {}
    for m in _AFTER_FROM_JOIN.finditer(masked):
        table_token = m.group(2)
        resolved = _resolve_table_name(table_token, tables, basename_map)
        if resolved is None:
            options = sorted(tables)
            sugg = _identifier_suggestions(table_token, options)
            if sugg:
                return f"I couldn't find table '{table_token}'. Did you mean: {', '.join(sugg)}?"
            return f"I couldn't find table '{table_token}'. Please use an exact table name from the schema."

        tail = masked[m.end() :]
        am = _AFTER_TABLE_ALIAS.match(tail)
        if am:
            alias = am.group(1)
            if alias and alias.lower() not in reserved:
                alias_map[alias] = resolved

        base = resolved.split(".")[-1]
        alias_map.setdefault(base, resolved)

    for m in _ALIAS_COL.finditer(masked):
        alias = m.group(1)
        col = m.group(2)
        table = alias_map.get(alias)
        if not table:
            continue
        if _is_system_relation(table):
            continue
        cols = table_cols.get(table) or set()
        if col not in cols:
            sugg = _identifier_suggestions(col, sorted(cols))
            if sugg:
                return f"Column '{col}' does not exist on '{table}'. Did you mean: {', '.join(sugg)}?"
            return f"Column '{col}' does not exist on '{table}'. Please use an exact column name from the schema."

    return None



def _spelling_suggestions(question: str, identifiers: list[str], *, limit: int = 10) -> str:
    words = re.findall(r"[A-Za-z_][A-Za-z_0-9]{2,}", question or "")
    suggestions: list[str] = []
    for w in sorted(set(words), key=len, reverse=True)[:40]:
        matches = difflib.get_close_matches(w, identifiers, n=2, cutoff=0.84)
        for m in matches:
            if m.lower() != w.lower():
                suggestions.append(f"{w} → {m}")
    if not suggestions:
        return ""
    return "\n".join(suggestions[:limit])


def _schema_column_names(schema_text: str) -> list[str]:
    cols: list[str] = []
    for line in (schema_text or "").splitlines():
        s = line.strip()
        if s.startswith("- ") or s.startswith("  - "):
            m = re.search(r"-\s*([A-Za-z_][A-Za-z_0-9]*)\s*\(", s)
            if m:
                cols.append(m.group(1))
    return sorted(set(cols))


def _gender_columns(schema_text: str) -> list[str]:
    cols = _schema_column_names(schema_text)
    out: list[str] = []
    for c in cols:
        lc = c.lower()
        if lc in ("gender", "sex") or "gndr" in lc or "gender" in lc or "sex" in lc:
            out.append(c)
    return out


def _gender_intent(question: str) -> str | None:
    q = (question or "").lower()
    male_terms = [
        "male",
        "males",
        "m",
        "M",
        "man",
        "men",
        "boy",
        ]
    female_terms = [
        "female",
        "females",
        "f",
        "F",
        "woman",
        "women",
        "girl",
            ]
    if any(re.search(rf"\b{re.escape(t)}\b", q) for t in male_terms):
        return "male"
    if any(re.search(rf"\b{re.escape(t)}\b", q) for t in female_terms):
        return "female"
    return None


def _value_normalization_hints(schema_text: str, question: str) -> str:
    lines: list[str] = []
    gender = _gender_intent(question)
    gender_cols = _gender_columns(schema_text)
    if gender and gender_cols:
        if gender == "male":
            variants = ["male", "m", "man", "men", "boy"]
        else:
            variants = ["female", "f", "woman", "women", "girl"]
        cols = ", ".join(gender_cols[:6])
        vals = ", ".join([f"'{v}'" for v in variants[:10]])
        lines.append(f"GENDER_HINT: user wants {gender}. Candidate columns: {cols}.")
        lines.append(f"Use LOWER(TRIM(col)) IN ({vals}).")
    return "\n".join(lines).strip()


def _extract_json(text: str) -> dict[str, Any] | None:
    m = _JSON_BLOCK.search(text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _extract_sql(text: str) -> str:
    m = _SQL_BLOCK.search(text or "")
    if m:
        return (m.group(1) or "").strip()
    data = _extract_json(text)
    if isinstance(data, dict) and isinstance(data.get("sql"), str):
        return data["sql"].strip()
    return (text or "").strip()


def _extract_plan(text: str) -> dict[str, Any] | None:
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None
    kind = data.get("kind")
    if kind not in ("chat", "clarify", "sql"):
        return None
    return data


def generate_plan(
    *,
    provider: str,
    api_key: str,
    model: str,
    schema_text: str,
    question: str,
    chat_history: list[dict[str, str]] | None = None,
    sql_mode: SQLMode = "read_only",
    memory_user_turns: int = 5,
    max_sql_statements: int = 1,
) -> dict[str, Any]:
    history_text = _format_short_history(chat_history, max_user_prompts=max(1, int(memory_user_turns)))
    max_sql_statements = max(1, int(max_sql_statements))

    mode_rules = (
        "SQL mode: READ ONLY.\n"
        f"- Output up to {max_sql_statements} statement(s), separated by semicolons.\n"
        "- Allowed: SELECT or WITH.\n"
        "- Forbidden: any write/delete/ddl operations.\n"
    )
    if sql_mode == "write_no_delete":
        mode_rules = (
            "SQL mode: WRITE (NO DELETE).\n"
            f"- Output up to {max_sql_statements} statement(s), separated by semicolons.\n"
            "- Allowed: SELECT/WITH, INSERT, UPDATE, and CREATE TABLE/VIEW/INDEX.\n"
            "- Forbidden: DELETE, DROP, ALTER, TRUNCATE, GRANT/REVOKE, COPY, VACUUM, functions/procedures.\n"
            "- Prefer safe changes: use WHERE clauses for UPDATE; use RETURNING * when helpful.\n"
        )
    if sql_mode == "write_full":
        mode_rules = (
            "SQL mode: WRITE (FULL CRUD).\n"
            f"- Output up to {max_sql_statements} statement(s), separated by semicolons.\n"
            "- Allowed: SELECT/WITH, INSERT, UPDATE, DELETE, and CREATE TABLE/VIEW/INDEX.\n"
            "- Forbidden: DROP, ALTER, TRUNCATE, GRANT/REVOKE, COPY, VACUUM, functions/procedures.\n"
            "- Prefer safe changes: use WHERE clauses for UPDATE/DELETE; use RETURNING * when helpful.\n"
        )

    system = (
        "You are a friendly English-speaking chatbot for a PostgreSQL database.\n"
        "You must ALWAYS return valid JSON.\n"
        "Output schema:\n"
        "- kind: one of \"chat\" | \"clarify\" | \"sql\"\n"
        "- message: string (friendly response or clarification question)\n"
        "- sql: string (only when kind=\"sql\", otherwise empty)\n"
        "\n"
        "Decide what to do:\n"
        "- If the user is greeting/small talk (e.g., hi/hello/hey/kaise ho), respond normally with kind=\"chat\".\n"
        "- If the user asks to run SQL on the DB, use kind=\"sql\" and put up to the allowed number of PostgreSQL statements in sql.\n"
        "- If the user asks INSERT/UPDATE/DELETE but provides incomplete info (missing table, missing values, missing WHERE), ask follow-up with kind=\"clarify\" and sql=\"\".\n"
        "- If the user refers to a wrong table/column name, respond with kind=\"clarify\" and ask what they meant.\n"
        "- Always write message in English, even if the user writes in Hindi/Hinglish.\n"
        "\n"
        "SQL rules:\n"
        f"{mode_rules}"
        "General rules:\n"
        "- Understand Hindi/Hinglish and typos, but respond in English.\n"
        "- Use only tables/columns that exist in the provided schema and use the exact names.\n"
        "- If user has typos or spelling mistakes, infer intended table/column names from schema.\n"
        "- Prefer explicit table qualifiers for ambiguous columns.\n"
        "- For text filters, use case/space-tolerant matching (LOWER(TRIM(col))).\n"
        "- Arithmetic is allowed: +, -, *, /, %, SUM/AVG/MIN/MAX, COUNT, CASE, COALESCE.\n"
        "- Before any arithmetic or SUM/AVG, ensure operands are numeric. If a value column is TEXT/VARCHAR, cast it (e.g., NULLIF(regexp_replace(col, '[^0-9\\.-]', '', 'g'), '')::numeric).\n"
        "- For division, avoid divide-by-zero using NULLIF(denominator, 0).\n"
        "- If the user asks for duplicate values, use GROUP BY ... HAVING COUNT(*) > 1 (and show count).\n"
        "- If the user asks to list all tables/columns, query information_schema (tables/columns) instead of guessing names.\n"
        "- Never use SQL Server syntax like TOP; in PostgreSQL use LIMIT.\n"
        "- Avoid UNION for simple filters; prefer a single SELECT with WHERE ... IN (...) or OR.\n"
        "- If you must use UNION/UNION ALL and need per-branch LIMIT, wrap each branch in parentheses: (SELECT ... LIMIT 1) UNION ALL (SELECT ... LIMIT 1).\n"
        "- If the user asks to insert/update/delete rows and SQL mode allows it, output the corresponding INSERT/UPDATE/DELETE.\n"
        "- For INSERT/UPDATE/DELETE, prefer RETURNING * so the app can show affected rows.\n"
        "- Complex queries are allowed: joins, CTEs, group by, set operations.\n"
        "- Keep it efficient; add LIMIT for list queries.\n"
    )

    identifiers = _schema_identifiers(schema_text)
    typo_hints = _spelling_suggestions(question, identifiers)
    value_hints = _value_normalization_hints(schema_text, question)

    user = (
        f"SCHEMA:\n{schema_text}\n\n"
        f"{('POSSIBLE TYPO FIXES:\n' + typo_hints + '\n\n') if typo_hints else ''}"
        f"{('VALUE NORMALIZATION HINTS:\n' + value_hints + '\n\n') if value_hints else ''}"
        f"{'CHAT HISTORY:\n' + history_text + '\n\n' if history_text else ''}"
        f"QUESTION:\n{question}\n"
    )

    content = chat_completion(
        provider=provider,  # type: ignore[arg-type]
        api_key=api_key,
        model=model,
        fallback_models=["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
        messages=[LLMChatMessage(role="system", content=system), LLMChatMessage(role="user", content=user)],
        temperature=0.2,
        max_tokens=750,
        timeout_s=45,
    )
    plan = _extract_plan(content)
    if plan is None:
        data = _extract_json(content)
        if data is None:
            raise NL2SQLError("Model did not return JSON")
        raise NL2SQLError("Model JSON missing required fields")

    if not isinstance(plan.get("message"), str):
        plan["message"] = ""
    if not isinstance(plan.get("sql"), str):
        plan["sql"] = ""
    return plan


def answer_question(
    *,
    provider: str,
    api_key: str,
    model: str,
    db: PostgresDB,
    question: str,
    chat_history: list[dict[str, str]] | None = None,
    statement_timeout_ms: int = 8000,
    max_rows: int = 200,
    sql_mode: SQLMode = "read_only",
    execute: bool = True,
    sql_override: str | None = None,
    memory_user_turns: int = 5,
    max_sql_statements: int = 1,
) -> NL2SQLResponse:
    schema_text = db.fetch_schema()
    raw_sql = (sql_override or "").strip()
    kind: Literal["chat", "clarify", "sql"] = "sql"
    message = ""
    if not raw_sql:
        plan = generate_plan(
            provider=provider,
            api_key=api_key,
            model=model,
            schema_text=schema_text,
            question=question,
            chat_history=chat_history,
            sql_mode=sql_mode,
            memory_user_turns=memory_user_turns,
            max_sql_statements=max_sql_statements,
        )
        kind = plan.get("kind", "sql")
        message = (plan.get("message") or "").strip() if isinstance(plan.get("message"), str) else ""
        raw_sql = (plan.get("sql") or "").strip() if isinstance(plan.get("sql"), str) else ""

        if kind in ("chat", "clarify"):
            return NL2SQLResponse(kind=kind, sql="", sql_statements=[], results=None, answer=message or "OK.")
        if not raw_sql:
            return NL2SQLResponse(kind="clarify", sql="", sql_statements=[], results=None, answer=message or "I need a bit more detail. Please clarify.")

    try:
        statements = validate_sql(raw_sql, sql_mode=sql_mode, max_statements=max(1, int(max_sql_statements)))
        normalized_statements: list[str] = []
        for s in statements:
            schema_issue = _validate_schema_usage(s, schema_text)
            if schema_issue:
                return NL2SQLResponse(kind="clarify", sql="", sql_statements=[], results=None, answer=schema_issue)
            stmt = classify_statement(s)
            if sql_mode == "read_only" and stmt in ("select", "with"):
                s = apply_limit(s, max_rows=max_rows)
            if sql_mode != "read_only" and stmt == "select":
                s = apply_limit(s, max_rows=max_rows)
            normalized_statements.append(s)
    except UnsafeSQLError as e:
        msg = str(e)
        if not execute and sql_override is None:
            if "must include WHERE" in msg:
                return NL2SQLResponse(
                    kind="clarify",
                    sql="",
                    sql_statements=[],
                    results=None,
                    answer="For UPDATE/DELETE, a WHERE condition is required. Which record should be changed (e.g., id, name, city)?",
                )
        raise NL2SQLError(msg) from e

    results: list[QueryResult] | None = None
    if execute:
        if len(normalized_statements) == 1:
            results = [db.execute_sql(normalized_statements[0], statement_timeout_ms=statement_timeout_ms)]
        else:
            results = db.execute_sql_batch(normalized_statements, statement_timeout_ms=statement_timeout_ms)

    stmt = classify_statement(normalized_statements[-1])
    if not execute:
        answer = message or "Here is the SQL I generated. Review it, then execute if needed."
    elif stmt in ("select", "with"):
        last_rows = results[-1].rows if results else []
        answer = message or f"Returned {len(last_rows)} row(s)."
    else:
        last = results[-1] if results else None
        rc = last.rowcount if last is not None else 0
        returned = len(last.rows) if last is not None else 0
        answer = message or f"Executed {stmt.upper()} (rowcount: {rc})."
        if returned:
            answer = f"{answer} Returned {returned} row(s)."

    full_sql = ";\n\n".join(normalized_statements)
    if full_sql:
        full_sql = f"{full_sql};"
    return NL2SQLResponse(kind="sql", sql=full_sql, sql_statements=normalized_statements, results=results, answer=answer)
