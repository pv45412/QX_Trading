from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    environment: str = "local"
    log_level: str = "INFO"
    input_dir: Path = Path("data/raw")
    output_dir: Path = Path("data/processed")
    cache_dir: Path = Path("data/cache")
    data_provider: str = "schwab"
    database_url: str = "sqlite:///data/qx.db"
    runtime_database_path: Path = Field(
        default=Path("data/scanner_history.db"),
        validation_alias=AliasChoices(
            "QX_RUNTIME_DATABASE_PATH",
            "SCANNER_RUNTIME_DATABASE_PATH",
        ),
    )
    opportunity_command_reconciliation_seconds: int = Field(default=300, ge=1)
    default_universe: str = "sp500"
    scan_time: str = "16:30"
    schwab_client_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "QX_SCHWAB_CLIENT_ID",
            "SCANNER_SCHWAB_CLIENT_ID",
        ),
    )
    schwab_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices(
            "QX_SCHWAB_CLIENT_SECRET",
            "SCANNER_SCHWAB_CLIENT_SECRET",
        ),
    )
    schwab_redirect_uri: str = Field(
        default="https://127.0.0.1",
        validation_alias=AliasChoices(
            "QX_SCHWAB_REDIRECT_URI",
            "SCANNER_SCHWAB_REDIRECT_URI",
        ),
    )
    schwab_token_path: Path = Field(
        default=Path("data/secrets/schwab_token.json"),
        validation_alias=AliasChoices(
            "QX_SCHWAB_TOKEN_PATH",
            "SCANNER_SCHWAB_TOKEN_PATH",
        ),
    )
    schwab_auth_base_url: str = Field(
        default="https://api.schwabapi.com/v1/oauth",
        validation_alias=AliasChoices(
            "QX_SCHWAB_AUTH_BASE_URL",
            "SCANNER_SCHWAB_AUTH_BASE_URL",
        ),
    )
    schwab_api_base_url: str = Field(
        default="https://api.schwabapi.com",
        validation_alias=AliasChoices(
            "QX_SCHWAB_API_BASE_URL",
            "SCANNER_SCHWAB_API_BASE_URL",
        ),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="QX_",
        extra="ignore",
        populate_by_name=True,
    )


def get_settings() -> Settings:
    return Settings()
