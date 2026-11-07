from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class QueryExecuteRequest(BaseModel):
    sql: str = Field(..., description="Read-only single SELECT query to execute on the dataset")


class QueryResultResponse(BaseModel):
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    execution_time_ms: float
    truncated: bool = False
    query: Optional[str] = None


class SavedQueryCreate(BaseModel):
    title: str = Field(..., max_length=255)
    sql_text: str = Field(...)


class SavedQueryUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    sql_text: Optional[str] = None


class SavedQueryResponse(BaseModel):
    id: int
    dataset_id: int
    owner_id: int
    title: str
    sql_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class SavedQueryListResponse(BaseModel):
    total: int
    items: List[SavedQueryResponse]
