import hashlib
import json
from datetime import datetime, timedelta

# In-memory cache: {hash: {"sql": ..., "result": ..., "expires": ...}}
_cache: dict = {}
TTL_MINUTES = 15


def _key(question: str, schema_hash: str) -> str:
    raw = f"{question.strip().lower()}|{schema_hash}"
    return hashlib.md5(raw.encode()).hexdigest()


def get(question: str, schema_hash: str):
    k = _key(question, schema_hash)
    entry = _cache.get(k)
    if entry and datetime.utcnow() < entry["expires"]:
        return entry["sql"], entry["df"]
    return None, None


def set(question: str, schema_hash: str, sql: str, df):
    k = _key(question, schema_hash)
    _cache[k] = {
        "sql": sql,
        "df": df,
        "expires": datetime.utcnow() + timedelta(minutes=TTL_MINUTES),
    }


def size() -> int:
    now = datetime.utcnow()
    return sum(1 for v in _cache.values() if now < v["expires"])
