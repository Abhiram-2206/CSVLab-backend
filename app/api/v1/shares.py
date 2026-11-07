import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.dataset import Dataset, DatasetStatus
from app.models.query import SavedQuery
from app.models.share import ShareLink
from app.schemas.share import (
    ShareCreateRequest,
    ShareResponse,
    SharedViewResponse,
)
from app.schemas.query import SavedQueryResponse, QueryResultResponse
from app.core.dependencies import get_current_user
from app.services.query_runner import execute_sandboxed_query

router = APIRouter(tags=["Sharing"])


@router.post(
    "/datasets/{dataset_id}/share/",
    response_model=ShareResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a read-only share link",
    description="Generates a unique, secure read-only token to share a dataset and optionally a saved query with mentors or peers.",
)
def create_share_link(
    dataset_id: int,
    share_in: ShareCreateRequest,
    request: Request,
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

    if share_in.query_id:
        query = (
            db.query(SavedQuery)
            .filter(
                SavedQuery.id == share_in.query_id,
                SavedQuery.dataset_id == dataset.id,
                SavedQuery.owner_id == current_user.id,
            )
            .first()
        )
        if not query:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Saved query {share_in.query_id} not found for this dataset.",
            )

    token = secrets.token_urlsafe(32)
    share_link = ShareLink(
        dataset_id=dataset.id,
        query_id=share_in.query_id,
        token=token,
    )
    db.add(share_link)
    db.commit()
    db.refresh(share_link)

    base_url = str(request.base_url).rstrip("/")
    share_url = f"{base_url}/api/v1/shared/{token}/"

    return ShareResponse(
        token=share_link.token,
        dataset_id=share_link.dataset_id,
        query_id=share_link.query_id,
        created_at=share_link.created_at,
        share_url=share_url,
    )


@router.delete(
    "/shares/{token}/",
    status_code=status.HTTP_200_OK,
    summary="Revoke a share link",
    description="Revokes an active share link so that subsequent visits return 404.",
)
def revoke_share_link(
    token: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    share_link = db.query(ShareLink).filter(ShareLink.token == token).first()
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found.",
        )

    # Check ownership of the dataset being shared
    dataset = db.query(Dataset).filter(Dataset.id == share_link.dataset_id).first()
    if not dataset or dataset.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to revoke this share link.",
        )

    if share_link.revoked_at is not None:
        return {"message": "Share link is already revoked."}

    share_link.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"message": "Share link revoked successfully."}


@router.get(
    "/shared/{token}/",
    response_model=SharedViewResponse,
    summary="View a shared dataset or query result",
    description="Public, unauthenticated read-only endpoint for mentors or reviewers to view shared data quality profiles and saved query results.",
)
def view_shared_dataset(token: str, db: Session = Depends(get_db)):
    share_link = (
        db.query(ShareLink)
        .filter(ShareLink.token == token, ShareLink.revoked_at.is_(None))
        .first()
    )
    if not share_link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared link is invalid or has been revoked.",
        )

    dataset = db.query(Dataset).filter(Dataset.id == share_link.dataset_id).first()
    if not dataset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The dataset linked to this share link no longer exists.",
        )

    saved_query_resp = None
    query_result_resp = None

    if share_link.query_id:
        query = db.query(SavedQuery).filter(SavedQuery.id == share_link.query_id).first()
        if query:
            saved_query_resp = SavedQueryResponse.model_validate(query)
            # Run the query in read-only sandbox
            try:
                raw_result = execute_sandboxed_query(
                    user_id=dataset.owner_id,
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    sql=query.sql_text,
                )
                query_result_resp = QueryResultResponse(**raw_result)
            except Exception:
                pass

    return SharedViewResponse(
        token=share_link.token,
        dataset_id=dataset.id,
        dataset_name=dataset.name,
        status=dataset.status,
        row_count=dataset.row_count,
        profile=dataset.profile,
        saved_query=saved_query_resp,
        query_result=query_result_resp,
        created_at=share_link.created_at,
    )
