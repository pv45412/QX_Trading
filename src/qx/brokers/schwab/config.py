from pathlib import Path


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
    "SCANNER_SCHWAB_REDIRECT_URI": "https://127.0.0.1",
    "SCANNER_SCHWAB_TOKEN_PATH": "data/secrets/schwab_token.json",
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
    "SCANNER_SCHWAB_CLIENT_ID",
    "SCANNER_SCHWAB_CLIENT_SECRET",
    "SCANNER_SCHWAB_REDIRECT_URI",
    "SCANNER_SCHWAB_TOKEN_PATH",
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
    if not client_id.strip():
        raise ValueError("Schwab client ID is required.")
    if not client_secret.strip():
        raise ValueError("Schwab client secret is required.")

    values = _read_env(env_path)
    for key, value in DEFAULT_SCHWAB_ENV_VALUES.items():
        values.setdefault(key, value)
    values["SCANNER_SCHWAB_CLIENT_ID"] = client_id.strip()
    values["SCANNER_SCHWAB_CLIENT_SECRET"] = client_secret.strip()
    values["SCANNER_SCHWAB_REDIRECT_URI"] = redirect_uri.strip() or "https://127.0.0.1"
    values["SCANNER_SCHWAB_TOKEN_PATH"] = "data/secrets/schwab_token.json"

    env_path.write_text(
        "\n".join(f"{key}={values[key]}" for key in ENV_KEY_ORDER if key in values) + "\n",
        encoding="utf-8",
    )
    Path("data/secrets").mkdir(parents=True, exist_ok=True)


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
