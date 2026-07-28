from fastapi import FastAPI
from pydantic import BaseModel


class StatusResponse(BaseModel):
    status: str


app = FastAPI()

@app.get("/", response_model=StatusResponse)
def read_root() -> StatusResponse:
    return {"status": "ok"}