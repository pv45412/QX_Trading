from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qx.brokers.schwab.auth import SchwabToken, SchwabTokenManager, SchwabTokenStore
from qx.brokers.schwab.config import save_schwab_env
from qx.brokers.schwab.health import SchwabHealthCheck
from qx.config.settings import Settings
from qx.data import factory
from qx.interfaces.schwab_system import (
    SchwabCredentialRequest,
    SchwabSystemService,
    create_schwab_system_router,
)
from qx.interfaces.web import create_app


class SuccessfulTokenResponse:
    status_code = 200
    text = ""

    def json(self) -> dict[str, Any]:
        return {
            "access_token": "access-value",
            "refresh_token": "refresh-value",
            "expires_in": 1800,
            "refresh_token_expires_in": 604800,
            "token_type": "Bearer",
        }


class SuccessfulTokenClient:
    def post(self, *args: object, **kwargs: object) -> SuccessfulTokenResponse:
        return SuccessfulTokenResponse()


def _credentials() -> dict[str, str]:
    return {
        "client_id": "local-client-1234",
        "client_secret": "not-a-real-secret-value",
        "redirect_uri": "https://127.0.0.1",
    }


def _settings_loader(env_path: Path, token_path: Path) -> Callable[[], Settings]:
    return lambda: Settings(_env_file=env_path, schwab_token_path=token_path)


def _service(tmp_path: Path, **kwargs: object) -> SchwabSystemService:
    env_path = tmp_path / ".env"
    token_path = tmp_path / "data/secrets/schwab_token.json"
    return SchwabSystemService(
        env_path=env_path,
        token_path=token_path,
        settings_loader=_settings_loader(env_path, token_path),
        **kwargs,
    )


def _client(tmp_path: Path, service: SchwabSystemService | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(create_schwab_system_router(service or _service(tmp_path)))
    return TestClient(app)


def _save_env(tmp_path: Path) -> None:
    save_schwab_env(**_credentials(), env_path=tmp_path / ".env")


def test_credential_api_never_returns_client_secret(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json=_credentials(),
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "configured",
        "client_id_last4",
        "redirect_uri",
        "oauth_status",
        "refresh_token_status",
        "provider_health",
        "last_verified_at",
    }
    assert "client_secret" not in response.text
    assert response.json()["client_id_last4"] == "1234"


def test_invalid_credential_request_never_echoes_client_secret(tmp_path):
    client = _client(tmp_path)
    submitted_secret = "validation-secret-must-not-return"

    response = client.post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json={
            "client_id": "local-client",
            "client_secret": {"invalid": submitted_secret},
            "redirect_uri": "https://127.0.0.1",
        },
    )

    assert response.status_code == 422
    assert submitted_secret not in response.text


def test_credential_api_rejects_env_injection_without_echoing_secret(tmp_path):
    client = _client(tmp_path)
    submitted_secret = "valid\nQX_DATABASE_URL=sqlite:///injected.db"

    response = client.post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json={**_credentials(), "client_secret": submitted_secret},
    )

    assert response.status_code == 400
    assert submitted_secret not in response.text
    assert not (tmp_path / ".env").exists()


def test_invalid_callback_request_never_echoes_callback(tmp_path):
    client = _client(tmp_path)
    callback = "https://127.0.0.1/?code=must-not-return"

    response = client.post(
        "/api/system/schwab/oauth-exchange",
        headers={"X-QX-Local": "1"},
        json={"callback_url": {"invalid": callback}},
    )

    assert response.status_code == 422
    assert callback not in response.text


def test_full_application_includes_local_schwab_status_route(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    app = create_app(
        tmp_path / "qx.db",
        tmp_path / "bars",
        configure_canonical_providers=False,
    )

    response = TestClient(app).get("/api/system/schwab/credentials/status")

    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_credential_mutations_require_local_confirmation_header(tmp_path):
    response = _client(tmp_path).post(
        "/api/system/schwab/credentials",
        json=_credentials(),
    )

    assert response.status_code == 403


def test_redirect_uri_must_remain_https_loopback(tmp_path):
    payload = _credentials()
    payload["redirect_uri"] = "https://example.com/callback"

    response = _client(tmp_path).post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json=payload,
    )

    assert response.status_code == 400
    assert "secret" not in response.text.lower()


def test_oauth_url_reuses_existing_token_manager_generator(tmp_path):
    _save_env(tmp_path)

    response = _client(tmp_path).get("/api/system/schwab/oauth-url")

    assert response.status_code == 200
    assert response.json()["authorization_url"].startswith(
        "https://api.schwabapi.com/v1/oauth/authorize?"
    )
    assert "not-a-real-secret-value" not in response.text
    assert response.json()["security_mode"] == "MANUAL_LOCAL_CALLBACK_NO_STATE"


