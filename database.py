import pyodbc
import pandas as pd
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

from pathlib import Path
load_dotenv(Path(__file__).parent / ".env", override=True)

SERVER = os.getenv("DB_SERVER", r"DESKTOP-64VG7D3\SQLEXPRESS")
DATABASE = os.getenv("DB_NAME", "DataWarehouseAnalytics")

CONNECTION_STRING = (
    f"mssql+pyodbc://@{SERVER}/{DATABASE}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
    "&trusted_connection=yes"
)


def get_engine():
    return create_engine(CONNECTION_STRING)


def get_schema() -> str:
    """Extract table and column metadata from the gold schema."""
    engine = get_engine()
    query = """
        SELECT
            t.TABLE_SCHEMA,
            t.TABLE_NAME,
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.IS_NULLABLE
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c
            ON t.TABLE_NAME = c.TABLE_NAME
            AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
        WHERE t.TABLE_SCHEMA = 'gold'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
    """
    with engine.connect() as conn:
        rows = conn.execute(text(query)).fetchall()

    schema_text = "Database: DataWarehouseAnalytics\n\nTables:\n"
    current_table = None
    for row in rows:
        table_full = f"{row[0]}.{row[1]}"
        if table_full != current_table:
            schema_text += f"\nTable: {table_full}\n"
            schema_text += "  Columns:\n"
            current_table = table_full
        nullable = "NULL" if row[4] == "YES" else "NOT NULL"
        schema_text += f"    - {row[2]} ({row[3]}, {nullable})\n"

    return schema_text


def run_query(sql: str) -> pd.DataFrame:
    """Execute a SELECT query and return results as a DataFrame."""
    sql = sql.strip()

    # Safety: only allow SELECT statements
    upper = sql.upper().lstrip()
    forbidden = ("DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "EXEC", "EXECUTE")
    for keyword in forbidden:
        if upper.startswith(keyword):
            raise ValueError(f"Only SELECT queries are allowed. Blocked keyword: {keyword}")

    engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    return df
