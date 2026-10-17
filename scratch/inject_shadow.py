import sys

with open('src/qx/interfaces/web.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "def ai_review(symbol: str, body: AIReviewRequest, request: Request) -> dict[str, Any]:" in line:
        lines.insert(i+1, "    try: run_pipeline_shadow(symbol)\n    except Exception: pass\n")
        break

with open('src/qx/interfaces/web.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
