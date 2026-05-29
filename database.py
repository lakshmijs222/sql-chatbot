import pandas as pd
from sqlalchemy import create_engine, text, event
from sqlalchemy.pool import QueuePool
from pathlib import Path
from dotenv import load_dotenv
from logger import logger
from config import DB_SERVER, DB_NAME, DB_POOL_SIZE, DB_QUERY_TIMEOUT, DB_MAX_ROWS

load_dotenv(Path(__file__).parent / ".env", override=True)

_CONNECTION_STRING = (
    f"mssql+pyodbc://@{DB_SERVER}/{DB_NAME}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
    "&trusted_connection=yes"
)

_FORBIDDEN = ("DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "EXEC", "EXECUTE", "GRANT", "REVOKE")


def _make_engine():
    return create_engine(
        _CONNECTION_STRING,
        poolclass=QueuePool,
        pool_size=DB_POOL_SIZE,
        max_overflow=2,
        pool_pre_ping=True,         # auto-reconnect on stale connections
        connect_args={"timeout": DB_QUERY_TIMEOUT},
    )


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def get_schema() -> str:
    query = """
        SELECT t.TABLE_SCHEMA, t.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.IS_NULLABLE
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c
            ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
        WHERE t.TABLE_SCHEMA = 'gold'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(query)).fetchall()

    schema_text = "Database: DataWarehouseAnalytics\n\nTables:\n"
    current_table = None
    for row in rows:
        table_full = f"{row[0]}.{row[1]}"
        if table_full != current_table:
            schema_text += f"\nTable: {table_full}\n  Columns:\n"
            current_table = table_full
        nullable = "NULL" if row[4] == "YES" else "NOT NULL"
        schema_text += f"    - {row[2]} ({row[3]}, {nullable})\n"

    logger.info("Schema loaded: %d tables", schema_text.count("Table:"))
    return schema_text


def run_query(sql: str) -> pd.DataFrame:
    sql = sql.strip()
    upper = sql.upper().lstrip()
    for keyword in _FORBIDDEN:
        if upper.startswith(keyword) or f" {keyword} " in upper:
            raise ValueError(f"Blocked operation: {keyword}. Only SELECT queries are allowed.")

    if not upper.startswith("SELECT"):
        raise ValueError("Query must start with SELECT.")

    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)

    if len(df) > DB_MAX_ROWS:
        df = df.head(DB_MAX_ROWS)
        logger.warning("Result truncated to %d rows", DB_MAX_ROWS)

    return df
