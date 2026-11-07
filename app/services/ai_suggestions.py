import json
import logging
from typing import List, Dict, Any
from app.config import settings
from app.schemas.suggestion import SuggestionItem, SuggestionResponse
from app.services.profiler import sanitize_identifier

logger = logging.getLogger(__name__)


def generate_heuristic_suggestions(
    dataset_name: str,
    table_name: str,
    profile: Dict[str, Any],
) -> List[SuggestionItem]:
    """
    Intelligent fallback suggestion generator based strictly on dataset profile metadata.
    Guarantees 5 useful, pedagogically sound questions and starter SQL queries.
    """
    columns = profile.get("columns", [])
    numeric_cols = [c for c in columns if c.get("type") in ("integer", "float")]
    categorical_cols = [c for c in columns if c.get("type") == "string"]
    datetime_cols = [c for c in columns if c.get("type") == "datetime"]
    null_cols = [c for c in columns if c.get("null_count", 0) > 0]

    suggestions: List[SuggestionItem] = []

    # 1. First glance overview
    suggestions.append(SuggestionItem(
        question=f"What does the first glance of the dataset look like?",
        sql=f"SELECT * FROM {table_name} LIMIT 10;",
        rationale="Inspect initial sample records to understand the structure and column values.",
    ))

    # 2. Aggregation on numeric column with categorical grouping
    if numeric_cols and categorical_cols:
        num = numeric_cols[0]["name"]
        cat = categorical_cols[0]["name"]
        suggestions.append(SuggestionItem(
            question=f"What is the total and average {num} grouped by {cat}?",
            sql=f"SELECT {cat}, COUNT(*) AS count, SUM({num}) AS total_{num}, ROUND(AVG({num}), 2) AS avg_{num} FROM {table_name} GROUP BY {cat} ORDER BY total_{num} DESC LIMIT 10;",
            rationale=f"Shows distribution of {num} across top categories of {cat}.",
        ))
    elif categorical_cols:
        cat = categorical_cols[0]["name"]
        suggestions.append(SuggestionItem(
            question=f"What are the most frequent values in {cat}?",
            sql=f"SELECT {cat}, COUNT(*) AS occurrences FROM {table_name} GROUP BY {cat} ORDER BY occurrences DESC LIMIT 10;",
            rationale=f"Ranks category frequency for {cat}.",
        ))
    elif numeric_cols:
        num = numeric_cols[0]["name"]
        suggestions.append(SuggestionItem(
            question=f"What are the summary metrics for {num}?",
            sql=f"SELECT MIN({num}) AS min_{num}, MAX({num}) AS max_{num}, AVG({num}) AS avg_{num} FROM {table_name};",
            rationale=f"Computes min, max, and average bounds for {num}.",
        ))

    # 3. Extremes / Top records
    if numeric_cols:
        num = numeric_cols[0]["name"]
        suggestions.append(SuggestionItem(
            question=f"What are the top 5 highest records by {num}?",
            sql=f"SELECT * FROM {table_name} ORDER BY {num} DESC LIMIT 5;",
            rationale=f"Highlights outlier or peak performers in {num}.",
        ))
    else:
        suggestions.append(SuggestionItem(
            question=f"How many total records are stored in this dataset?",
            sql=f"SELECT COUNT(*) AS total_rows FROM {table_name};",
            rationale="Verifies complete row count in the loaded table.",
        ))

    # 4. Time series or second category breakdown
    if datetime_cols:
        dt = datetime_cols[0]["name"]
        if numeric_cols:
            num = numeric_cols[0]["name"]
            suggestions.append(SuggestionItem(
                question=f"How does {num} vary over time by {dt}?",
                sql=f"SELECT {dt}, SUM({num}) AS total_{num} FROM {table_name} GROUP BY {dt} ORDER BY {dt} ASC LIMIT 20;",
                rationale=f"Reveals chronological trends over time using {dt}.",
            ))
        else:
            suggestions.append(SuggestionItem(
                question=f"What is the frequency of activity over time by {dt}?",
                sql=f"SELECT {dt}, COUNT(*) AS frequency FROM {table_name} GROUP BY {dt} ORDER BY {dt} ASC LIMIT 20;",
                rationale=f"Identifies time patterns and volume spikes over {dt}.",
            ))
    elif len(categorical_cols) > 1:
        cat2 = categorical_cols[1]["name"]
        suggestions.append(SuggestionItem(
            question=f"What is the breakdown of records by {cat2}?",
            sql=f"SELECT {cat2}, COUNT(*) AS count FROM {table_name} GROUP BY {cat2} ORDER BY count DESC LIMIT 10;",
            rationale=f"Explores category distribution for {cat2}.",
        ))
    elif len(numeric_cols) > 1:
        num2 = numeric_cols[1]["name"]
        suggestions.append(SuggestionItem(
            question=f"What is the distribution of {num2}?",
            sql=f"SELECT MIN({num2}) AS min_val, MAX({num2}) AS max_val, AVG({num2}) AS avg_val FROM {table_name};",
            rationale=f"Calculates summary statistics for {num2}.",
        ))
    else:
        suggestions.append(SuggestionItem(
            question=f"What are the distinct values present in the data?",
            sql=f"SELECT DISTINCT * FROM {table_name} LIMIT 10;",
            rationale="Checks unique variations across all columns.",
        ))

    # 5. Data quality check / missing values
    if null_cols:
        target_null = null_cols[0]["name"]
        suggestions.append(SuggestionItem(
            question=f"Which records have missing values in {target_null}?",
            sql=f"SELECT * FROM {table_name} WHERE {target_null} IS NULL LIMIT 10;",
            rationale=f"Locates dirty or incomplete records in {target_null} for data cleaning.",
        ))
    else:
        suggestions.append(SuggestionItem(
            question="Are there any unexpected nulls or anomalies across key fields?",
            sql=f"SELECT COUNT(*) AS count_of_records FROM {table_name} WHERE 1=1;",
            rationale="Confirms cleanliness and completeness of table records.",
        ))

    return suggestions[:5]


