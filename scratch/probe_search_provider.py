"""Extract the search-provider wiring from the DSH asar to explain the failure."""
import re

ASAR = r"C:\Users\preet\AppData\Local\Programs\DeepSeek Harness\resources\app.asar"

with open(ASAR, "rb") as handle:
    text = handle.read().decode("utf-8", errors="ignore")

print(f"asar scanned: {len(text):,} chars\n")

print("=" * 88)
print("A. What search providers exist, and what do they need?")
print("=" * 88)
for needle in ("deepseek-official", "brave", "perplexity"):
    positions = [m.start() for m in re.finditer(re.escape(needle), text)]
    print(f"\n  '{needle}' appears {len(positions)} times")

# Find the provider registry: look for a list of provider ids.
for pattern in (r'searchProviders?\s*[:=]\s*\[[^\]]{0,400}\]',
                r'providers?\s*[:=]\s*\[[^\]]{0,300}\]',
                r'"deepseek-official"'):
    for match in list(re.finditer(pattern, text))[:3]:
        snippet = match.group(0).replace("\n", " ")[:320]
        print(f"\n  pattern {pattern!r}:")
        print(f"     {snippet}")

print()
print("=" * 88)
print("B. What triggers 'WEB_PROVIDER_ERROR'?")
print("=" * 88)
for match in list(re.finditer(r"WEB_PROVIDER_ERROR", text))[:6]:
    start = max(0, match.start() - 260)
    snippet = text[start:match.end() + 120].replace("\n", " ")
    print(f"\n  ...{snippet}...")

print()
print("=" * 88)
print("C. Is there a search API endpoint / key name expected?")
print("=" * 88)
for pattern in (r'[A-Z_]*SEARCH[A-Z_]*API_KEY', r'BRAVE[A-Z_]*KEY', r'PERPLEXITY[A-Z_]*KEY',
                r'[A-Z_]*WEB_SEARCH[A-Z_]*'):
    found = sorted(set(re.findall(pattern, text)))
    if found:
        print(f"  {pattern:<32} {found[:6]}")

print()
print("=" * 88)
print("D. Where does 'no matching primary provider' come from? (not in the asar)")
print("=" * 88)
print("  It is absent from app.asar, so it is produced by a PLUGIN or by the")
print("  search tool's own fallback layer rather than the bundled app.")
print("  Check the profile's installed plugins for a search provider entry.")
