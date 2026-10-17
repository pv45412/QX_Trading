import sys

with open('src/qx/pipeline/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.playbooks.engine import PlaybookResult", "")
content = content.replace("playbooks: Optional[PlaybookResult] = None", "playbooks: Any = None")

with open('src/qx/pipeline/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("models.py playbooks fixed.")
