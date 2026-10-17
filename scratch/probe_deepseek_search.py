"""What does the deepseek-official search provider call, and why would it fail?"""
import re

ASAR = r"C:\Users\preet\AppData\Local\Programs\DeepSeek Harness\resources\app.asar"
with open(ASAR, "rb") as handle:
    text = handle.read().decode("utf-8", errors="ignore")

print("=" * 88)
print("A. Provider selection env var and its default")
print("=" * 88)
for match in list(re.finditer(r"DSH_WEB_SEARCH_PROVIDER", text))[:6]:
    start = max(0, match.start() - 300)
    snippet = text[start:match.end() + 300].replace("\n", " ")
    snippet = re.sub(r"\s+", " ", snippet)
    print(f"\n  ...{snippet}...")

print()
print("=" * 88)
print("B. The DeepSeek search provider definition")
print("=" * 88)
for match in list(re.finditer(r"WEB_SEARCH_DEEPSEEK_SETTINGS_NAMESPACE", text))[:3]:
    start = max(0, match.start() - 500)
    snippet = text[start:match.end() + 700].replace("\n", " ")
    snippet = re.sub(r"\s+", " ", snippet)
    print(f"\n  ...{snippet}...")

print()
print("=" * 88)
print("C. Any search endpoint URL in the bundle")
print("=" * 88)
urls = set()
for pattern in (r'https?://[a-zA-Z0-9._\-/]*search[a-zA-Z0-9._\-/]*',
                r'https?://[a-zA-Z0-9._\-/]*deepseek[a-zA-Z0-9._\-/]*'):
    for found in re.findall(pattern, text):
        if len(found) < 120:
            urls.add(found)
for url in sorted(urls)[:20]:
    print(f"  {url}")

print()
print("=" * 88)
print("D. Provider ids the search tool accepts")
print("=" * 88)
for match in list(re.finditer(r'"(deepseek-official|brave|perplexity)"', text))[:8]:
    start = max(0, match.start() - 200)
    snippet = text[start:match.end() + 200].replace("\n", " ")
    snippet = re.sub(r"\s+", " ", snippet)
    print(f"\n  ...{snippet}...")
