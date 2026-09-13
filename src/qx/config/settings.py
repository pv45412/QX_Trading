from pathlib import Path

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
    default_universe: str = "sp500"
    scan_time: str = "16:30"
    schwab_client_id: str = ""
    schwab_client_secret: str = ""
    schwab_redirect_uri: str = "https://127.0.0.1"
    schwab_token_path: Path = Path("data/secrets/schwab_token.json")
    schwab_auth_base_url: str = "https://api.schwabapi.com/v1/oauth"
    schwab_api_base_url: str = "https://api.schwabapi.com"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="QX_",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
