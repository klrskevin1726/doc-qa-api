from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.database import get_db
from models.schemas import StatusResponse


router = APIRouter()


@router.get("/", response_model=StatusResponse)
def get_algo_status() -> StatusResponse:
    return {"status": "ok"}


@router.get("/health", response_model=StatusResponse)
def get_health() -> StatusResponse:
    return {"status": "ok"}


@router.get("/ready", response_model=StatusResponse)
def get_readiness(db: Session = Depends(get_db)) -> StatusResponse:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
    return {"status": "ready"}