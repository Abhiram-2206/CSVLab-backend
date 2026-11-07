import re
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple


def sanitize_identifier(name: str) -> str:
    """
    Sanitize a column or table name to be a safe SQL identifier:
    - Lowercase
    - Replace spaces and non-alphanumeric chars with underscores
    - Prefix with 'col_' if it starts with a number or is an empty string
    - Truncate to 63 chars (PostgreSQL max identifier length)
    """
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        cleaned = "col"
    if cleaned[0].isdigit():
        cleaned = f"col_{cleaned}"
    
    # Check reserved words
    reserved = {
        "select", "from", "where", "group", "order", "table", "user", "schema",
        "create", "drop", "alter", "delete", "insert", "update", "limit", "offset",
        "as", "by", "join", "left", "right", "inner", "outer", "on", "into", "values",
        "default", "null", "true", "false", "and", "or", "not", "case", "when", "then"
    }
    if cleaned in reserved:
        cleaned = f"{cleaned}_col"
    
    return cleaned[:63]


def infer_column_type(series: pd.Series) -> str:
    """Infer high-level column data type for reporting and DB loading."""
    # Check if empty or all null
    non_null = series.dropna()
    if len(non_null) == 0:
        return "string"

    # Boolean check
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    
    # Numeric check
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        # Check if all floats are actually whole numbers
        if (non_null % 1 == 0).all():
            return "integer"
        return "float"

    # Datetime check
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    
    # Try parsing sample strings as datetime
    if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
        sample = non_null.head(20).astype(str)
        # Avoid treating pure numbers as datetime
        if not sample.str.replace(".", "", regex=False).str.isdigit().all():
            try:
                pd.to_datetime(sample, errors="raise", format="mixed")
                return "datetime"
            except Exception:
                pass

    return "string"


def profile_dataframe(df: pd.DataFrame, dataset_id: int, dataset_name: str, table_name: str) -> Dict[str, Any]:
    """
    Analyze DataFrame to produce an in-depth data-quality profile report.
    Returns:
    - row_count, column_count, duplicate_rows
    - Per-column: name, original_name, type, null_count, null_percentage, unique_count, stats
    """
    row_count = int(len(df))
    column_count = int(len(df.columns))
    duplicate_rows = int(df.duplicated().sum())

    columns_profile: List[Dict[str, Any]] = []

    # Track sanitized names to ensure uniqueness
    seen_names = set()

    for col in df.columns:
        original_name = str(col)
        sanitized = sanitize_identifier(original_name)
        
        # Ensure unique column names if duplicates collide after sanitization
        unique_sanitized = sanitized
        counter = 1
        while unique_sanitized in seen_names:
            unique_sanitized = f"{sanitized}_{counter}"
            counter += 1
        seen_names.add(unique_sanitized)

        series = df[col]
        col_type = infer_column_type(series)
        null_count = int(series.isna().sum())
        null_pct = round((null_count / row_count * 100.0) if row_count > 0 else 0.0, 2)
        unique_count = int(series.nunique(dropna=True))

        stats: Dict[str, Any] = {}
        if col_type in ("integer", "float"):
            numeric_series = pd.to_numeric(series, errors="coerce").dropna()
            if len(numeric_series) > 0:
                stats["min"] = float(numeric_series.min()) if col_type == "float" else int(numeric_series.min())
                stats["max"] = float(numeric_series.max()) if col_type == "float" else int(numeric_series.max())
                stats["mean"] = round(float(numeric_series.mean()), 2)
                stats["std"] = round(float(numeric_series.std()), 2) if len(numeric_series) > 1 else 0.0
                stats["median"] = round(float(numeric_series.median()), 2)
        elif col_type == "string":
            # Top 5 most frequent values
            top_vals = series.dropna().astype(str).value_counts().head(5)
            stats["top_values"] = [{"value": val, "count": int(count)} for val, count in top_vals.items()]
        elif col_type == "datetime":
            dt_series = pd.to_datetime(series, errors="coerce").dropna()
            if len(dt_series) > 0:
                stats["min"] = str(dt_series.min())
                stats["max"] = str(dt_series.max())

        columns_profile.append({
            "name": unique_sanitized,
            "original_name": original_name,
            "type": col_type,
            "null_count": null_count,
            "null_percentage": null_pct,
            "unique_count": unique_count,
            "stats": stats,
        })

    return {
        "dataset_id": dataset_id,
        "dataset_name": dataset_name,
        "table_name": table_name,
        "row_count": row_count,
        "column_count": column_count,
        "duplicate_rows": duplicate_rows,
        "columns": columns_profile,
    }


def load_and_profile_csv(
    file_path: str,
    dataset_id: int,
    dataset_name: str,
    table_name: str,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Read CSV file into pandas DataFrame with multiple encoding fallbacks,
    sanitizes column names on the dataframe, and generates the profile report.
    """
    encodings = ["utf-8", "utf-8-sig", "latin1", "cp1252", "iso-8859-1"]
    df = None
    last_err = None

    for enc in encodings:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            break
        except Exception as e:
            last_err = e
            continue

    if df is None:
        raise ValueError(f"Failed to read CSV file with standard encodings: {last_err}")

    profile = profile_dataframe(df, dataset_id, dataset_name, table_name)

    # Rename dataframe columns to their unique sanitized names for database loading
    sanitized_col_names = [col_info["name"] for col_info in profile["columns"]]
    df.columns = sanitized_col_names

    return df, profile
