from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DataDrift API"
    app_version: str = "1.0.0"
    database_url: str = "postgresql+psycopg://datadrift:datadrift@localhost:5432/datadrift"
    # A snapshot whose drift score reaches this value is flagged as DRIFT_DETECTED.
    drift_threshold: float = 0.30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
