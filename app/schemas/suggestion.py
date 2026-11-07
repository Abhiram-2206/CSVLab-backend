from pydantic import BaseModel
from typing import List


class SuggestionItem(BaseModel):
    question: str
    sql: str
    rationale: str


class SuggestionResponse(BaseModel):
    dataset_id: int
    dataset_name: str
    table_name: str
    suggestions: List[SuggestionItem]
