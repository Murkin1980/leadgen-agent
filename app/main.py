from fastapi import FastAPI

from app.api.admin import admin_router
from app.api.outreach_routes import router as outreach_router
from app.api.production_routes import router as production_router
from app.api.routes import router
from app.api.whatsapp_routes import router as whatsapp_router

app = FastAPI(title="Leadgen Agent", version="0.7.0")
app.include_router(router)
app.include_router(outreach_router)
app.include_router(whatsapp_router)
app.include_router(admin_router)
app.include_router(production_router, prefix="/api/v1", tags=["phase07"])
