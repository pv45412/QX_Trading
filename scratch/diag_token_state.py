"""Why does status() report refresh_token_valid=True while the grant is dead?"""
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

import qx.brokers.schwab.auth as auth  # noqa: E402
from qx.config.settings import get_settings  # noqa: E402

print("auth module file :", auth.__file__)
print("_PROVIDER_REJECTIONS id:", id(auth._PROVIDER_REJECTIONS))
print("registry at import      :", auth._PROVIDER_REJECTIONS)
print("confirmed at import     :", auth._PROVIDER_CONFIRMED)
print()

settings = get_settings()
print("token_path              :", settings.schwab_token_path)
print("_rejection_key(settings):", repr(auth._rejection_key(settings)))
print()

manager = auth.SchwabTokenManager(settings)
st = manager.status()
print("--- status() BEFORE any probe ---")
for f in ("configured", "has_token", "access_token_valid", "refresh_token_valid",
          "restart_required", "refresh_expiry_known", "refresh_token_state",
          "provider_verified", "provider_error"):
    print(f"  {f:24}: {getattr(st, f)!r}")
print()

# Now force the same failure the health probe hits.
print("--- forcing a refresh attempt ---")
try:
    manager.get_access_token()
except Exception as exc:  # noqa: BLE001
    print("  raised:", type(exc).__name__, str(exc)[:120])
print("  registry now          :", auth._PROVIDER_REJECTIONS)
print("  _provider_rejection() :", repr(auth._provider_rejection(settings)))
print()

st2 = manager.status()
print("--- status() AFTER the failure ---")
for f in ("refresh_token_valid", "restart_required", "refresh_token_state",
          "provider_verified", "provider_error"):
    print(f"  {f:24}: {getattr(st2, f)!r}")
print()

# Fresh manager, as the settings page would build.
st3 = auth.SchwabTokenManager(settings).status()
print("--- status() from a FRESH manager (what the page builds) ---")
for f in ("refresh_token_valid", "restart_required", "refresh_token_state",
          "provider_verified", "provider_error"):
    print(f"  {f:24}: {getattr(st3, f)!r}")
print()

# What the settings service actually forwards to the browser.
from qx.app import settings_service  # noqa: E402

live = settings_service.status()
print("--- settings_service.status() token block ---")
for k, v in live["token"].items():
    print(f"  {k:24}: {v!r}")
print("  health.ok             :", live["health"]["ok"])
