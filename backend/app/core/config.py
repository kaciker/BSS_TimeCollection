from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_seed_defaults: bool = False
    event_timezone: str = "Europe/Madrid"

    database_url: str = "postgresql+psycopg://bss_timecollection:change-me@db:5432/bss_timecollection"
    database_admin_test_enabled: bool = False

    oracle_enabled: bool = False
    oracle_base_url: str = ""
    oracle_api_path: str = "/hcmRestApi/resources/11.13.18.05/timeEventRequests"
    oracle_source_id: str = "HWM_CLOCK_TIME"
    oracle_reporter_id_type: str = "BADGE"
    oracle_auth_mode: str = "none"
    oracle_username: str = ""
    oracle_password: str = ""
    oracle_bearer_token: str = ""
    oracle_timeout_seconds: float = 15.0

    terminal_cookie_secure: bool = False
    terminal_session_days: int = 365
    terminal_pairing_minutes: int = 10

    admin_username: str = "admin"
    admin_password_hash: str = ""
    admin_session_secret: str = ""
    admin_session_hours: int = 8
    admin_cookie_secure: bool = False
    admin_login_max_attempts: int = 5
    admin_login_window_seconds: int = 300

    perimeter_sqlserver_credentials_file: str = "/run/secrets/perimeter_sqlserver.json"
    perimeter_external_max_age_hours: int = 12
    perimeter_external_sync_seconds: float = 30.0
    perimeter_external_sync_batch_size: int = 500

    worker_poll_seconds: float = 3.0
    worker_stale_sending_seconds: int = 300

    operational_metrics_token: str = ""
    operational_statement_timeout_ms: int = 750
    worker_heartbeat_seconds: int = 10
    worker_heartbeat_stale_seconds: int = 45

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