def extract_metadata_for_llm(dataset_name: str, table_name: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    CRITICAL PRIVACY FUNCTION:
    Extracts ONLY structural metadata (table name, column names, column data types, null %, summary stats).
    EXPLICITLY GUARANTEES NO RAW ROW VALUES ARE TRANSMITTED.
    """
    column_metadata = []
    for col in profile.get("columns", []):
        col_summary = {
            "name": col.get("name"),
            "data_type": col.get("type"),
            "null_percentage": col.get("null_percentage"),
            "unique_count": col.get("unique_count"),
        }
        # Only include high-level summary bounds, never individual raw cell rows
        stats = col.get("stats", {})
        if stats:
            if "min" in stats and "max" in stats:
                col_summary["min"] = stats["min"]
                col_summary["max"] = stats["max"]
            if "mean" in stats:
                col_summary["mean"] = stats["mean"]
        column_metadata.append(col_summary)

    return {
        "dataset_name": dataset_name,
        "table_name": table_name,
        "total_rows": profile.get("row_count", 0),
        "columns": column_metadata,
    }


def get_ai_suggestions(
    dataset_name: str,
    dataset_id: int,
    profile: Dict[str, Any],
) -> SuggestionResponse:
    """
    Generate 5 suggested questions and starter SQL queries using Groq API (or heuristic fallback).
    Enforces that only metadata is sent to Groq.
    """
    table_name = sanitize_identifier(dataset_name)
    metadata = extract_metadata_for_llm(dataset_name, table_name, profile)

    if settings.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)

            system_prompt = (
                "You are an expert data analysis mentor helping beginner students learn SQL. "
                "Given dataset schema metadata (table name, column names, column types, and statistical ranges), "
                "suggest exactly 5 insightful, educational exploration questions with starter read-only SQL queries. "
                "Format your response as a valid JSON object with a single key 'suggestions' containing a list of 5 objects, "
                "each having 'question', 'sql', and 'rationale' strings. "
                "Only use SELECT queries with the provided table name and column names."
            )

            user_prompt = (
                f"Dataset metadata (NO raw rows included):\n{json.dumps(metadata, indent=2)}\n\n"
                "Please return 5 starter SQL questions in JSON format."
            )

            completion = client.chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
            )

            content = completion.choices[0].message.content
            parsed = json.loads(content)
            items = []
            for item in parsed.get("suggestions", []):
                items.append(SuggestionItem(
                    question=item.get("question", ""),
                    sql=item.get("sql", f"SELECT * FROM {table_name} LIMIT 10;"),
                    rationale=item.get("rationale", "Exploratory question."),
                ))
            if len(items) == 5:
                return SuggestionResponse(
                    dataset_id=dataset_id,
                    dataset_name=dataset_name,
                    table_name=table_name,
                    suggestions=items,
                )
        except Exception as e:
            logger.warning(f"Groq API call failed or unavailable ({e}); falling back to heuristic engine.")

    # Fallback to intelligent heuristic generator
    heuristic_items = generate_heuristic_suggestions(dataset_name, table_name, profile)
    return SuggestionResponse(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        table_name=table_name,
        suggestions=heuristic_items,
    )
