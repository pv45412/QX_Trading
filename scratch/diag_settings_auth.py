"""Ground truth: is the Schwab refresh token actually rejected?"""
import json
import os
import sys

os.chdir(r"C:\Project\2026")
sys.path.insert(0, r"C:\Project\2026\src")

from qx.config.settings import get_settings  # noqa: E402
from qx.brokers.schwab.auth import SchwabTokenManager  # noqa: E402

s = get_settings()
print("token path :", s.schwab_token_path)
print("exists     :", s.schwab_token_path.exists())

store = SchwabTokenManager(s).store
tok = store.load()
print()
print("--- what the manager reports (the settings page source) ---")
print("  needs_refresh        :", tok.needs_refresh)
print("  refresh_expired      :", tok.refresh_expired)
print("  refresh_expiry_known :", tok.refresh_expiry_known)
print("  access_expires_at    :", tok.access_token_expires_at)
print("  refresh_expires_at   :", tok.refresh_token_expires_at)
print("  scope                :", tok.scope)
print()
st = SchwabTokenManager(s).status()
print("--- manager.status() ---")
print("  refresh_token_valid  :", st.refresh_token_valid)
print("  access_token_valid   :", st.access_token_valid)
print("  restart_required     :", st.restart_required)
print("  refresh_token_state  :", st.refresh_token_state)
print("  refresh_expiry_known :", st.refresh_expiry_known)
print("  provider_error       :", st.provider_error)
print("  message              :", st.message)

print()
print("--- raw refresh grant against Schwab (ground truth) ---")
import requests  # noqa: E402

payload = {
    "grant_type": "refresh_token",
    "refresh_token": tok.refresh_token,
    "client_id": s.schwab_client_id,
    "client_secret": s.schwab_client_secret,
}
try:
    r = requests.post(
        f"{s.schwab_api_base_url}/v1/oauth/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    print("  HTTP", r.status_code)
    body = r.text
    if len(body) > 400:
        body = body[:400] + "..."
    print("  body:", body)
except Exception as exc:
    print("  EXC:", type(exc).__name__, exc)
