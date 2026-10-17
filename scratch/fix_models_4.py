import sys

with open('src/qx/pipeline/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.direction.direction_engine import DirectionalContext", "from qx.direction.direction_engine import DirectionEngineResult")
content = content.replace("direction: Optional[DirectionalContext] = None", "direction: Optional[DirectionEngineResult] = None")

with open('src/qx/pipeline/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("models.py direction result fixed.")
