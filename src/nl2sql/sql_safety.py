from __future__ import annotations

import re
from typing import Literal

import sqlparse


class UnsafeSQLError(ValueError):
    pass


SQLMode = Literal["read_only", "write_no_delete", "write_full"]

_FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|vacuum|analyze|"
    r"execute|prepare|deallocate|call|do|refresh|cluster|reindex|comment|security|"
    r"set\s+role|set\s+session|set\s+transaction|listen|notify|load"
    r")\b",
    re.IGNORECASE,
)

_FORBIDDEN_WRITE_NO_DELETE = re.compile(
    r"\b("
    r"delete|drop|alter|truncate|grant|revoke|copy|vacuum|analyze|"
    r"execute|prepare|deallocate|call|do|refresh|cluster|reindex|comment|security|"
    r"set\s+role|set\s+session|set\s+transaction|listen|notify|load"
    r")\b",
    re.IGNORECASE,
)

_FORBIDDEN_WRITE_FULL = re.compile(
    r"\b("
    r"drop|alter|truncate|grant|revoke|copy|vacuum|analyze|"
    r"execute|prepare|deallocate|call|do|refresh|cluster|reindex|comment|security|"
    r"set\s+role|set\s+session|set\s+transaction|listen|notify|load"
    r")\b",
    re.IGNORECASE,
)

_CREATE_ALLOWED = re.compile(r"^\s*create\s+(table|view|index)\b", re.IGNORECASE)

_DOLLAR_QUOTED = re.compile(
    r"(\$\$)[\s\S]*?\1|(\$[A-Za-z_][A-Za-z_0-9]*\$)[\s\S]*?\2",
    re.MULTILINE,
)
_SINGLE_QUOTED = re.compile(r"(?:E)?'(?:[^']|'')*'")
_DOUBLE_QUOTED = re.compile(r'"(?:[^"]|"")*"')
_SELECT_TOP = re.compile(r"^\s*select\s+(distinct\s+)?top\s*\(?\s*(\d+)\s*\)?\s+", re.IGNORECASE)
_SET_OP = re.compile(r"\b(union(\s+all)?|intersect|except)\b", re.IGNORECASE)
_LIMIT_BEFORE_SET_OP = re.compile(r"\blimit\s+\d+\s+(?=union\b|intersect\b|except\b)", re.IGNORECASE)


def _single_statement(sql: str) -> str:
    parsed = [s for s in sqlparse.parse(sql) if s and s.value.strip()]
    if len(parsed) != 1:
        raise UnsafeSQLError("Only one SQL statement is allowed")
    return parsed[0].value.strip()


def _split_statements(sql: str, *, max_statements: int) -> list[str]:
    parsed = [s for s in sqlparse.parse(sql) if s and s.value.strip()]
    if not parsed:
        raise UnsafeSQLError("Empty SQL")
    if len(parsed) > max_statements:
        raise UnsafeSQLError(f"Too many SQL statements (max {max_statements})")
    return [s.value.strip().rstrip(";").strip() for s in parsed]


def _mask_literals_and_comments(sql: str) -> str:
    masked = sqlparse.format(sql, strip_comments=True)
    masked = _DOLLAR_QUOTED.sub("''", masked)
    masked = _SINGLE_QUOTED.sub("''", masked)
    masked = _DOUBLE_QUOTED.sub('""', masked)
    return masked


def normalize_sql(sql: str) -> str:
    sql = (sql or "").strip()
    if not sql:
        return sql
    sql = sql.strip().rstrip(";").strip()

    m = _SELECT_TOP.match(sql)
    if m:
        distinct = m.group(1) or ""
        n = m.group(2)
        rest = sql[m.end() :]
        rebuilt = f"SELECT {distinct}{rest}".strip()
        if not re.search(r"\blimit\s+\d+\b", rebuilt, re.IGNORECASE):
            rebuilt = f"{rebuilt}\nLIMIT {int(n)}"
        return rebuilt

    if _SET_OP.search(sql):
        sql = _LIMIT_BEFORE_SET_OP.sub("", sql).strip()

    return sql


def _format_match(m: re.Match[str]) -> str:
    raw = m.group(0) or ""
    cleaned = re.sub(r"\s+", " ", raw).strip()
    return cleaned or "UNKNOWN"


