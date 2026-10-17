from pathlib import Path

from qx.config.settings import Settings


def test_settings_defaults_are_portable() -> None:
    settings = Settings()

    assert settings.environment == "local"
    assert settings.data_provider == "schwab"
    assert settings.database_url == "sqlite:///data/qx.db"
    assert settings.runtime_database_path == Path("data/scanner_history.db")
    assert settings.cache_dir == Path("data/cache")
    assert settings.default_universe == "sp500"


def test_runtime_database_path_has_one_typed_environment_override(monkeypatch) -> None:
    monkeypatch.setenv("QX_RUNTIME_DATABASE_PATH", "data/custom_runtime.db")
    assert Settings().runtime_database_path == Path("data/custom_runtime.db")
