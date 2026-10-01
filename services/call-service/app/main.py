from __future__ import annotations

from fastapi import FastAPI

from .config import get_settings
from .db import Base, engine
from .routers import checklists, internal, label_definitions, label_rules, public

app = FastAPI(title="call-service", version="1.0.0")
settings = get_settings()
app.include_router(label_definitions.router)
app.include_router(label_rules.router)
app.include_router(checklists.router)
app.include_router(public.router)
app.include_router(internal.router)


@app.on_event("startup")
def startup() -> None:
    if settings.db_auto_create:
        Base.metadata.create_all(bind=engine)


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    return {"status": "ready"}
