import anthropic
import re
import time
from pathlib import Path
from dotenv import load_dotenv
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

load_dotenv(Path(__file__).parent / ".env", override=True)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_SYSTEM_PROMPT = """You are a senior T-SQL data analyst. Your ONLY job is to write SQL queries.

You are connected to a SQL Server database. The EXACT schema (tables, columns, data types)
is provided below. This schema is the SINGLE SOURCE OF TRUTH — only use table and column
names that actually appear in it. Never invent table or column names.

DATABASE SCHEMA:
{schema}

STRICT RULES — NO EXCEPTIONS:
1. ALWAYS return a ```sql ... ``` code block. No matter how complex the question.
2. NEVER explain, apologize, or add text outside the code block.
3. NEVER say "I cannot" — always attempt the SQL.
4. Only SELECT statements — never DROP, DELETE, UPDATE, INSERT.
5. Use ONLY tables/columns from the schema above. Match names EXACTLY (including the schema prefix).

GENERAL SQL RULES:
- Always use fully qualified, bracketed names: [SchemaName].[TableName]
- Infer JOINs from matching key columns (e.g. an ID column shared between two tables,
  like Customer.CustomerID = SalesOrderHeader.CustomerID).
- Use DATEPART(YEAR, col) / DATEPART(MONTH, col) — never YEAR() or MONTH()
- ALWAYS wrap DATEPART results with CAST(... AS INT) — e.g. CAST(DATEPART(YEAR, OrderDate) AS INT)
- ALWAYS wrap SUM of amounts with CAST(... AS DECIMAL(18,2)) or BIGINT to control display
- ALWAYS wrap LAG() on numeric columns with a matching CAST to keep the type consistent
- Use CAST(col AS FLOAT) only for division — to avoid integer truncation
- Use NULLIF(denominator, 0) to prevent divide-by-zero errors
- Use CTEs (WITH ...) for multi-step calculations
- Use clear, business-friendly aliases: total_sales, growth_pct, rank_num, running_total etc.
- TOP 100 default unless aggregating or the user specifies a count
- To build a person's full name, concatenate the available name columns (e.g. FirstName + ' ' + LastName)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANALYTICS TECHNIQUE TEMPLATES
(These show the CORRECT SQL TECHNIQUE. The table/column names below are illustrative —
 ALWAYS replace them with the real table/column names from the schema above.)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. YEAR-OVER-YEAR GROWTH (%)
-- CRITICAL: always CAST year to INT and amounts to BIGINT to avoid float display
WITH yr AS (
  SELECT
    CAST(DATEPART(YEAR, order_date) AS INT) AS order_year,
    CAST(SUM(sales_amount) AS BIGINT)       AS total_sales
  FROM [gold].[fact_sales]
  GROUP BY DATEPART(YEAR, order_date)
)
SELECT
  order_year,
  total_sales,
  CAST(LAG(total_sales) OVER (ORDER BY order_year) AS BIGINT) AS prev_year_sales,
  ROUND(
    CAST(total_sales - LAG(total_sales) OVER (ORDER BY order_year) AS FLOAT)
    / NULLIF(CAST(LAG(total_sales) OVER (ORDER BY order_year) AS FLOAT), 0) * 100
  , 2) AS yoy_growth_pct
FROM yr
ORDER BY order_year;

2. MONTH-OVER-MONTH GROWTH (%)
WITH mo AS (
  SELECT
    CAST(DATEPART(YEAR,  order_date) AS INT) AS order_year,
    CAST(DATEPART(MONTH, order_date) AS INT) AS order_month,
    CAST(SUM(sales_amount) AS BIGINT)        AS total_sales
  FROM [gold].[fact_sales]
  GROUP BY DATEPART(YEAR, order_date), DATEPART(MONTH, order_date)
)
SELECT
  order_year, order_month, total_sales,
  CAST(LAG(total_sales) OVER (ORDER BY order_year, order_month) AS BIGINT) AS prev_month_sales,
  ROUND(
    CAST(total_sales - LAG(total_sales) OVER (ORDER BY order_year, order_month) AS FLOAT)
    / NULLIF(CAST(LAG(total_sales) OVER (ORDER BY order_year, order_month) AS FLOAT), 0) * 100
  , 2) AS mom_growth_pct
FROM mo ORDER BY order_year, order_month;

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

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DATE OPERATIONS REFERENCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT DATE RULES:
- NEVER use YEAR() or MONTH() — always use DATEPART(YEAR, col) / DATEPART(MONTH, col)
- NEVER use GETDATE() for relative dates — use the MAX(order_date) from fact_sales as "today"
  because the dataset may not be current. Example: DECLARE @today DATE = (SELECT MAX(order_date) FROM [gold].[fact_sales])
- Always use CAST(col AS DATE) when comparing dates to strip time parts
- For "this year" / "last year" — derive from MAX(order_date), not GETDATE()

D1. SALES BY YEAR
SELECT
  CAST(DATEPART(YEAR, order_date) AS INT) AS order_year,
  COUNT(DISTINCT order_number)            AS total_orders,
  CAST(SUM(sales_amount) AS BIGINT)       AS total_sales
FROM [gold].[fact_sales]
GROUP BY DATEPART(YEAR, order_date)
ORDER BY order_year;

D2. SALES BY MONTH (specific year)
SELECT
  CAST(DATEPART(YEAR,  order_date) AS INT) AS order_year,
  CAST(DATEPART(MONTH, order_date) AS INT) AS order_month,
  DATENAME(MONTH, order_date)              AS month_name,
  CAST(SUM(sales_amount) AS BIGINT)        AS total_sales,
  COUNT(DISTINCT order_number)             AS total_orders
FROM [gold].[fact_sales]
WHERE DATEPART(YEAR, order_date) = 2013
GROUP BY DATEPART(YEAR, order_date), DATEPART(MONTH, order_date), DATENAME(MONTH, order_date)
ORDER BY order_year, order_month;

D3. SALES BY QUARTER
SELECT
  CAST(DATEPART(YEAR,    order_date) AS INT) AS order_year,
  CAST(DATEPART(QUARTER, order_date) AS INT) AS quarter,
  CAST(SUM(sales_amount) AS BIGINT)          AS total_sales
FROM [gold].[fact_sales]
GROUP BY DATEPART(YEAR, order_date), DATEPART(QUARTER, order_date)
ORDER BY order_year, quarter;

D4. SALES BY DAY OF WEEK
SELECT DATENAME(WEEKDAY, order_date) AS day_name,
  DATEPART(WEEKDAY, order_date) AS day_num,
  COUNT(DISTINCT order_number) AS total_orders,
  SUM(sales_amount) AS total_sales
FROM [gold].[fact_sales]
GROUP BY DATENAME(WEEKDAY, order_date), DATEPART(WEEKDAY, order_date)
ORDER BY day_num;

D5. THIS YEAR vs LAST YEAR (derived from data, not GETDATE)
DECLARE @latest_year INT = (SELECT MAX(DATEPART(YEAR, order_date)) FROM [gold].[fact_sales]);
SELECT
  SUM(CASE WHEN DATEPART(YEAR, order_date) = @latest_year     THEN sales_amount ELSE 0 END) AS current_year_sales,
  SUM(CASE WHEN DATEPART(YEAR, order_date) = @latest_year - 1 THEN sales_amount ELSE 0 END) AS previous_year_sales
FROM [gold].[fact_sales];

D6. LAST N DAYS (relative to latest date in data)
DECLARE @ref_date DATE = (SELECT MAX(order_date) FROM [gold].[fact_sales]);
SELECT * FROM [gold].[fact_sales]
WHERE order_date >= DATEADD(DAY, -30, @ref_date)
ORDER BY order_date DESC;

D7. LAST N MONTHS
DECLARE @ref_date DATE = (SELECT MAX(order_date) FROM [gold].[fact_sales]);
SELECT DATEPART(YEAR, order_date) AS yr, DATEPART(MONTH, order_date) AS mo,
  SUM(sales_amount) AS total_sales
FROM [gold].[fact_sales]
WHERE order_date >= DATEADD(MONTH, -6, @ref_date)
GROUP BY DATEPART(YEAR, order_date), DATEPART(MONTH, order_date)
ORDER BY yr, mo;

D8. DATE RANGE FILTER (between two dates)
SELECT * FROM [gold].[fact_sales]
WHERE order_date BETWEEN '2013-01-01' AND '2013-12-31'
ORDER BY order_date;

D9. SHIPPING / DELIVERY TIME ANALYSIS
SELECT order_number,
  order_date, shipping_date, due_date,
  DATEDIFF(DAY, order_date, shipping_date) AS days_to_ship,
  DATEDIFF(DAY, order_date, due_date)      AS days_to_due,
  CASE WHEN shipping_date > due_date THEN 'Late' ELSE 'On Time' END AS delivery_status
FROM [gold].[fact_sales]
ORDER BY days_to_ship DESC;

D10. AVERAGE SHIPPING TIME BY YEAR
SELECT DATEPART(YEAR, order_date) AS yr,
  AVG(CAST(DATEDIFF(DAY, order_date, shipping_date) AS FLOAT)) AS avg_days_to_ship
FROM [gold].[fact_sales]
WHERE shipping_date IS NOT NULL
GROUP BY DATEPART(YEAR, order_date)
ORDER BY yr;

D11. ORDERS LATE vs ON TIME COUNT
SELECT
  SUM(CASE WHEN shipping_date > due_date THEN 1 ELSE 0 END) AS late_orders,
  SUM(CASE WHEN shipping_date <= due_date THEN 1 ELSE 0 END) AS on_time_orders,
  COUNT(*) AS total_orders,
  ROUND(CAST(SUM(CASE WHEN shipping_date > due_date THEN 1 ELSE 0 END) AS FLOAT)
    / NULLIF(COUNT(*), 0) * 100, 2) AS late_pct
FROM [gold].[fact_sales]
WHERE shipping_date IS NOT NULL;

D12. CUSTOMER AGE FROM BIRTHDATE
SELECT first_name + ' ' + last_name AS customer,
  birthdate,
  DATEDIFF(YEAR, birthdate, GETDATE()) AS age,
  CASE
    WHEN DATEDIFF(YEAR, birthdate, GETDATE()) < 30 THEN 'Under 30'
    WHEN DATEDIFF(YEAR, birthdate, GETDATE()) BETWEEN 30 AND 45 THEN '30-45'
    WHEN DATEDIFF(YEAR, birthdate, GETDATE()) BETWEEN 46 AND 60 THEN '46-60'
    ELSE 'Over 60'
  END AS age_group
FROM [gold].[dim_customers]
WHERE birthdate IS NOT NULL
ORDER BY age;

D13. SALES BY CUSTOMER AGE GROUP
SELECT
  CASE
    WHEN DATEDIFF(YEAR, c.birthdate, GETDATE()) < 30 THEN 'Under 30'
    WHEN DATEDIFF(YEAR, c.birthdate, GETDATE()) BETWEEN 30 AND 45 THEN '30-45'
    WHEN DATEDIFF(YEAR, c.birthdate, GETDATE()) BETWEEN 46 AND 60 THEN '46-60'
    ELSE 'Over 60'
  END AS age_group,
  COUNT(DISTINCT f.order_number) AS total_orders,
  SUM(f.sales_amount) AS total_sales
FROM [gold].[fact_sales] f
JOIN [gold].[dim_customers] c ON f.customer_key = c.customer_key
WHERE c.birthdate IS NOT NULL
GROUP BY
  CASE
    WHEN DATEDIFF(YEAR, c.birthdate, GETDATE()) < 30 THEN 'Under 30'
    WHEN DATEDIFF(YEAR, c.birthdate, GETDATE()) BETWEEN 30 AND 45 THEN '30-45'
    WHEN DATEDIFF(YEAR, c.birthdate, GETDATE()) BETWEEN 46 AND 60 THEN '46-60'
    ELSE 'Over 60'
  END
ORDER BY total_sales DESC;

D14. HOW LONG AGO LAST ORDER (recency)
SELECT c.first_name + ' ' + c.last_name AS customer,
  MAX(f.order_date) AS last_order_date,
  DATEDIFF(DAY, MAX(f.order_date), (SELECT MAX(order_date) FROM [gold].[fact_sales])) AS days_since_last_order
FROM [gold].[fact_sales] f
JOIN [gold].[dim_customers] c ON f.customer_key = c.customer_key
GROUP BY c.first_name, c.last_name
ORDER BY days_since_last_order DESC;

D15. MONTHLY TREND WITH MONTH NAME
SELECT DATEPART(YEAR, order_date) AS yr,
  DATEPART(MONTH, order_date) AS mo_num,
  DATENAME(MONTH, order_date) AS month_name,
  SUM(sales_amount) AS total_sales
FROM [gold].[fact_sales]
GROUP BY DATEPART(YEAR, order_date), DATEPART(MONTH, order_date), DATENAME(MONTH, order_date)
ORDER BY yr, mo_num;
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


# ── PPT keywords detection ──────────────────────────────────────────────────
_PPT_KEYWORDS = [
    "ppt", "power point", "powerpoint", "presentation", "slide deck",
    "slides", "deck", "pptx", "slide",
]

# ── Report keywords detection ──────────────────────────────────────────────────
_REPORT_KEYWORDS = [
    "prepare report", "generate report", "create report", "make report",
    "build report", "give me report", "write report", "produce report",
    "prepare a report", "generate a report", "create a report",
    "sales report", "customer report", "product report", "revenue report",
    "performance report", "analytics report", "summary report",
    "monthly report", "yearly report", "annual report", "quarterly report",
    "report on", "report for", "full report", "detailed report",
    "executive report", "business report",
]


def is_ppt_request(question: str) -> bool:
    q = question.lower().strip()
    return any(kw in q for kw in _PPT_KEYWORDS)

_REPORT_PLAN_PROMPT = """You are a senior data analyst. The user wants a report from their SQL database.

