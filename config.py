from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).parent / ".env", override=True)

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "1024"))

# Database
DB_SERVER = os.getenv("DB_SERVER", r"DESKTOP-64VG7D3\SQLEXPRESS")
DB_NAME = os.getenv("DB_NAME", "AdventureWorksLT2022")
# Comma-separated list of schemas to expose. Leave blank to auto-detect all
# user schemas (everything except the system schemas listed below).
DB_SCHEMAS = os.getenv("DB_SCHEMAS", "SalesLT")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_QUERY_TIMEOUT = int(os.getenv("DB_QUERY_TIMEOUT", "30"))
DB_MAX_ROWS = int(os.getenv("DB_MAX_ROWS", "500"))

# Schemas/tables to always ignore (system objects)
SYSTEM_SCHEMAS = ("sys", "INFORMATION_SCHEMA", "guest", "db_owner", "db_accessadmin")
SYSTEM_TABLES = ("BuildVersion", "ErrorLog", "sysdiagrams")

# Auth
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
ADMIN_PASSWORD_PLAIN = os.getenv("ADMIN_PASSWORD", "admin123")

# App
APP_TITLE = "InsightIQ"
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
