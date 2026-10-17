from qx.config.settings import Settings
from qx.market.ai_review import AIReviewer


def test_unit_settings_do_not_load_repository_dotenv():
    settings = Settings()

    assert settings.schwab_client_id == ""
    assert settings.schwab_client_secret == ""
    assert settings.schwab_redirect_uri == "https://127.0.0.1"


def test_explicit_test_env_file_remains_supported(tmp_path):
    env_file = tmp_path / "explicit-test.env"
    env_file.write_text("QX_ENVIRONMENT=isolated-test\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.environment == "isolated-test"


def test_ai_reviewer_defaults_to_disabled_without_local_dotenv():
    status = AIReviewer().status()

    assert status["enabled"] is False
    assert status["configured"] is False
