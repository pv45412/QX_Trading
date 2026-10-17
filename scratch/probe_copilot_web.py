"""What does the DSH web-search settings page configure, and what is the copilot web override?"""
import re

ASAR = r"C:\Users\preet\AppData\Local\Programs\DeepSeek Harness\resources\app.asar"
with open(ASAR, "rb") as handle:
    text = handle.read().decode("utf-8", errors="ignore")

print("=" * 88)
print("A. github-copilot routed web — what does it register as a search provider?")
print("=" * 88)
for needle in ("github-copilot-routed-web", "github-copilot-web-delegate"):
    for match in list(re.finditer(re.escape(needle), text))[:3]:
        start = max(0, match.start() - 200)
        snippet = re.sub(r"\s+", " ", text[start:match.end() + 400])
        print(f"\n  [{needle}]\n     ...{snippet}...")

print()
print("=" * 88)
print("B. The web-search settings namespace / schema")
print("=" * 88)
for pattern in (r"web-search[a-z\-]*", r"WEB_SEARCH_NS", r"searchProvider"):
    found = sorted(set(re.findall(pattern, text)))
    print(f"  {pattern:<24} {found[:10]}")

print()
print("=" * 88)
print("C. Any message the UI shows when search is unavailable")
print("=" * 88)
for needle in ("no matching primary provider", "WEB_PROVIDER_UNAVAILABLE",
               "Sign in to GitHub", "copilot", "GitHub Copilot"):
    count = len(re.findall(re.escape(needle), text))
    if count:
        print(f"  {needle!r} appears {count} times")

print()
print("=" * 88)
print("D. Does the copilot plugin declare search providers?")
print("=" * 88)
for match in list(re.finditer(r"registerSearchProvider", text))[:6]:
    start = max(0, match.start() - 300)
    snippet = re.sub(r"\s+", " ", text[start:match.end() + 200])
    print(f"\n  ...{snippet}...")
