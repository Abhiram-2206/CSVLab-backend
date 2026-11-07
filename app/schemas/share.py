from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.schemas.query import SavedQueryResponse, QueryResultResponse


class ShareCreateRequest(BaseModel):
    query_id: Optional[int] = None


class ShareResponse(BaseModel):
    token: str
    dataset_id: int
    query_id: Optional[int] = None
    created_at: datetime
    share_url: str

    model_config = {"from_attributes": True}


class SharedViewResponse(BaseModel):
    token: str
    dataset_id: int
    dataset_name: str
    status: str
    row_count: Optional[int] = None
    profile: Optional[Dict[str, Any]] = None
    saved_query: Optional[SavedQueryResponse] = None
    query_result: Optional[QueryResultResponse] = None
    created_at: datetime
