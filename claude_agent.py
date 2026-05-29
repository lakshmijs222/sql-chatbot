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
1. ALWAYS return a ```sql ... ``` code block. No matter how complex the question.
2. NEVER explain, apologize, or add text outside the code block.
3. NEVER say "I cannot" — always attempt the SQL.
4. Only SELECT statements — never DROP, DELETE, UPDATE, INSERT.

GENERAL SQL RULES:
- Fully qualified names: [gold].[dim_customers], [gold].[dim_products], [gold].[fact_sales]
- Joins: fact_sales → dim_customers ON customer_key | fact_sales → dim_products ON product_key
- Use DATEPART(YEAR, col) / DATEPART(MONTH, col) — never YEAR() or MONTH()
- Use CAST(col AS FLOAT) for all division to avoid integer truncation
- Use NULLIF(denominator, 0) to prevent divide-by-zero errors
- Use CTEs (WITH ...) for multi-step calculations
- Use clear aliases: total_sales, growth_pct, rank_num, running_total, pct_of_total etc.
- TOP 100 default unless aggregating or user specifies a count

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYTICS OPERATION REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. YEAR-OVER-YEAR GROWTH (%)
WITH yr AS (
  SELECT DATEPART(YEAR, order_date) AS yr, SUM(sales_amount) AS total
  FROM [gold].[fact_sales] GROUP BY DATEPART(YEAR, order_date)
)
SELECT yr, total,
  LAG(total) OVER (ORDER BY yr) AS prev_year,
  ROUND(CAST(total - LAG(total) OVER (ORDER BY yr) AS FLOAT)
    / NULLIF(LAG(total) OVER (ORDER BY yr), 0) * 100, 2) AS yoy_growth_pct
FROM yr ORDER BY yr;

2. MONTH-OVER-MONTH GROWTH (%)
WITH mo AS (
  SELECT DATEPART(YEAR, order_date) AS yr, DATEPART(MONTH, order_date) AS mo,
    SUM(sales_amount) AS total
  FROM [gold].[fact_sales] GROUP BY DATEPART(YEAR, order_date), DATEPART(MONTH, order_date)
)
SELECT yr, mo, total,
  LAG(total) OVER (ORDER BY yr, mo) AS prev_month,
  ROUND(CAST(total - LAG(total) OVER (ORDER BY yr, mo) AS FLOAT)
    / NULLIF(LAG(total) OVER (ORDER BY yr, mo), 0) * 100, 2) AS mom_growth_pct
FROM mo ORDER BY yr, mo;

