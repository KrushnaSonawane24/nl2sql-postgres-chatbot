# NL → SQL Chatbot (PostgreSQL) using Gemini

This is a simple Natural Language → SQL chatbot:

- Uses Gemini (Google Generative Language API) to generate SQL
- Introspects your PostgreSQL schema (tables + columns) and uses it in the prompt
- Enforces read-only SQL (single `SELECT` / `WITH`) and applies a row limit
- Runs as a Streamlit chat app

## 1) Setup

Create a virtual environment and install deps:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env` (copy from `.env.example`) and fill in your values:

```env
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-1.5-flash-latest
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
```

## 2) Run the app

```bash
streamlit run app.py
```

## SQL modes

- `read_only`: only `SELECT` / `WITH` queries run automatically.
- `write_no_delete`: allows `INSERT`, `UPDATE`, and `CREATE TABLE/VIEW/INDEX` (no `DELETE`). Write queries are shown first and require an explicit Execute click.
- `write_full`: allows full CRUD (`INSERT`/`UPDATE`/`DELETE`) plus `CREATE TABLE/VIEW/INDEX`. Write queries are shown first and require an explicit Execute click.

## Safety notes

- This app only allows a single read-only statement (must start with `SELECT` or `WITH`).
- It also blocks common write keywords and applies a `LIMIT` if missing.
- Still, never point this at a production DB with broad permissions. Use a read-only role.

## Project structure

- `app.py`: Streamlit UI
- `src/nl2sql/agent.py`: prompt + SQL generation + execution orchestration
- `src/nl2sql/db.py`: Postgres schema + query execution
- `src/nl2sql/sql_safety.py`: SQL validation and `LIMIT` enforcement
