import sys

with open('src/qx/pipeline/adapters.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.models.market import BarData\n", "")
content = content.replace("historical_bars: List[BarData]", "historical_bars: List[Dict[str, Any]]")

with open('src/qx/pipeline/adapters.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("adapters.py fixed")