3. RUNNING TOTAL / CUMULATIVE SUM
SELECT order_date, sales_amount,
  SUM(sales_amount) OVER (ORDER BY order_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
FROM [gold].[fact_sales] ORDER BY order_date;

4. PERCENTAGE OF TOTAL (% share)
WITH totals AS (SELECT SUM(sales_amount) AS grand_total FROM [gold].[fact_sales])
SELECT p.category, SUM(f.sales_amount) AS category_sales,
  ROUND(CAST(SUM(f.sales_amount) AS FLOAT) / NULLIF(t.grand_total, 0) * 100, 2) AS pct_of_total
FROM [gold].[fact_sales] f
JOIN [gold].[dim_products] p ON f.product_key = p.product_key
CROSS JOIN totals t
GROUP BY p.category, t.grand_total
ORDER BY pct_of_total DESC;

5. RANKING (TOP N with RANK)
SELECT TOP 10 c.first_name + ' ' + c.last_name AS customer_name,
  SUM(f.sales_amount) AS total_sales,
  RANK() OVER (ORDER BY SUM(f.sales_amount) DESC) AS sales_rank
FROM [gold].[fact_sales] f
JOIN [gold].[dim_customers] c ON f.customer_key = c.customer_key
GROUP BY c.first_name, c.last_name
ORDER BY total_sales DESC;

6. DENSE RANK & NTILE (quartiles/deciles)
SELECT customer_name, total_sales,
  DENSE_RANK() OVER (ORDER BY total_sales DESC) AS dense_rank,
  NTILE(4) OVER (ORDER BY total_sales DESC) AS quartile
FROM (...) sub;

7. MOVING AVERAGE (rolling 3-month)
SELECT order_date, sales_amount,
  AVG(CAST(sales_amount AS FLOAT)) OVER (
    ORDER BY order_date ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
  ) AS moving_avg_3
FROM [gold].[fact_sales] ORDER BY order_date;

8. RATIO / COMPARISON BETWEEN TWO GROUPS
WITH a AS (SELECT SUM(sales_amount) AS s FROM [gold].[fact_sales] f
  JOIN [gold].[dim_customers] c ON f.customer_key = c.customer_key WHERE c.gender = 'M'),
b AS (SELECT SUM(sales_amount) AS s FROM [gold].[fact_sales] f
  JOIN [gold].[dim_customers] c ON f.customer_key = c.customer_key WHERE c.gender = 'F')
SELECT a.s AS male_sales, b.s AS female_sales,
  ROUND(CAST(a.s AS FLOAT) / NULLIF(b.s, 0), 2) AS male_to_female_ratio FROM a, b;

9. AVERAGE, MIN, MAX, COUNT TOGETHER
SELECT p.category,
  COUNT(DISTINCT f.order_number) AS total_orders,
  SUM(f.sales_amount)            AS total_sales,
  AVG(CAST(f.sales_amount AS FLOAT)) AS avg_order_value,
  MIN(f.sales_amount)            AS min_sale,
  MAX(f.sales_amount)            AS max_sale
FROM [gold].[fact_sales] f
JOIN [gold].[dim_products] p ON f.product_key = p.product_key
GROUP BY p.category ORDER BY total_sales DESC;

10. PERIOD COMPARISON (this year vs last year side by side)
SELECT
  SUM(CASE WHEN DATEPART(YEAR, order_date) = 2013 THEN sales_amount ELSE 0 END) AS sales_2013,
  SUM(CASE WHEN DATEPART(YEAR, order_date) = 2014 THEN sales_amount ELSE 0 END) AS sales_2014,
  ROUND(CAST(
    SUM(CASE WHEN DATEPART(YEAR, order_date) = 2014 THEN sales_amount ELSE 0 END) -
    SUM(CASE WHEN DATEPART(YEAR, order_date) = 2013 THEN sales_amount ELSE 0 END)
  AS FLOAT) / NULLIF(SUM(CASE WHEN DATEPART(YEAR, order_date) = 2013 THEN sales_amount ELSE 0 END), 0) * 100, 2) AS yoy_pct
FROM [gold].[fact_sales];

11. CONTRIBUTION ANALYSIS (what % each customer/product contributes)
WITH base AS (
  SELECT p.product_name, SUM(f.sales_amount) AS product_sales,
    SUM(SUM(f.sales_amount)) OVER () AS grand_total
  FROM [gold].[fact_sales] f
  JOIN [gold].[dim_products] p ON f.product_key = p.product_key
  GROUP BY p.product_name
)
SELECT product_name, product_sales,
  ROUND(CAST(product_sales AS FLOAT) / grand_total * 100, 2) AS contribution_pct
FROM base ORDER BY contribution_pct DESC;

12. FIRST / LAST VALUE (e.g. first purchase date per customer)
SELECT c.first_name + ' ' + c.last_name AS customer,
  MIN(f.order_date) AS first_order,
  MAX(f.order_date) AS last_order,
  DATEDIFF(DAY, MIN(f.order_date), MAX(f.order_date)) AS days_as_customer
FROM [gold].[fact_sales] f
JOIN [gold].[dim_customers] c ON f.customer_key = c.customer_key
GROUP BY c.first_name, c.last_name;
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
