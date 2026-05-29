import anthropic
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are a helpful data analyst assistant for a business team.
You have access to a SQL Server data warehouse called DataWarehouseAnalytics with the following schema:

{schema}

Your job:
1. Understand the user's business question (written in plain English).
2. Write a valid T-SQL SELECT query to answer it.
3. Return ONLY the SQL query inside a ```sql ... ``` code block — nothing else in that first response.

Rules for writing SQL:
- Always use fully qualified names like [gold].[dim_customers]
- Only write SELECT statements — never DROP, DELETE, UPDATE, INSERT
- Use TOP 100 by default unless the user asks for more or for aggregations
- Use clear column aliases so results are readable
- For date filters, use CAST or CONVERT for SQL Server compatibility
"""

EXPLAIN_PROMPT = """You are a helpful data analyst assistant for a non-technical business team.

The user asked: "{question}"

The SQL query run was:
```sql
{sql}
```

The results were:
{results}

Now explain the results in plain, friendly English — like you are talking to a business person with no technical background.
Highlight key numbers, trends, or insights. Keep it concise (3-5 sentences max).
If the result is empty, say so clearly and suggest why that might be.
"""


def extract_sql(text: str) -> str:
    """Pull the SQL query out of a markdown code block."""
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    # Fallback: return the whole text if no code block found
    return text.strip()


def generate_sql(question: str, schema: str) -> str:
    """Ask Claude to convert a natural language question to SQL."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT.format(schema=schema),
        messages=[{"role": "user", "content": question}],
    )
    raw = response.content[0].text
    return extract_sql(raw)


def explain_results(question: str, sql: str, results_str: str) -> str:
    """Ask Claude to explain the query results in plain English."""
    prompt = EXPLAIN_PROMPT.format(
        question=question,
        sql=sql,
        results=results_str,
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text
