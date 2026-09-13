from pathlib import Path

from qx.config.settings import Settings


def test_settings_defaults_are_portable() -> None:
    settings = Settings()

    assert settings.environment == "local"
    assert settings.data_provider == "schwab"
    assert settings.database_url == "sqlite:///data/qx.db"
    assert settings.cache_dir == Path("data/cache")
    assert settings.default_universe == "sp500"