def classify_statement(sql: str) -> str:
    s = (sql or "").lstrip().lower()
    if s.startswith("with"):
        return "with"
    if s.startswith("select"):
        return "select"
    if s.startswith("insert"):
        return "insert"
    if s.startswith("update"):
        return "update"
    if s.startswith("create"):
        return "create"
    if s.startswith("delete"):
        return "delete"
    return "other"


def validate_readonly_sql(sql: str, *, max_statements: int = 1) -> list[str]:
    sql = (sql or "").strip()
    if not sql:
        raise UnsafeSQLError("Empty SQL")

    normalized = normalize_sql(sql)
    statements = _split_statements(normalized, max_statements=max(1, int(max_statements)))
    out: list[str] = []
    for stmt_sql in statements:
        head = stmt_sql.lstrip().lower()
        if not (head.startswith("select") or head.startswith("with")):
            raise UnsafeSQLError("Only SELECT queries are allowed")
        m = _FORBIDDEN.search(_mask_literals_and_comments(stmt_sql))
        if m:
            raise UnsafeSQLError(f"Query contains forbidden keyword: {_format_match(m)}")
        out.append(stmt_sql)
    return out


def validate_sql(sql: str, *, sql_mode: SQLMode, max_statements: int = 1) -> list[str]:
    sql = (sql or "").strip()
    if not sql:
        raise UnsafeSQLError("Empty SQL")

    normalized = normalize_sql(sql)
    statements = _split_statements(normalized, max_statements=max(1, int(max_statements)))

    out: list[str] = []
    for stmt_sql in statements:
        stmt = classify_statement(stmt_sql)
        masked = _mask_literals_and_comments(stmt_sql)

        if sql_mode == "read_only":
            if stmt not in ("select", "with"):
                raise UnsafeSQLError("Only SELECT queries are allowed")
            m = _FORBIDDEN.search(masked)
            if m:
                raise UnsafeSQLError(f"Query contains forbidden keyword: {_format_match(m)}")
            out.append(stmt_sql)
            continue

        if sql_mode == "write_no_delete":
            if stmt not in ("select", "with", "insert", "update", "create"):
                raise UnsafeSQLError("Only SELECT/WITH/INSERT/UPDATE/CREATE are allowed")

            m = _FORBIDDEN_WRITE_NO_DELETE.search(masked)
            if m:
                raise UnsafeSQLError(f"Query contains forbidden keyword: {_format_match(m)}")

            if stmt == "update" and not re.search(r"\bwhere\b", masked, re.IGNORECASE):
                raise UnsafeSQLError("UPDATE must include WHERE")

            if stmt == "create" and not _CREATE_ALLOWED.match(masked):
                raise UnsafeSQLError("Only CREATE TABLE/VIEW/INDEX are allowed")

            out.append(stmt_sql)
            continue

        if sql_mode == "write_full":
            if stmt not in ("select", "with", "insert", "update", "delete", "create"):
                raise UnsafeSQLError("Only SELECT/WITH/INSERT/UPDATE/DELETE/CREATE are allowed")

            m = _FORBIDDEN_WRITE_FULL.search(masked)
            if m:
                raise UnsafeSQLError(f"Query contains forbidden keyword: {_format_match(m)}")

            if stmt in ("update", "delete") and not re.search(r"\bwhere\b", masked, re.IGNORECASE):
                raise UnsafeSQLError(f"{stmt.upper()} must include WHERE")

            if stmt == "create" and not _CREATE_ALLOWED.match(masked):
                raise UnsafeSQLError("Only CREATE TABLE/VIEW/INDEX are allowed")

            out.append(stmt_sql)
            continue

        raise UnsafeSQLError("Unknown SQL mode")

    return out


def apply_limit(sql: str, max_rows: int) -> str:
    max_rows = max(1, int(max_rows))
    normalized = sqlparse.format(sql, strip_comments=True).strip().rstrip(";").strip()
    if _SET_OP.search(normalized):
        if re.search(r"\blimit\s+\d+\s*$", normalized, re.IGNORECASE):
            return normalized
        normalized = _LIMIT_BEFORE_SET_OP.sub("", normalized).strip()
        return f"{normalized}\nLIMIT {max_rows}"

    if re.search(r"\blimit\s+\d+\b", normalized, re.IGNORECASE):
        return normalized
    return f"{normalized}\nLIMIT {max_rows}"
