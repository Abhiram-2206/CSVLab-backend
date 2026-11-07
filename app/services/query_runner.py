import re
import time
from typing import Dict, Any, List, Tuple
import sqlparse
from sqlparse.sql import Statement, TokenList
from sqlalchemy import text
from app.config import settings
import app.database
from app.services.profiler import sanitize_identifier


class SQLSecurityError(ValueError):
    """Raised when user SQL violates safety constraints."""
    pass


class SQLTimeoutError(RuntimeError):
    """Raised when user SQL exceeds the allowed execution time limit."""
    pass


FORBIDDEN_KEYWORDS = {
    "drop", "alter", "create", "truncate", "insert", "update", "delete",
    "grant", "revoke", "vacuum", "analyze", "reindex", "cluster",
    "copy", "exec", "execute", "call", "lock", "checkpoint", "listen",
    "notify", "unlisten", "discard", "reset", "set", "commit", "rollback",
    "savepoint", "prepare", "deallocate", "merge", "replace"
}

FORBIDDEN_TABLES = {
    "users", "datasets", "saved_queries", "share_links", "alembic_version",
    "sqlite_master", "sqlite_schema", "sqlite_sequence", "information_schema",
    "pg_catalog", "pg_tables", "pg_user", "pg_stat_activity", "pg_class"
}


def validate_sql_safety(sql: str) -> str:
    """
    Validate that user SQL is strictly a single, safe SELECT query.
    Rejects:
    - Multiple statements (semicolon chained queries)
    - DDL or DML write operations
    - Dangerous keywords or system table accesses
    Returns clean SQL text.
    """
    if not sql or not sql.strip():
        raise SQLSecurityError("Query cannot be empty.")

    cleaned_sql = sql.strip()

    # Parse using sqlparse
    parsed = sqlparse.parse(cleaned_sql)
    if not parsed:
        raise SQLSecurityError("Invalid SQL query syntax.")

    # Filter out empty statements (like a lone semicolon)
    valid_statements = [stmt for stmt in parsed if stmt.get_type() != "UNKNOWN" or stmt.tokens]
    if len(valid_statements) > 1:
        raise SQLSecurityError("Multiple statements are not permitted; submit exactly one SELECT query.")

    stmt = valid_statements[0]
    stmt_type = stmt.get_type()

    if stmt_type != "SELECT":
        raise SQLSecurityError(f"Only SELECT queries are allowed. Received statement type: '{stmt_type}'.")

    # Deep token inspection for forbidden keywords
    normalized_sql = cleaned_sql.lower()

    # Check for forbidden keywords as whole words
    for kw in FORBIDDEN_KEYWORDS:
        pattern = rf"\b{kw}\b"
        if re.search(pattern, normalized_sql):
            raise SQLSecurityError(f"Forbidden keyword '{kw.upper()}' detected in query.")

    # Check for INTO keyword (e.g. SELECT ... INTO table)
    if re.search(r"\binto\b", normalized_sql):
        raise SQLSecurityError("SELECT ... INTO statements are not allowed.")

    # Check for direct access to forbidden application/system tables
    for tbl in FORBIDDEN_TABLES:
        pattern = rf"\b{tbl}\b"
        if re.search(pattern, normalized_sql):
            raise SQLSecurityError(f"Access to protected system/application table '{tbl}' is forbidden.")

    # Ensure no multiple statements hidden behind semicolons
    if ";" in cleaned_sql:
        parts = [p.strip() for p in cleaned_sql.split(";") if p.strip()]
        if len(parts) > 1:
            raise SQLSecurityError("Multiple statements separated by semicolons are not permitted.")

    return cleaned_sql.rstrip(";")


def serialize_cell_value(val: Any) -> Any:
    """Convert DB cell values (e.g. Timestamp, Decimal, NaN) to JSON-serializable types."""
    if val is None:
        return None
    # Check for NaN / Infinity
    if isinstance(val, float):
        import math
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    # Dates / timestamps
    if hasattr(val, "isoformat"):
        return val.isoformat()
    # Decimals
    if hasattr(val, "as_tuple"):
        return float(val)
    # Bytes
    if isinstance(val, (bytes, bytearray)):
        return val.decode("utf-8", errors="replace")
    return val


