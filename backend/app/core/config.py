from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_seed_defaults: bool = False
    event_timezone: str = "Europe/Madrid"

    database_url: str = "postgresql+psycopg://bss_timecollection:change-me@db:5432/bss_timecollection"

    oracle_enabled: bool = False
    oracle_base_url: str = ""
    oracle_api_path: str = "/hcmRestApi/resources/11.13.18.05/timeEventRequests"
    oracle_source_id: str = "HWM_CLOCK_TIME"
    oracle_auth_mode: str = "none"
    oracle_username: str = ""
    oracle_password: str = ""
    oracle_bearer_token: str = ""
    oracle_timeout_seconds: float = 15.0

    worker_poll_seconds: float = 3.0
    worker_stale_sending_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
