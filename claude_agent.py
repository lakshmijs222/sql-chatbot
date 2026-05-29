import anthropic
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

load_dotenv(Path(__file__).parent / ".env", override=True)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """You are a senior T-SQL data analyst. Your ONLY job is to write SQL queries.

Database: DataWarehouseAnalytics (SQL Server)
Schema:
{schema}

STRICT RULES — NO EXCEPTIONS:
1. ALWAYS return a ```sql ... ``` code block. Even if the question is complex or unclear.
2. NEVER explain, apologize, or add text outside the code block.
3. NEVER say "I cannot" or "this is complex" — always attempt the SQL.
4. Only write SELECT statements — never DROP, DELETE, UPDATE, INSERT.

SQL WRITING RULES:
- Use fully qualified names: [gold].[dim_customers], [gold].[dim_products], [gold].[fact_sales]
- Joins: fact_sales → dim_customers on customer_key | fact_sales → dim_products on product_key
- Use DATEPART(YEAR, col) and DATEPART(MONTH, col) — never YEAR() or MONTH()
- Use CTEs (WITH ...) for complex multi-step calculations like growth, rankings, percentages
- For year-over-year growth: use LAG() window function or self-join with CTEs
- For percentages: use CAST(col AS FLOAT) to avoid integer division
- Use TOP 100 unless aggregating or the user specifies otherwise
- Use clear aliases: total_sales, growth_pct, customer_name, order_year etc.
- Always return numbers as numbers (not strings) — UI handles formatting

EXAMPLE for "year over year growth":
WITH yearly AS (
  SELECT DATEPART(YEAR, order_date) AS order_year, SUM(sales_amount) AS total_sales
  FROM [gold].[fact_sales] GROUP BY DATEPART(YEAR, order_date)
)
SELECT order_year, total_sales,
  LAG(total_sales) OVER (ORDER BY order_year) AS prev_year_sales,
  ROUND(CAST(total_sales - LAG(total_sales) OVER (ORDER BY order_year) AS FLOAT)
    / NULLIF(LAG(total_sales) OVER (ORDER BY order_year), 0) * 100, 2) AS growth_pct
FROM yearly ORDER BY order_year;
"""

_REPAIR_PROMPT = """The following T-SQL query failed with an error. Fix it.

Original query:
```sql
{sql}
```

Error:
{error}

Database schema:
{schema}

Return only the corrected SQL query inside a ```sql ... ``` code block. Nothing else.
"""

_EXPLAIN_PROMPT = """You are a friendly data analyst explaining query results to a non-technical business team.

The user asked: "{question}"

The query returned {row_count} row(s). Here is a sample:
{results}

Instructions:
- Write a short summary (2-4 sentences) in plain business language
- Highlight the most important numbers or trends
- If results are empty, suggest why that might be
- Then add a **Key Insights** section with 2-3 bullet points (use - for bullets)
- Never mention SQL, queries, tables, or technical terms
- Use **bold** for important numbers
"""


def _call_claude(messages: list, system: str = None, retries: int = 3) -> str:
    kwargs = dict(model=CLAUDE_MODEL, max_tokens=MAX_TOKENS, messages=messages)
    if system:
        kwargs["system"] = system
    for attempt in range(retries):
        try:
            response = client.messages.create(**kwargs)
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise RuntimeError("The AI service is temporarily rate-limited. Please wait a moment and try again.")
        except anthropic.APIConnectionError:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                raise RuntimeError("Cannot reach the AI service. Please check your internet connection.")
        except anthropic.AuthenticationError:
            raise RuntimeError("Invalid API key. Please check your ANTHROPIC_API_KEY in the .env file.")
        except Exception as e:
            raise RuntimeError(f"AI service error: {str(e)}")
    raise RuntimeError("Failed after multiple retries.")


def extract_sql(text: str) -> str:
    """Robustly extract SQL from Claude's response using multiple strategies."""
    # Strategy 1: standard ```sql ... ``` block
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Strategy 2: any ``` ... ``` block
    match = re.search(r"```\s*(SELECT|WITH).*?```", text, re.DOTALL | re.IGNORECASE)
    if match:
        sql = re.sub(r"^```[a-z]*\s*", "", match.group(0)).rstrip("`").strip()
        return sql

    # Strategy 3: find SELECT or WITH anywhere in the text
    match = re.search(r"(WITH\s+\w|\bSELECT\b).*", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(0).strip()

    # Strategy 4: entire response might just be SQL (no code block)
    stripped = text.strip()
    upper = stripped.upper()
    if upper.startswith("SELECT") or upper.startswith("WITH"):
        return stripped

    raise ValueError(
        "The AI could not generate a SQL query for this question. "
        "Try rephrasing — for example: 'Show year over year sales growth by year'"
    )


def generate_sql(question: str, schema: str) -> str:
    raw = _call_claude(
        messages=[{"role": "user", "content": question}],
        system=_SYSTEM_PROMPT.format(schema=schema),
    )
    return extract_sql(raw)


def repair_sql(sql: str, error: str, schema: str) -> str:
    """Ask Claude to fix a broken SQL query."""
    raw = _call_claude(
        messages=[{"role": "user", "content": _REPAIR_PROMPT.format(sql=sql, error=error, schema=schema)}],
    )
    return extract_sql(raw)


def explain_results(question: str, sql: str, df) -> str:
    import pandas as pd
    row_count = len(df)
    if df.empty:
        results_str = "No rows returned."
    else:
        results_str = df.head(10).to_string(index=False)

    return _call_claude(
        messages=[{"role": "user", "content": _EXPLAIN_PROMPT.format(
            question=question,
            sql=sql,
            row_count=row_count,
            results=results_str,
        )}],
    )
