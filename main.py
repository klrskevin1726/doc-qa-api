from fastapi import FastAPI
from routers.health_router import router as health_router
from routers.auth import router as auth_router
from routers.documents import router as documents_router

app = FastAPI()
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(documents_router)