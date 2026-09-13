from pathlib import Path

import pytest

from qx.brokers.schwab.config import save_schwab_env


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
    assert "SCANNER_SCHWAB_CLIENT_ID=client" in content
    assert "SCANNER_SCHWAB_CLIENT_SECRET=secret" in content
    assert "SCANNER_SCHWAB_REDIRECT_URI=https://127.0.0.1" in content
    assert (tmp_path / "data" / "secrets").exists()


def test_save_schwab_env_requires_credentials(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="client ID"):
        save_schwab_env(client_id="", client_secret="secret", env_path=tmp_path / ".env")
    with pytest.raises(ValueError, match="client secret"):
        save_schwab_env(client_id="client", client_secret="", env_path=tmp_path / ".env")
