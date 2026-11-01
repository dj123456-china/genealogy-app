from contextlib import asynccontextmanager
import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.guides import router as guides_router
from app.api.routes.family import router as family_router
from app.api.routes.assets import router as assets_router
from app.api.routes.notifications import router as notifications_router
from app.api.routes.wechat import router as wechat_router
from app.api.routes.invite_codes import router as invite_codes_router
from app.services.notifications import notification_scheduler
from app.core.config import settings
from app.db.session import Base, engine, ensure_database, ensure_schema
from app.models import User  # noqa: F401 - ensure all models are registered


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_database()
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    stop = asyncio.Event()
    scheduler = None
    if os.getenv('NOTIFICATION_SCHEDULER_ENABLED', 'true').lower() not in {'false', '0', 'no'}:
        scheduler = asyncio.create_task(notification_scheduler(stop))
    try:
        yield
    finally:
        stop.set()
        if scheduler:
            try:
                await asyncio.wait_for(scheduler, timeout=15)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                scheduler.cancel()


app = FastAPI(title="家谱 App API", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router, prefix="/api")
app.include_router(guides_router, prefix="/api")
app.include_router(family_router, prefix="/api")
app.include_router(assets_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(wechat_router, prefix="/api")
app.include_router(invite_codes_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# 包裹完整应用，让未处理异常产生的 500 响应也携带 CORS 头。
app = CORSMiddleware(
    app,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
