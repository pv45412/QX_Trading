import sys

with open('src/qx/pipeline/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.models.market import BarData\n", "")
content = content.replace("bars: List[BarData] = Field(default_factory=list)", "bars: Any = None")
content = content.replace("from pydantic import BaseModel, Field", "from pydantic import BaseModel, Field, ConfigDict")
content = content.replace("class QXEvaluationContext(BaseModel):", "class QXEvaluationContext(BaseModel):\n    model_config = ConfigDict(arbitrary_types_allowed=True)\n")

with open('src/qx/pipeline/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("models.py fixed.")
