from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "call-service"
    app_host: str = "0.0.0.0"
    app_port: int = 8003
    db_auto_create: bool = False

    database_url: str

    jwt_secret: str
    jwt_algorithm: str = "HS256"

    internal_api_key: str

    yc_s3_endpoint: str
    yc_s3_region: str
    yc_s3_bucket: str
    yc_access_key_id: str
    yc_secret_access_key: str

    ymq_endpoint_url: str
    ymq_queue_url: str
    ymq_region: str
    ymq_access_key_id: str
    ymq_secret_access_key: str

    # YandexGPT for validate-prompt (same IAM token source as transcription-service)
    yc_iam_token: str = ""
    yc_iam_token_source: str = "metadata"  # "metadata" | "env"
    yc_metadata_token_url: str = "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token"
    yandexgpt_folder_id: str = ""
    yandexgpt_model_uri: str = ""
    yandexgpt_api_url: str = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
