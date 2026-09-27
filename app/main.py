from fastapi import FastAPI

from app.api.admin import admin_router
from app.api.admin_messages_secure import router as secure_admin_messages_router
from app.api.admin_recovery import recovery_router
from app.api.outreach_routes import router as outreach_router
from app.api.production_routes import router as production_router
from app.api.routes import router
from app.api.whatsapp_routes import router as whatsapp_router

app = FastAPI(title="Leadgen Agent", version="0.7.0")
app.include_router(router)
app.include_router(outreach_router)
app.include_router(whatsapp_router)
# Secure routes must be registered before the legacy admin router because
# Starlette resolves duplicate paths in registration order.
app.include_router(secure_admin_messages_router)
app.include_router(admin_router)
app.include_router(recovery_router)
app.include_router(production_router, prefix="/api/v1", tags=["phase07"])
