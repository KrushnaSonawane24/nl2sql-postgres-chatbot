from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


class DatabaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[dict[str, Any]]
    rowcount: int


class PostgresDB:
    def __init__(self, database_url: str):
        if not database_url:
            raise DatabaseError("Missing DATABASE_URL")
        self._database_url = database_url

    def _connect(self):
        return psycopg2.connect(self._database_url)

    def fetch_schema(self, *, include_system: bool = False) -> str:
        where_system = ""
        if not include_system:
            where_system = "AND table_schema NOT IN ('pg_catalog', 'information_schema')"

        sql = f"""
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE 1=1
          {where_system}
        ORDER BY table_schema, table_name, ordinal_position
        """

        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql)
                    rows = cur.fetchall()
        except Exception as e:
            raise DatabaseError(f"Schema fetch failed: {e}") from e

        lines: list[str] = []
        current_table = None
        for r in rows:
            table = f"{r['table_schema']}.{r['table_name']}"
            if table != current_table:
                lines.append(f"\nTABLE {table}")
                current_table = table
            lines.append(f"  - {r['column_name']} ({r['data_type']})")
        return "\n".join(lines).strip()

    def execute_sql(
        self,
        sql: str,
        *,
        statement_timeout_ms: int = 8000,
    ) -> QueryResult:
        results = self.execute_sql_batch([sql], statement_timeout_ms=statement_timeout_ms)
        return results[0]

    def execute_sql_batch(
        self,
        statements: list[str],
        *,
        statement_timeout_ms: int = 8000,
    ) -> list[QueryResult]:
        if not statements:
            raise DatabaseError("Empty SQL")
        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(f"SET statement_timeout TO '{int(statement_timeout_ms)}ms'")
                    out: list[QueryResult] = []
                    for sql in statements:
                        cur.execute(sql)
                        rows: list[dict[str, Any]] = []
                        columns: list[str] = []
                        if cur.description is not None:
                            rows = cur.fetchall()
                            columns = list(rows[0].keys()) if rows else [d.name for d in cur.description]
                        out.append(QueryResult(columns=columns, rows=rows, rowcount=int(cur.rowcount)))
                    return out
        except Exception as e:
            raise DatabaseError(f"Query failed: {e}") from e
