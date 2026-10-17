import sys

with open('src/qx/interfaces/web.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.startswith("@app.post(\"/api/ai/review/{symbol}\")"):
        new_lines.append("    " + line)
    else:
        new_lines.append(line)

with open('src/qx/interfaces/web.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