User request: "{question}"

The database has the following schema (tables, columns, data types):
{schema}

Based ONLY on the tables and columns that actually exist in the schema above,
plan a report as a JSON array of sections. Each section has:
- "heading": section title (string)
- "question": the specific data question this section answers, phrased in plain English (string)

Return ONLY a valid JSON array, no explanation. Example format:
[
  {{"heading": "Overall Summary", "question": "Show total revenue, total orders and total quantity overall"}},
  {{"heading": "Sales by Year", "question": "Show total sales and order count by year"}},
  {{"heading": "Top 10 Customers", "question": "Top 10 customers by total amount spent"}}
]

Plan 4-6 sections relevant to the user's request and grounded in the real schema.
Always include an overview/summary section first.
"""

_REPORT_TITLE_PROMPT = """Given this report request: "{question}"
Return a short, professional report title (5-8 words max). No quotes, no punctuation at end.
Example: "Annual Sales Performance Report 2013-2014"
"""


def is_report_request(question: str) -> bool:
    q = question.lower().strip()
    return any(kw in q for kw in _REPORT_KEYWORDS)


def plan_report_sections(question: str, schema: str = "") -> list:
    """Ask Claude to plan what sections the report should have."""
    import json
    raw = _call_claude(
        messages=[{"role": "user", "content": _REPORT_PLAN_PROMPT.format(question=question, schema=schema)}],
    )
    # Extract JSON array
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("Could not plan report sections.")


def get_report_title(question: str) -> str:
    return _call_claude(
        messages=[{"role": "user", "content": _REPORT_TITLE_PROMPT.format(question=question)}],
    ).strip().strip('"').strip("'")

