import pandas as pd
from sqlalchemy import create_engine, text, event
from sqlalchemy.pool import QueuePool
from pathlib import Path
from dotenv import load_dotenv
from logger import logger
from config import (DB_SERVER, DB_NAME, DB_POOL_SIZE, DB_QUERY_TIMEOUT, DB_MAX_ROWS,
                    DB_SCHEMAS, SYSTEM_SCHEMAS, SYSTEM_TABLES)

load_dotenv(Path(__file__).parent / ".env", override=True)

_FORBIDDEN = ("DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE")

# System databases never shown in the switcher
_SYSTEM_DBS = ("master", "tempdb", "model", "msdb")


def _conn_string(db_name: str) -> str:
    return (
        f"mssql+pyodbc://@{DB_SERVER}/{db_name}"
        "?driver=ODBC+Driver+17+for+SQL+Server"
        "&trusted_connection=yes"
    )


def _make_engine(db_name: str):
    return create_engine(
        _conn_string(db_name),
        poolclass=QueuePool,
        pool_size=DB_POOL_SIZE,
        max_overflow=2,
        pool_pre_ping=True,
        connect_args={"timeout": DB_QUERY_TIMEOUT},
    )


# Cache one engine per database name
_engines = {}


def get_engine(db_name: str = None):
    name = db_name or DB_NAME
    if name not in _engines:
        _engines[name] = _make_engine(name)
    return _engines[name]


def list_databases() -> list:
    """List user databases available on the server (excludes system DBs)."""
    engine = get_engine("master")
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT name FROM sys.databases WHERE state = 0 ORDER BY name"
        )).fetchall()
    return [r[0] for r in rows if r[0].lower() not in _SYSTEM_DBS]


def _schema_filter_clause(schemas: str = None):
    """Build the WHERE clause + params to restrict to the chosen schemas.
    If `schemas` is None, fall back to configured DB_SCHEMAS."""
    raw = DB_SCHEMAS if schemas is None else schemas
    configured = [s.strip() for s in raw.split(",") if s.strip()]
    if configured:
        placeholders = ", ".join(f":s{i}" for i in range(len(configured)))
        clause = f"t.TABLE_SCHEMA IN ({placeholders})"
        params = {f"s{i}": name for i, name in enumerate(configured)}
    else:
        # Auto-detect: exclude system schemas
        placeholders = ", ".join(f":sys{i}" for i in range(len(SYSTEM_SCHEMAS)))
        clause = f"t.TABLE_SCHEMA NOT IN ({placeholders})"
        params = {f"sys{i}": name for i, name in enumerate(SYSTEM_SCHEMAS)}
    return clause, params


def list_tables(db_name: str = None, schemas: str = None) -> list:
    """Return a list of 'schema.table' names exposed to the chatbot."""
    clause, params = _schema_filter_clause(schemas)
    query = text(f"""
        SELECT DISTINCT TABLE_SCHEMA, TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES t
        WHERE TABLE_TYPE = 'BASE TABLE' AND {clause}
        ORDER BY TABLE_SCHEMA, TABLE_NAME
    """)
    engine = get_engine(db_name)
    with engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [f"{r[0]}.{r[1]}" for r in rows if r[1] not in SYSTEM_TABLES]


def get_schema(db_name: str = None, schemas: str = None) -> str:
    clause, params = _schema_filter_clause(schemas)
    query = text(f"""
        SELECT t.TABLE_SCHEMA, t.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.IS_NULLABLE
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c
            ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
        WHERE t.TABLE_TYPE = 'BASE TABLE' AND {clause}
        ORDER BY t.TABLE_SCHEMA, t.TABLE_NAME, c.ORDINAL_POSITION
    """)
    engine = get_engine(db_name)
    with engine.connect() as conn:
        rows = conn.execute(query, params).fetchall()

    schema_text = f"Database: {db_name or DB_NAME}\n\nTables:\n"
    current_table = None
    for row in rows:
        if row[1] in SYSTEM_TABLES:
            continue
        table_full = f"{row[0]}.{row[1]}"
        if table_full != current_table:
            schema_text += f"\nTable: {table_full}\n  Columns:\n"
            current_table = table_full
        nullable = "NULL" if row[4] == "YES" else "NOT NULL"
        schema_text += f"    - {row[2]} ({row[3]}, {nullable})\n"

    logger.info("Schema loaded: %d tables from %s", schema_text.count("Table:"), db_name or DB_NAME)
    return schema_text


def run_query(sql: str, db_name: str = None) -> pd.DataFrame:
    sql = sql.strip()
    upper = sql.upper().lstrip()

    # Block destructive operations anywhere in the statement
    for keyword in _FORBIDDEN:
        if upper.startswith(keyword) or f" {keyword} " in upper:
            raise ValueError(f"Blocked operation: {keyword}. Only read-only queries are allowed.")

    # Allow read-only query forms: plain SELECT, CTEs (WITH), and
    # variable declarations used by date-relative analytics (DECLARE ... SELECT)
    allowed_starts = ("SELECT", "WITH", "DECLARE")
    if not upper.startswith(allowed_starts):
        raise ValueError("Only read-only queries (SELECT) are allowed.")

    engine = get_engine(db_name)
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    if len(df) > DB_MAX_ROWS:
        df = df.head(DB_MAX_ROWS)
        logger.warning("Result truncated to %d rows", DB_MAX_ROWS)

    return df
