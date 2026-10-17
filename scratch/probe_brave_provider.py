"""Is a Brave SEARCH provider actually available, and is there a key for it?

Setting DSH_WEB_SEARCH_PROVIDER=brave only helps if:
  1. a Brave search provider package is installed/installable, AND
  2. a Brave API key exists in credentials.
Otherwise the error just changes from WEB_PROVIDER_ERROR to WEB_PROVIDER_UNAVAILABLE.
"""
import re

ASAR = r"C:\Users\preet\AppData\Local\Programs\DeepSeek Harness\resources\app.asar"
with open(ASAR, "rb") as handle:
    text = handle.read().decode("utf-8", errors="ignore")

print("=" * 88)
print("A. Every 'brave' reference in the bundle — provider, or something else?")
print("=" * 88)
for i, match in enumerate(re.finditer(r"[Bb]rave", text)):
    start = max(0, match.start() - 110)
    snippet = re.sub(r"\s+", " ", text[start:match.end() + 110])
    print(f"  [{i+1}] ...{snippet}...")
    if i >= 11:
        print("  ... (truncated)")
        break

print()
print("=" * 88)
print("B. Search-provider package names referenced in the bundle")
print("=" * 88)
names = sorted(set(re.findall(r"@deepseek-ai/dsh-web-[a-z0-9\-]+", text)))
for name in names:
    print(f"  {name}")

print()
print("=" * 88)
print("C. Env vars the search layer reads")
print("=" * 88)
for pattern in (r"DSH_WEB_[A-Z_]+", r"[A-Z_]*BRAVE[A-Z_]*", r"[A-Z_]*EXA[A-Z_]*",
                r"[A-Z_]*PERPLEXITY[A-Z_]*"):
    found = sorted(set(re.findall(pattern, text)))
    if found:
        print(f"  {pattern:<28} {found[:8]}")
