import math
import os
import uuid
from pathlib import Path
from typing import Optional
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
    Query,
    status,
)
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset, DatasetStatus
from app.schemas.dataset import (
    DatasetResponse,
    DatasetUploadResponse,
    DatasetListResponse,
    ProfileReport,
)
from app.core.dependencies import get_current_user
from app.services.data_loader import process_dataset_background, drop_dataset_tables

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post(
    "/",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a CSV dataset",
    description=(
        "Upload a CSV file (max 10 MB). Validates type and size, creates dataset record with "
        "status 'processing', and initiates asynchronous background profiling and schema loading."
    ),
)
async def upload_dataset(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV file to upload"),
    name: Optional[str] = Form(None, description="Optional custom dataset name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 1. Validate file extension
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format; only .csv files are supported.",
        )

    # 2. Read and validate file size (max 10 MB)
    contents = await file.read()
    file_size = len(contents)
    if file_size > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB.",
        )
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded CSV file is empty.",
        )

    # 3. Determine dataset name
    dataset_name = name.strip() if name and name.strip() else Path(filename).stem

    # 4. Save file to disk
    user_upload_dir = Path(settings.UPLOAD_DIR) / f"user_{current_user.id}"
    user_upload_dir.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{uuid.uuid4().hex}_{Path(filename).name}"
    file_path = user_upload_dir / saved_filename

    with open(file_path, "wb") as f:
        f.write(contents)

    # 5. Create database record
    dataset = Dataset(
        owner_id=current_user.id,
        name=dataset_name,
        original_filename=filename,
        file_path=str(file_path),
        status=DatasetStatus.PROCESSING.value,
        row_count=None,
        profile=None,
        error_message=None,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    # 6. Queue background profiling & loading
    background_tasks.add_task(process_dataset_background, dataset.id)

    return DatasetUploadResponse(
        id=dataset.id,
        name=dataset.name,
        original_filename=dataset.original_filename,
        status=dataset.status,
    )


@router.get(
    "/",
    response_model=DatasetListResponse,
    summary="List my datasets",
    description="Retrieve a paginated list of datasets uploaded by the current authenticated user.",
)
def list_datasets(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Dataset).filter(Dataset.owner_id == current_user.id)
    total = query.count()
    total_pages = max(1, math.ceil(total / page_size))
    items = (
        query.order_by(Dataset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return DatasetListResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.get(
    "/{dataset_id}/",
    response_model=DatasetResponse,
    summary="Get dataset details and status",
    description="Retrieve metadata, loading status ('processing', 'ready', 'failed'), and error message for a dataset.",
)
def get_dataset(
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
    return dataset


@router.get(
    "/{dataset_id}/profile/",
    response_model=ProfileReport,
    summary="Get data-quality report",
    description="Retrieve the automated data quality profile (column types, null %, duplicate counts, summary statistics).",
)
def get_dataset_profile(
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

    if dataset.status == DatasetStatus.PROCESSING.value:
        raise HTTPException(
            status_code=status.HTTP_202_ACCEPTED,
            detail="Dataset is currently being profiled. Please check back shortly.",
        )
    if dataset.status == DatasetStatus.FAILED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Profiling failed for this dataset: {dataset.error_message}",
        )

    if not dataset.profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile data not available for this dataset.",
        )

    return dataset.profile


@router.delete(
    "/{dataset_id}/",
    status_code=status.HTTP_200_OK,
    summary="Delete a dataset and its database table",
    description="Deletes a dataset, drops its isolated database table/schema view, and removes stored files.",
)
def delete_dataset(
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

    # 1. Drop database tables / views
    drop_dataset_tables(
        user_id=current_user.id,
        dataset_id=dataset.id,
        dataset_name=dataset.name,
    )

    # 2. Delete file from filesystem
    try:
        if os.path.exists(dataset.file_path):
            os.remove(dataset.file_path)
    except Exception:
        pass

    # 3. Delete database record
    db.delete(dataset)
    db.commit()

    return {"message": f"Dataset {dataset_id} deleted successfully."}
