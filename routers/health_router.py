from fastapi import APIRouter
from models.schemas import StatusResponse   


router = APIRouter()
@router.get("/", response_model=StatusResponse)
def get_algo_status() -> StatusResponse:
    return {"status": "ok"}