import logging
import json
from datetime import datetime
from pathlib import Path
from config import LOG_DIR

# File logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("sql_chatbot")

_query_log_file = LOG_DIR / "query_history.jsonl"


def log_query(user: str, question: str, sql: str, row_count: int, error: str = None):
    """Append a query record to the JSONL log."""
    record = {
        "ts": datetime.utcnow().isoformat(),
        "user": user,
        "question": question,
        "sql": sql,
        "rows": row_count,
        "error": error,
    }
    with open(_query_log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    if error:
        logger.error("Query failed | user=%s | error=%s", user, error)
    else:
        logger.info("Query OK | user=%s | rows=%d", user, row_count)