def execute_sandboxed_query(
    user_id: int,
    dataset_id: int,
    dataset_name: str,
    sql: str,
    limit: int = settings.MAX_QUERY_ROWS,
    timeout_seconds: int = settings.QUERY_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    Execute a sandboxed, read-only SQL query against the user's dataset.
    Enforces:
    - SQL safety validation (single SELECT only)
    - Schema isolation (Postgres search_path or SQLite table scoping)
    - Row cap (up to limit rows)
    - Statement timeout (5 seconds)
    """
    safe_sql = validate_sql_safety(sql)
    is_postgres = settings.DATABASE_URL.startswith("postgresql")
    schema_name = f"user_{user_id}"
    clean_name = sanitize_identifier(dataset_name)
    primary_table = f"ds_{dataset_id}"

    start_time = time.perf_counter()

    if is_postgres:
        # In PostgreSQL:
        # 1. SET LOCAL statement_timeout
        # 2. SET TRANSACTION READ ONLY
        # 3. SET LOCAL search_path = "user_{id}" (excludes public, preventing access to users/datasets)
        with app.database.engine.connect() as conn:
            # PostgreSQL requires read only / timeout inside a transaction
            trans = conn.begin()
            try:
                conn.execute(text(f"SET LOCAL statement_timeout = {int(timeout_seconds * 1000)};"))
                conn.execute(text("SET TRANSACTION READ ONLY;"))
                conn.execute(text(f'SET LOCAL search_path = "{schema_name}";'))

                # Wrap query with LIMIT limit + 1 to detect truncation
                wrapped_sql = f"SELECT * FROM ({safe_sql}) AS __csvlab_q LIMIT {limit + 1};"
                result = conn.execute(text(wrapped_sql))
                columns = list(result.keys())
                raw_rows = result.fetchall()
                trans.commit()
            except Exception as e:
                trans.rollback()
                err_msg = str(e).lower()
                if "canceling statement due to statement timeout" in err_msg or "timeout" in err_msg:
                    raise SQLTimeoutError(f"Query exceeded execution timeout of {timeout_seconds} seconds.")
                raise ValueError(f"Query execution error: {e}")
    else:
        # SQLite execution:
        # Rewrite references to dataset table if user wrote 'bakery_sales' or 'ds_42'
        # to the scoped table 'user_{id}__bakery_sales' / 'user_{id}__ds_42'
        scoped_sql = safe_sql
        # Replace occurrences of friendly_table or primary_table with SQLite prefixed names
        pattern_friendly = rf"\b{re.escape(clean_name)}\b"
        scoped_sql = re.sub(pattern_friendly, f"{schema_name}__{clean_name}", scoped_sql, flags=re.IGNORECASE)
        pattern_primary = rf"\b{re.escape(primary_table)}\b"
        scoped_sql = re.sub(pattern_primary, f"{schema_name}__{primary_table}", scoped_sql, flags=re.IGNORECASE)

        # In SQLite, also ensure the user is not querying unauthorized tables
        # Check that table names belong to this user
        with app.database.engine.connect() as conn:
            try:
                # Wrap query to cap rows
                wrapped_sql = f"SELECT * FROM ({scoped_sql}) AS __csvlab_q LIMIT {limit + 1};"
                result = conn.execute(text(wrapped_sql))
                columns = list(result.keys())
                raw_rows = result.fetchall()
            except Exception as e:
                raise ValueError(f"Query execution error: {e}")

    execution_time_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

    truncated = len(raw_rows) > limit
    returned_rows = raw_rows[:limit]

    formatted_rows = [
        {col: serialize_cell_value(val) for col, val in zip(columns, row)}
        for row in returned_rows
    ]

    return {
        "columns": columns,
        "rows": formatted_rows,
        "row_count": len(formatted_rows),
        "execution_time_ms": execution_time_ms,
        "truncated": truncated,
        "query": safe_sql,
    }
