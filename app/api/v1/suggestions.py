from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset, DatasetStatus
from app.schemas.suggestion import SuggestionResponse
from app.core.dependencies import get_current_user
from app.services.ai_suggestions import get_ai_suggestions

router = APIRouter(prefix="/datasets", tags=["AI Suggestions"])


@router.post(
    "/{dataset_id}/suggestions/",
    response_model=SuggestionResponse,
    summary="Get AI-suggested exploratory questions and starter SQL",
    description=(
        "Generates 5 thoughtful exploratory data questions and starter read-only SQL queries "
        "powered by LLM metadata analysis. CRITICAL PRIVACY: Only dataset schema, column types, "
        "and summary metrics are analyzed; NO raw data rows are ever transmitted."
    ),
)
def get_dataset_suggestions(
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

    if dataset.status != DatasetStatus.READY.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset is not ready (status: {dataset.status}). Suggestions require completed profiling.",
        )

    if not dataset.profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset profile is missing; cannot generate suggestions without schema metadata.",
        )

    return get_ai_suggestions(
        dataset_name=dataset.name,
        dataset_id=dataset.id,
        profile=dataset.profile,
    )
