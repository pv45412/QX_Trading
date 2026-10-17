"""Confirm EXA_API_KEY is settable via the .env layer (no bootstrap-only restriction)."""
import re

ASAR = r"C:\Users\preet\AppData\Local\Programs\DeepSeek Harness\resources\app.asar"
with open(ASAR, "rb") as handle:
    text = handle.read().decode("utf-8", errors="ignore")

print("=" * 88)
print("A. isBootstrapOnly — which names are rejected in a layer?")
print("=" * 88)
for match in list(re.finditer(r"function isBootstrapOnly", text))[:1]:
    snippet = re.sub(r"\s+", " ", text[match.start():match.end() + 700])
    print(f"\n  ...{snippet}...")

print()
print("=" * 88)
print("B. HOME_LAYER_PROXY_NAMES — allowed in the home layer")
print("=" * 88)
for match in list(re.finditer(r"HOME_LAYER_PROXY_NAMES\s*=", text))[:1]:
    snippet = re.sub(r"\s+", " ", text[match.start():match.end() + 400])
    print(f"\n  ...{snippet}...")

print()
print("=" * 88)
print("C. Is EXA_API_KEY mentioned as bootstrap-only anywhere?")
print("=" * 88)
hits = [m.start() for m in re.finditer(r"EXA_API_KEY", text)]
print(f"  'EXA_API_KEY' appears {len(hits)} times")
for start in hits[:4]:
    snippet = re.sub(r"\s+", " ", text[max(0, start - 200):start + 200])
    print(f"     ...{snippet}...")

print()
print("=" * 88)
print("D. The credential layering order (which layer wins)")
print("=" * 88)
for match in list(re.finditer(r"layered\s+against the environment by how much", text))[:1]:
    snippet = re.sub(r"\s+", " ", text[max(0, match.start() - 100):match.end() + 900])
    print(f"\n  ...{snippet}...")
