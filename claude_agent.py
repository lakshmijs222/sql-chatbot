import anthropic
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

load_dotenv(Path(__file__).parent / ".env", override=True)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """You are a helpful senior data analyst assistant for a business team.
You have access to a SQL Server data warehouse called DataWarehouseAnalytics with the following schema:

{schema}

Your job:
1. Understand the user's business question written in plain English.
2. Write a valid T-SQL SELECT query to answer it.
3. Return ONLY the SQL query inside a ```sql ... ``` code block. Nothing else.

Rules:
- Always use fully qualified names: [gold].[dim_customers], [gold].[dim_products], [gold].[fact_sales]
- Only write SELECT statements — never DROP, DELETE, UPDATE, INSERT
- Use TOP 100 by default unless the user asks for more or requests aggregations
- Use meaningful column aliases (e.g. total_sales, customer_name)
- For joins: fact_sales joins dim_customers on customer_key, joins dim_products on product_key
- For currency: use plain numbers (not strings), the UI handles formatting
- If a question is ambiguous, make the most reasonable business assumption
- Never use YEAR() or MONTH() — use DATEPART(YEAR, col) and DATEPART(MONTH, col) instead
- Always wrap column/table names with brackets if they could conflict with reserved words
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
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: if no code block but looks like SQL
    text = text.strip()
    if text.upper().startswith("SELECT"):
        return text
    raise ValueError("Could not extract a valid SQL query from the AI response.")


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