def test_callback_uses_existing_exchange_and_is_not_persisted(tmp_path):
    _save_env(tmp_path)
    service = _service(tmp_path)
    manager = SchwabTokenManager(service.settings, http_client=SuccessfulTokenClient())

    def healthy(active_manager: SchwabTokenManager) -> SchwabHealthCheck:
        return SchwabHealthCheck(active_manager.status(), True, "ready")

    service.health_check = healthy
    service.manager = lambda: manager  # type: ignore[method-assign]
    client = _client(tmp_path, service)
    callback = "https://127.0.0.1/?code=temporary-code%40&session=temporary-session"

    response = client.post(
        "/api/system/schwab/oauth-exchange",
        headers={"X-QX-Local": "1"},
        json={"callback_url": callback},
    )

    token_path = service.settings().schwab_token_path
    assert response.status_code == 200
    assert response.json()["oauth_status"] == "AUTHENTICATED"
    assert response.json()["refresh_token_status"] == "VALID"
    assert response.json()["provider_health"] == "HEALTHY"
    assert callback not in (tmp_path / ".env").read_text(encoding="utf-8")
    assert callback not in token_path.read_text(encoding="utf-8")


def test_clear_removes_env_credentials_and_existing_token(tmp_path):
    _save_env(tmp_path)
    service = _service(tmp_path)
    token_path = service.settings().schwab_token_path
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("token", encoding="utf-8")

    response = _client(tmp_path, service).delete(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
    )

    assert response.status_code == 200
    assert response.json()["configured"] is False
    env_content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "QX_SCHWAB_CLIENT_ID" not in env_content
    assert "QX_SCHWAB_CLIENT_SECRET" not in env_content
    assert not token_path.exists()


def test_credential_rotation_invalidates_existing_token(tmp_path):
    service = _service(tmp_path)
    client = _client(tmp_path, service)
    assert client.post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json=_credentials(),
    ).status_code == 200
    token_path = service.settings().schwab_token_path
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("old-token", encoding="utf-8")
    replacement = _credentials()
    replacement["client_id"] = "replacement-client-5678"

    response = client.post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json=replacement,
    )

    assert response.status_code == 200
    assert not token_path.exists()
    assert response.json()["oauth_status"] == "UNAUTHENTICATED"


def test_token_invalidation_failure_does_not_persist_rotated_credentials(
    monkeypatch,
    tmp_path,
):
    _save_env(tmp_path)
    service = _service(tmp_path)
    token_path = service.settings().schwab_token_path
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("old-token", encoding="utf-8")
    original_env = (tmp_path / ".env").read_text(encoding="utf-8")
    original_unlink = Path.unlink

    def fail_token_unlink(path: Path, *args: object, **kwargs: object) -> None:
        if path == token_path:
            raise OSError("simulated token deletion failure")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_token_unlink)
    replacement = _credentials()
    replacement["client_id"] = "replacement-client-5678"

    response = _client(tmp_path, service).post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json=replacement,
    )

    assert response.status_code == 400
    assert (tmp_path / ".env").read_text(encoding="utf-8") == original_env
    assert token_path.read_text(encoding="utf-8") == "old-token"


def test_identical_credentials_preserve_existing_token(tmp_path):
    _save_env(tmp_path)
    service = _service(tmp_path)
    token_path = service.settings().schwab_token_path
    token_path.parent.mkdir(parents=True, exist_ok=True)
    SchwabTokenStore(token_path).save(
        SchwabToken(
            access_token="access",
            refresh_token="refresh",
            access_token_expires_at=datetime.now(UTC) + timedelta(minutes=20),
            refresh_token_expires_at=datetime.now(UTC) + timedelta(days=5),
        )
    )

    response = _client(tmp_path, service).post(
        "/api/system/schwab/credentials",
        headers={"X-QX-Local": "1"},
        json=_credentials(),
    )

    assert response.status_code == 200
    assert token_path.exists()
    assert response.json()["oauth_status"] == "AUTHENTICATED"


def test_dynamic_token_manager_reloads_saved_env_credentials(tmp_path):
    service = _service(tmp_path)
    manager = SchwabTokenManager(service.settings)

    assert manager.status().configured is False
    service.save(SchwabCredentialRequest(**_credentials()))

    assert manager.status().configured is True
    assert "authorize" in manager.authorization_url()


def test_canonical_client_uses_dynamic_settings_provider(monkeypatch):
    settings = Settings()
    monkeypatch.setattr(factory, "get_settings", lambda: settings)
    client = factory._schwab_client()

    settings = Settings(
        schwab_client_id="configured-client",
        schwab_client_secret="configured-value",
        schwab_token_path=Path("missing-token.json"),
    )

    assert client.token_manager.status().configured is True
