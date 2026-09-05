from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expires_hours: int = 24
    cookie_secure: bool = False
    # Used to build links that get emailed out (e.g. verification links),
    # since those have to be absolute. Override via APP_BASE_URL in
    # deployed environments.
    app_base_url: str = "http://localhost:8000"


settings = Settings()  # type: ignore[call-arg]