from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict


class ColumnStats(BaseModel):
    min: Optional[Any] = None
    max: Optional[Any] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    median: Optional[float] = None
    top_values: Optional[List[Dict[str, Any]]] = None


class ColumnProfile(BaseModel):
    name: str
    original_name: str
    type: str
    null_count: int
    null_percentage: float
    unique_count: int
    stats: Optional[Dict[str, Any]] = None


class ProfileReport(BaseModel):
    dataset_id: int
    dataset_name: str
    table_name: str
    row_count: int
    column_count: int
    duplicate_rows: int
    columns: List[ColumnProfile]
    created_at: Optional[datetime] = None


class DatasetResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    original_filename: str
    status: str
    row_count: Optional[int] = None
    created_at: datetime
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class DatasetUploadResponse(BaseModel):
    id: int
    name: str
    original_filename: str
    status: str
    message: str = "Dataset uploaded successfully; profiling and loading started in background."


class DatasetListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[DatasetResponse]
