from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "transcription-service"
    app_host: str = "0.0.0.0"
    app_port: int = 8004

    internal_api_key: str
    call_service_internal_url: str

    ymq_endpoint_url: str
    ymq_queue_url: str
    ymq_region: str
    ymq_access_key_id: str
    ymq_secret_access_key: str

    yc_iam_token: str | None = None
    yc_iam_token_source: str = "auto"
    yc_metadata_token_url: str = "http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token"
    yc_metadata_timeout_seconds: float = 5.0
    yc_metadata_refresh_margin_seconds: int = 120

    speechkit_api_version: str = "v3"
    speechkit_folder_id: str | None = None

    speechkit_long_running_url: str
    speechkit_v3_recognize_file_async_url: str = "https://stt.api.cloud.yandex.net/stt/v3/recognizeFileAsync"
    speechkit_v3_get_recognition_url: str = "https://stt.api.cloud.yandex.net/stt/v3/getRecognition"
    speechkit_operation_url: str
    speechkit_model: str = "general"
    speechkit_language: str = "ru-RU"
    speechkit_audio_channel_count: int = 1
    speechkit_raw_results: bool = True
    speechkit_text_normalization_enabled: bool = True
    speechkit_literature_text: bool = False
    speechkit_profanity_filter: bool = False
    speechkit_speaker_labeling_enabled: bool = True
    speechkit_summarization_enabled: bool = True
    speechkit_summarization_model_uri: str = ""
    speechkit_poll_delay_seconds: int = 15
    speechkit_max_attempts: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
