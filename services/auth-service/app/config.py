from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "auth-service"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    db_auto_create: bool = False

    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30

    auth_registration_enabled: bool = False
    auth_bootstrap_admin_login: str = "admin"
    auth_bootstrap_admin_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
