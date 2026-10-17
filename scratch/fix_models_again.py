import sys

with open('src/qx/pipeline/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.structure.smc_suite import MarketStructureContext", "from qx.structure.smc_suite import SMCAnalysisResult")
content = content.replace("structure: Optional[MarketStructureContext] = None", "structure: Optional[SMCAnalysisResult] = None")

with open('src/qx/pipeline/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("models.py fixed again.")
