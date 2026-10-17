from pathlib import Path
from urllib.parse import urlparse


DEFAULT_SCHWAB_TOKEN_PATH = Path("data/secrets/schwab_token.json")


DEFAULT_SCHWAB_ENV_VALUES: dict[str, str] = {
    "SCANNER_ENV": "local",
    "SCANNER_LOG_LEVEL": "INFO",
    "SCANNER_INPUT_DIR": "data/raw",
    "SCANNER_OUTPUT_DIR": "data/processed",
    "SCANNER_DATA_PROVIDER": "schwab",
    "SCANNER_DATABASE_URL": "sqlite:///data/qx.db",
    "SCANNER_CACHE_DIR": "data/cache",
    "SCANNER_DEFAULT_UNIVERSE": "sp500",
    "SCANNER_SCAN_TIME": "16:30",
    "QX_SCHWAB_REDIRECT_URI": "https://127.0.0.1",
    "QX_SCHWAB_TOKEN_PATH": str(DEFAULT_SCHWAB_TOKEN_PATH).replace("\\", "/"),
    "SCANNER_SCHWAB_AUTH_BASE_URL": "https://api.schwabapi.com/v1/oauth",
    "SCANNER_SCHWAB_API_BASE_URL": "https://api.schwabapi.com",
}


ENV_KEY_ORDER = [
    "SCANNER_ENV",
    "SCANNER_LOG_LEVEL",
    "SCANNER_INPUT_DIR",
    "SCANNER_OUTPUT_DIR",
    "SCANNER_DATA_PROVIDER",
    "SCANNER_DATABASE_URL",
    "SCANNER_CACHE_DIR",
    "SCANNER_DEFAULT_UNIVERSE",
    "SCANNER_SCAN_TIME",
    "QX_SCHWAB_CLIENT_ID",
    "QX_SCHWAB_CLIENT_SECRET",
    "QX_SCHWAB_REDIRECT_URI",
    "QX_SCHWAB_TOKEN_PATH",
    "SCANNER_SCHWAB_AUTH_BASE_URL",
    "SCANNER_SCHWAB_API_BASE_URL",
]


def save_schwab_env(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str = "https://127.0.0.1",
    env_path: Path = Path(".env"),
) -> None:
    _validate_env_value(client_id, "client ID")
    _validate_env_value(client_secret, "client secret")
    _validate_env_value(redirect_uri, "redirect URI")
    resolved_client_id = client_id.strip()
    resolved_client_secret = client_secret.strip()
    if not resolved_client_id:
        raise ValueError("Schwab client ID is required.")
    if not resolved_client_secret:
        raise ValueError("Schwab client secret is required.")
    resolved_redirect_uri = redirect_uri.strip() or "https://127.0.0.1"
    _validate_redirect_uri(resolved_redirect_uri)

    values = _read_env(env_path)
    for key in list(values):
        if key.startswith("SCANNER_SCHWAB_"):
            values.pop(key)
    for key, value in DEFAULT_SCHWAB_ENV_VALUES.items():
        values.setdefault(key, value)
    values["QX_SCHWAB_CLIENT_ID"] = resolved_client_id
    values["QX_SCHWAB_CLIENT_SECRET"] = resolved_client_secret
    values["QX_SCHWAB_REDIRECT_URI"] = resolved_redirect_uri
    values["QX_SCHWAB_TOKEN_PATH"] = str(DEFAULT_SCHWAB_TOKEN_PATH).replace("\\", "/")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    ordered_keys = [key for key in ENV_KEY_ORDER if key in values]
    ordered_keys.extend(key for key in values if key not in ordered_keys)
    env_path.write_text(
        "\n".join(f"{key}={values[key]}" for key in ordered_keys) + "\n",
        encoding="utf-8",
    )


def clear_schwab_env(env_path: Path = Path(".env")) -> None:
    values = _read_env(env_path)
    for key in list(values):
        if key.startswith(("QX_SCHWAB_", "SCANNER_SCHWAB_")):
            values.pop(key)
    if not values:
        env_path.unlink(missing_ok=True)
        return
    ordered_keys = [key for key in ENV_KEY_ORDER if key in values]
    ordered_keys.extend(key for key in values if key not in ordered_keys)
    env_path.write_text(
        "\n".join(f"{key}={values[key]}" for key in ordered_keys) + "\n",
        encoding="utf-8",
    )


def _read_env(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _validate_redirect_uri(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Redirect URI must be an HTTPS loopback address for local development.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Redirect URI contains unsupported components.")


def _validate_env_value(value: str, field_name: str) -> None:
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise ValueError(f"Schwab {field_name} contains unsupported characters.")
