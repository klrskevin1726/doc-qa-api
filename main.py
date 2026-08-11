from fastapi import FastAPI
from routers.health_router import router as health_router
from routers.auth import router as auth_router


app = FastAPI()
app. include_router(health_router)
app.include_router(auth_router)