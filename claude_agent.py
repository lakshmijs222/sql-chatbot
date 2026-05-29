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
3. Return ONLY the SQL query inside a ```sql ... ``` code block.

Rules:
- Always use fully qualified names: [gold].[dim_customers], [gold].[dim_products], [gold].[fact_sales]
- Only write SELECT statements — never DROP, DELETE, UPDATE, INSERT
- Use TOP 100 by default unless the user asks for more or requests aggregations
- Use meaningful column aliases (e.g. total_sales, customer_name)
- For joins: fact_sales joins dim_customers on customer_key, joins dim_products on product_key
- For currency: format as plain numbers (not strings), let the UI handle formatting
- If a question is ambiguous, make the most reasonable business assumption
"""

_EXPLAIN_PROMPT = """You are a friendly data analyst explaining results to a non-technical business team.

The user asked: "{question}"

The SQL query run was:
```sql
{sql}
```

The query returned {row_count} rows. Here is a sample of the data:
{results}

Instructions:
- Write a clear, concise summary (3-5 sentences max)
- Highlight the most important numbers and insights
- Use plain business language — no SQL or technical terms
- If results are empty, explain possible reasons
- Add a "Key Insights" section with 2-3 bullet points if there are interesting patterns
"""


def extract_sql(text: str) -> str:
    match = re.search(r"```sql\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def generate_sql(question: str, schema: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                system=_SYSTEM_PROMPT.format(schema=schema),
                messages=[{"role": "user", "content": question}],
            )
            return extract_sql(response.content[0].text)
        except anthropic.RateLimitError:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError("Failed to generate SQL after retries.")


def explain_results(question: str, sql: str, df, retries: int = 3) -> str:
    row_count = len(df)
    results_str = "No data returned." if df.empty else df.head(10).to_string(index=False)

    prompt = _EXPLAIN_PROMPT.format(
        question=question,
        sql=sql,
        row_count=row_count,
        results=results_str,
    )
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    raise RuntimeError("Failed to explain results after retries.")
