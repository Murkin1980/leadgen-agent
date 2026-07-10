from fastapi import FastAPI

from app.api.admin import admin_router
from app.api.routes import router

app = FastAPI(title="Leadgen Agent", version="0.2.0")
app.include_router(router)
app.include_router(admin_router)
