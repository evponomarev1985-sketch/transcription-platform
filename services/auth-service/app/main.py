from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import select

from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import User, UserRole
from .routers import admin, auth
from .security import hash_password

settings = get_settings()
app = FastAPI(title="auth-service", version="1.0.0")

app.include_router(auth.router)
app.include_router(admin.router)


@app.on_event("startup")
def startup() -> None:
    if settings.db_auto_create:
        Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin_user = db.execute(select(User).where(User.login == settings.auth_bootstrap_admin_login)).scalar_one_or_none()
        if not admin_user and settings.auth_bootstrap_admin_password:
            db.add(
                User(
                    login=settings.auth_bootstrap_admin_login,
                    password_hash=hash_password(settings.auth_bootstrap_admin_password),
                    role=UserRole.ADMIN,
                    is_active=True,
                    is_blocked=False,
                )
            )
            db.commit()
    finally:
        db.close()


@app.get("/health/live")
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready() -> dict[str, str]:
    return {"status": "ready"}
