import sys

with open('src/qx/pipeline/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.triggers.models import TriggerResult", "from qx.triggers.models import TriggeredSetupResult")
content = content.replace("trigger: Optional[TriggerResult] = None", "trigger: Optional[TriggeredSetupResult] = None")

with open('src/qx/pipeline/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("models.py trigger fixed.")
