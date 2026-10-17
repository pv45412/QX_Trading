from pathlib import Path

import pytest

from qx.brokers.schwab.config import clear_schwab_env, save_schwab_env
from qx.config.settings import Settings


def test_save_schwab_env_writes_local_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    env_path = tmp_path / ".env"

    save_schwab_env(
        client_id="client",
        client_secret="secret",
        redirect_uri="https://127.0.0.1",
        env_path=env_path,
    )

    content = env_path.read_text(encoding="utf-8")
    assert "QX_SCHWAB_CLIENT_ID=client" in content
    assert "QX_SCHWAB_CLIENT_SECRET=secret" in content
    assert "QX_SCHWAB_REDIRECT_URI=https://127.0.0.1" in content
    assert "QX_SCHWAB_TOKEN_PATH=data/secrets/schwab_token.json" in content
    settings = Settings(_env_file=env_path)
    assert settings.schwab_client_id == "client"
    assert settings.schwab_client_secret == "secret"


def test_save_schwab_env_requires_credentials(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="client ID"):
        save_schwab_env(client_id="", client_secret="secret", env_path=tmp_path / ".env")
    with pytest.raises(ValueError, match="client secret"):
        save_schwab_env(client_id="client", client_secret="", env_path=tmp_path / ".env")


@pytest.mark.parametrize("field", ["client_id", "client_secret"])
def test_save_schwab_env_rejects_line_injection(tmp_path: Path, field: str) -> None:
    values = {"client_id": "client", "client_secret": "secret"}
    values[field] = f"valid\nQX_DATABASE_URL=sqlite:///injected.db"
    env_path = tmp_path / ".env"

    with pytest.raises(ValueError, match="unsupported characters"):
        save_schwab_env(**values, env_path=env_path)

    assert not env_path.exists()


@pytest.mark.parametrize("field", ["client_id", "client_secret", "redirect_uri"])
@pytest.mark.parametrize("value", ["\nvalue", "value\n", "\rvalue", "value\r"])
def test_save_schwab_env_rejects_boundary_line_breaks(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    values = {
        "client_id": "client",
        "client_secret": "secret",
        "redirect_uri": "https://127.0.0.1",
    }
    values[field] = value
    env_path = tmp_path / ".env"

    with pytest.raises(ValueError, match="unsupported characters"):
        save_schwab_env(**values, env_path=env_path)

    assert not env_path.exists()


def test_settings_reads_legacy_scanner_schwab_names(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SCANNER_SCHWAB_CLIENT_ID=legacy-client\n"
        "SCANNER_SCHWAB_CLIENT_SECRET=legacy-secret\n"
        "SCANNER_SCHWAB_REDIRECT_URI=https://127.0.0.1\n"
        "SCANNER_SCHWAB_TOKEN_PATH=data/secrets/schwab_token.json\n"
        "SCANNER_SCHWAB_AUTH_BASE_URL=https://legacy.example/oauth\n"
        "SCANNER_SCHWAB_API_BASE_URL=https://legacy.example\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_path)

    assert settings.schwab_client_id == "legacy-client"
    assert settings.schwab_client_secret == "legacy-secret"
    assert settings.schwab_token_path == Path("data/secrets/schwab_token.json")
    assert settings.schwab_auth_base_url == "https://legacy.example/oauth"
    assert settings.schwab_api_base_url == "https://legacy.example"


def test_qx_schwab_names_take_precedence_over_legacy_names(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SCANNER_SCHWAB_CLIENT_ID=legacy-client\n"
        "QX_SCHWAB_CLIENT_ID=current-client\n"
        "SCANNER_SCHWAB_CLIENT_SECRET=legacy-secret\n"
        "QX_SCHWAB_CLIENT_SECRET=current-secret\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=env_path)

    assert settings.schwab_client_id == "current-client"
    assert settings.schwab_client_secret == "current-secret"


def test_save_migrates_legacy_schwab_names_to_qx(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SCANNER_SCHWAB_CLIENT_ID=legacy-client\n"
        "SCANNER_SCHWAB_CLIENT_SECRET=legacy-secret\n",
        encoding="utf-8",
    )

    save_schwab_env(
        client_id="current-client",
        client_secret="current-secret",
        env_path=env_path,
    )

    content = env_path.read_text(encoding="utf-8")
    assert "QX_SCHWAB_CLIENT_ID=current-client" in content
    assert "QX_SCHWAB_CLIENT_SECRET=current-secret" in content
    assert "SCANNER_SCHWAB_CLIENT_ID" not in content
    assert "SCANNER_SCHWAB_CLIENT_SECRET" not in content
    assert "SCANNER_SCHWAB_REDIRECT_URI" not in content
    assert "SCANNER_SCHWAB_TOKEN_PATH" not in content


def test_clear_removes_both_schwab_name_families(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "QX_SCHWAB_CLIENT_ID=current-client\n"
        "SCANNER_SCHWAB_CLIENT_SECRET=legacy-secret\n"
        "FASTAPI_PORT=8510\n",
        encoding="utf-8",
    )

    clear_schwab_env(env_path)

    assert env_path.read_text(encoding="utf-8") == "FASTAPI_PORT=8510\n"
