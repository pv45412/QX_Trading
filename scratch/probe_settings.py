"""Probe the real settings payload and the live token state."""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.app import settings_service  # noqa: E402

payload = settings_service.status()
print("=== settings_service.status() ===")
print(json.dumps(payload, indent=2, default=str)[:2600])

print()
print("=== raw token file ===")
from qx.config.settings import get_settings  # noqa: E402
from qx.brokers.schwab.auth import SchwabTokenStore  # noqa: E402

settings = get_settings()
store = SchwabTokenStore(settings.schwab_token_path)
token = store.load()
if token is None:
    print("  no token")
else:
    print(f"  access expires  : {token.access_token_expires_at}")
    print(f"  refresh expires : {token.refresh_token_expires_at}")
    print(f"  needs_refresh   : {token.needs_refresh}")
    print(f"  refresh_expired : {token.refresh_expired}")
    print(f"  scope           : {token.scope}")

print()
print("=== live refresh attempt (reveals the true server-side state) ===")
from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402

manager = SchwabTokenManager(settings)
try:
    fresh = manager.refresh_access_token(token.refresh_token)
    print(f"  REFRESH OK — new access token expires {fresh.access_token_expires_at}")
except Exception as exc:  # noqa: BLE001
    print(f"  REFRESH FAILED — {type(exc).__name__}: {exc}")
