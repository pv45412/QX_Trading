"""Extract the web-search settings schema so the UI fields are known exactly."""
import re

ASAR = r"C:\Users\preet\AppData\Local\Programs\DeepSeek Harness\resources\app.asar"
with open(ASAR, "rb") as handle:
    text = handle.read().decode("utf-8", errors="ignore")

print("=" * 88)
print("A. The web-search settings card — labels and fields")
print("=" * 88)
for match in list(re.finditer(r"web-search-card-controller", text))[:2]:
    start = max(0, match.start() - 200)
    snippet = re.sub(r"\s+", " ", text[start:match.end() + 1500])
    print(f"\n  ...{snippet}...")

print()
print("=" * 88)
print("B. Provider ids the settings expose")
print("=" * 88)
for match in list(re.finditer(r"WEB_SEARCH_NS", text))[:4]:
    start = max(0, match.start() - 600)
    snippet = re.sub(r"\s+", " ", text[start:match.end() + 900])
    print(f"\n  ...{snippet}...")

print()
print("=" * 88)
print("C. Guidance strings shown to the user")
print("=" * 88)
for key in ("web-search-only-guidance", "web-search-guidance-with-fetch-enabled"):
    for match in list(re.finditer(re.escape(key), text))[:1]:
        start = max(0, match.start() - 100)
        snippet = re.sub(r"\s+", " ", text[start:match.end() + 500])
        print(f"\n  [{key}]\n     ...{snippet}...")
