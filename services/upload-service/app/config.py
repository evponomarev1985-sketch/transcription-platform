from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "upload-service"
    app_host: str = "0.0.0.0"
    app_port: int = 8002

    jwt_secret: str
    jwt_algorithm: str = "HS256"

    upload_signing_secret: str

    yc_s3_endpoint: str
    yc_s3_region: str
    yc_s3_bucket: str
    yc_access_key_id: str
    yc_secret_access_key: str

    call_service_internal_url: str
    call_service_internal_api_key: str

    ymq_endpoint_url: str
    ymq_queue_url: str
    ymq_region: str
    ymq_access_key_id: str
    ymq_secret_access_key: str

    upload_max_file_size_bytes: int = 1024 * 1024 * 500


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
