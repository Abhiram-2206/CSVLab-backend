import logging
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
import app.database
from app.models.dataset import Dataset, DatasetStatus
from app.services.profiler import sanitize_identifier, load_and_profile_csv

logger = logging.getLogger(__name__)


def get_schema_and_table_name(user_id: int, dataset_id: int, dataset_name: str) -> tuple[str, str, str]:
    """
    Returns (schema_name, primary_table_name, friendly_table_name)
    """
    clean_name = sanitize_identifier(dataset_name)
    primary_table = f"ds_{dataset_id}"
    friendly_table = clean_name
    schema_name = f"user_{user_id}"
    return schema_name, primary_table, friendly_table


def load_dataframe_to_db(df: pd.DataFrame, user_id: int, dataset_id: int, dataset_name: str):
    """
    Load profiled DataFrame into the appropriate database schema/table.
    Supports both PostgreSQL (isolated user schemas) and SQLite.
    """
    schema_name, primary_table, friendly_table = get_schema_and_table_name(user_id, dataset_id, dataset_name)
    is_postgres = settings.DATABASE_URL.startswith("postgresql")

    with app.database.engine.begin() as conn:
        if is_postgres:
            # 1. Create user schema if not exists
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";'))
            
            # 2. Write DataFrame to user schema
            df.to_sql(
                name=primary_table,
                con=conn,
                schema=schema_name,
                if_exists="replace",
                index=False,
            )

            # 3. Create friendly view if friendly_table != primary_table
            if friendly_table != primary_table:
                conn.execute(
                    text(f'CREATE OR REPLACE VIEW "{schema_name}"."{friendly_table}" AS SELECT * FROM "{schema_name}"."{primary_table}";')
                )
        else:
            # SQLite path: prefix table name
            sqlite_table = f"{schema_name}__{primary_table}"
            df.to_sql(
                name=sqlite_table,
                con=conn,
                if_exists="replace",
                index=False,
            )
            # Friendly view in SQLite
            if friendly_table != primary_table:
                sqlite_friendly = f"{schema_name}__{friendly_table}"
                conn.execute(text(f'DROP VIEW IF EXISTS "{sqlite_friendly}";'))
                conn.execute(text(f'CREATE VIEW "{sqlite_friendly}" AS SELECT * FROM "{sqlite_table}";'))


def drop_dataset_tables(user_id: int, dataset_id: int, dataset_name: str):
    """Drop the stored tables and views associated with a dataset upon deletion."""
    schema_name, primary_table, friendly_table = get_schema_and_table_name(user_id, dataset_id, dataset_name)
    is_postgres = settings.DATABASE_URL.startswith("postgresql")

    try:
        with app.database.engine.begin() as conn:
            if is_postgres:
                if friendly_table != primary_table:
                    conn.execute(text(f'DROP VIEW IF EXISTS "{schema_name}"."{friendly_table}";'))
                conn.execute(text(f'DROP TABLE IF EXISTS "{schema_name}"."{primary_table}" CASCADE;'))
            else:
                sqlite_friendly = f"{schema_name}__{friendly_table}"
                sqlite_table = f"{schema_name}__{primary_table}"
                conn.execute(text(f'DROP VIEW IF EXISTS "{sqlite_friendly}";'))
                conn.execute(text(f'DROP TABLE IF EXISTS "{sqlite_table}";'))
    except Exception as e:
        logger.warning(f"Error dropping tables for dataset {dataset_id}: {e}")


def process_dataset_background(dataset_id: int):
    """
    Background worker task to profile the CSV and load it into the database.
    Updates dataset status to ready or failed.
    """
    db: Session = app.database.SessionLocal()
    try:
        dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            logger.error(f"Dataset {dataset_id} not found in background task")
            return

        clean_table_name = sanitize_identifier(dataset.name)
        
        # Profile CSV
        df, profile = load_and_profile_csv(
            file_path=dataset.file_path,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            table_name=clean_table_name,
        )

        # Load to database
        load_dataframe_to_db(
            df=df,
            user_id=dataset.owner_id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
        )

        # Update dataset record
        dataset.status = DatasetStatus.READY.value
        dataset.row_count = profile["row_count"]
        dataset.profile = profile
        dataset.error_message = None
        db.commit()
        logger.info(f"Dataset {dataset_id} profiled and loaded successfully ({profile['row_count']} rows)")

    except Exception as exc:
        logger.exception(f"Background processing failed for dataset {dataset_id}: {exc}")
        try:
            db.rollback()
            dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
            if dataset:
                dataset.status = DatasetStatus.FAILED.value
                dataset.error_message = str(exc)
                db.commit()
        except Exception as inner_e:
            logger.error(f"Failed to record failure status for dataset {dataset_id}: {inner_e}")
    finally:
        db.close()
