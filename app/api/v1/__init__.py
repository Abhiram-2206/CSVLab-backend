from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.datasets import router as datasets_router
from app.api.v1.queries import router as queries_router
from app.api.v1.suggestions import router as suggestions_router
from app.api.v1.shares import router as shares_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(datasets_router)
api_router.include_router(queries_router)
api_router.include_router(suggestions_router)
api_router.include_router(shares_router)
