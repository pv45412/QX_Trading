"""Find the search PROVIDER SELECTION mechanism and what can be selected."""
import re

PATH = r"C:\Users\preet\.dsh\profiles\desktop\node_modules\dsh-github-copilot\lib\search-routing-CV2hs8as.js"
text = open(PATH, encoding="utf-8", errors="ignore").read()
print(f"file: {len(text):,} chars\n")

print("=" * 90)
print("A. Provider ids referenced for selection")
print("=" * 90)
ids = sorted(set(re.findall(r'"(github-copilot[a-z\-]*|[a-z0-9\-]*deepseek[a-z0-9\-]*|[a-z0-9\-]*exa[a-z0-9\-]*|[a-z0-9\-]*perplexity[a-z0-9\-]*)"', text)))
for i in ids:
    print(f"  {i}")

print()
print("=" * 90)
print("B. currentSearchSelection — how is a provider chosen?")
print("=" * 90)
for match in list(re.finditer(r"function currentSearchSelection|currentSearchSelection\s*=|const currentSearchSelection", text))[:2]:
    start = max(0, match.start() - 100)
    snippet = re.sub(r"\s+", " ", text[start:match.end() + 900])
    print(f"\n  ...{snippet}...")

print()
print("=" * 90)
print("C. isCopilotSearchSelection — what counts as a copilot selection?")
print("=" * 90)
for match in list(re.finditer(r"function isCopilotSearchSelection", text))[:1]:
    snippet = re.sub(r"\s+", " ", text[match.start():match.end() + 500])
    print(f"\n  ...{snippet}...")

print()
print("=" * 90)
print("D. Settings keys that carry the selection")
print("=" * 90)
keys = sorted(set(re.findall(r'"(searchProvider|search[A-Za-z]*|webSearch[A-Za-z]*)"', text)))
for k in keys[:15]:
    print(f"  {k}")

print()
print("=" * 90)
print("E. Any mention of how the user selects, or a UI label")
print("=" * 90)
for needle in ("preview", "select", "Select", "configured web provider"):
    for match in list(re.finditer(re.escape(needle), text))[:2]:
        start = max(0, match.start() - 140)
        snippet = re.sub(r"\s+", " ", text[start:match.end() + 160])
        print(f"\n  [{needle}] ...{snippet}...")
