import csv
import io
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset, DatasetStatus
from app.models.query import SavedQuery
from app.schemas.query import (
    QueryExecuteRequest,
    QueryResultResponse,
    SavedQueryCreate,
    SavedQueryUpdate,
    SavedQueryResponse,
    SavedQueryListResponse,
)
from app.core.dependencies import get_current_user
from app.services.query_runner import (
    execute_sandboxed_query,
    validate_sql_safety,
    SQLSecurityError,
    SQLTimeoutError,
)
from app.services.profiler import sanitize_identifier

router = APIRouter(tags=["Queries & Export"])


@router.post(
    "/datasets/{dataset_id}/query/",
    response_model=QueryResultResponse,
    summary="Run a sandboxed read-only SQL query",
    description=(
        "Executes a user-submitted SQL query on their private dataset table. "
        "Strictly enforces single SELECT statements, blocks DDL/DML, caps results to 1,000 rows, "
        "and enforces a 5-second statement timeout."
    ),
)
def run_query(
    dataset_id: int,
    query_in: QueryExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.owner_id == current_user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found.",
        )

    if dataset.status != DatasetStatus.READY.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset is not ready for querying (current status: {dataset.status}).",
        )

    try:
        result = execute_sandboxed_query(
            user_id=current_user.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            sql=query_in.sql,
        )
        return result
    except SQLSecurityError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Security violation: {str(e)}",
        )
    except SQLTimeoutError as e:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected query execution failure: {str(e)}",
        )


@router.post(
    "/datasets/{dataset_id}/queries/",
    response_model=SavedQueryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a query for a dataset",
    description="Saves a SQL query with a title for reuse and sharing.",
)
def create_saved_query(
    dataset_id: int,
    query_in: SavedQueryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.owner_id == current_user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found.",
        )

    # Validate SQL safety and verify that it executes successfully against the dataset
    try:
        clean_sql = validate_sql_safety(query_in.sql_text)
        if dataset.status == DatasetStatus.READY.value:
            execute_sandboxed_query(
                user_id=current_user.id,
                dataset_id=dataset.id,
                dataset_name=dataset.name,
                sql=clean_sql,
                limit=1,
            )
    except (SQLSecurityError, SQLTimeoutError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot save invalid query: {str(e)}",
        )

    saved_query = SavedQuery(
        dataset_id=dataset.id,
        owner_id=current_user.id,
        title=query_in.title,
        sql_text=clean_sql,
    )
    db.add(saved_query)
    db.commit()
    db.refresh(saved_query)
    return saved_query


@router.get(
    "/datasets/{dataset_id}/queries/",
    response_model=SavedQueryListResponse,
    summary="List saved queries for a dataset",
    description="Retrieve all queries saved by the current user for the given dataset.",
)
def list_saved_queries(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.owner_id == current_user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found.",
        )

    queries = (
        db.query(SavedQuery)
        .filter(SavedQuery.dataset_id == dataset_id, SavedQuery.owner_id == current_user.id)
        .order_by(SavedQuery.created_at.desc())
        .all()
    )
    return SavedQueryListResponse(total=len(queries), items=queries)


@router.get(
    "/queries/{query_id}/",
    response_model=SavedQueryResponse,
    summary="Get saved query details",
    description="Retrieve details of a specific saved query.",
)
def get_saved_query(
    query_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(SavedQuery)
        .filter(SavedQuery.id == query_id, SavedQuery.owner_id == current_user.id)
        .first()
    )
    if not query:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved query {query_id} not found.",
        )
    return query


@router.put(
    "/queries/{query_id}/",
    response_model=SavedQueryResponse,
    summary="Update a saved query",
    description="Update title or SQL text of an existing saved query.",
)
def update_saved_query(
    query_id: int,
    query_update: SavedQueryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(SavedQuery)
        .filter(SavedQuery.id == query_id, SavedQuery.owner_id == current_user.id)
        .first()
    )
    if not query:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved query {query_id} not found.",
        )

    if query_update.title is not None:
        query.title = query_update.title
    if query_update.sql_text is not None:
        try:
            clean_sql = validate_sql_safety(query_update.sql_text)
            dataset = db.query(Dataset).filter(Dataset.id == query.dataset_id).first()
            if dataset and dataset.status == DatasetStatus.READY.value:
                execute_sandboxed_query(
                    user_id=current_user.id,
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    sql=clean_sql,
                    limit=1,
                )
            query.sql_text = clean_sql
        except (SQLSecurityError, SQLTimeoutError, ValueError) as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot save invalid query: {str(e)}",
            )

    db.commit()
    db.refresh(query)
    return query


@router.delete(
    "/queries/{query_id}/",
    status_code=status.HTTP_200_OK,
    summary="Delete a saved query",
    description="Deletes a saved query owned by the current user.",
)
def delete_saved_query(
    query_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(SavedQuery)
        .filter(SavedQuery.id == query_id, SavedQuery.owner_id == current_user.id)
        .first()
    )
    if not query:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Saved query {query_id} not found.",
        )
    db.delete(query)
    db.commit()
    return {"message": f"Saved query {query_id} deleted successfully."}


@router.get(
    "/datasets/{dataset_id}/export/",
    summary="Export query result as CSV",
    description="Executes a safe read-only SQL query or saved query and downloads the result as a CSV file.",
)
def export_query_csv(
    dataset_id: int,
    sql: Optional[str] = Query(None, description="Raw SELECT query to export"),
    query_id: Optional[int] = Query(None, description="Optional saved query ID to export"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dataset = (
        db.query(Dataset)
        .filter(Dataset.id == dataset_id, Dataset.owner_id == current_user.id)
        .first()
    )
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with ID {dataset_id} was not found.",
        )

    if dataset.status != DatasetStatus.READY.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset is not ready for querying (status: {dataset.status}).",
        )

    query_to_run = sql
    if not query_to_run and query_id is not None:
        saved_q = (
            db.query(SavedQuery)
            .filter(SavedQuery.id == query_id, SavedQuery.owner_id == current_user.id)
            .first()
        )
        if not saved_q:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Saved query {query_id} not found.",
            )
        query_to_run = saved_q.sql_text

    if not query_to_run:
        clean_name = sanitize_identifier(dataset.name)
        query_to_run = f"SELECT * FROM {clean_name}"

    try:
        result = execute_sandboxed_query(
            user_id=current_user.id,
            dataset_id=dataset.id,
            dataset_name=dataset.name,
            sql=query_to_run,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to execute export query: {str(e)}",
        )

    columns = result["columns"]
    rows = result["rows"]

    # Generate CSV stream
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)

    output.seek(0)
    export_filename = f"{sanitize_identifier(dataset.name)}_export.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{export_filename}"'},
    )
