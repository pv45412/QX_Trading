import sys

with open('src/qx/pipeline/orchestrator.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("structure_state=struct_ctx.current_state.value if struct_ctx else \"UNKNOWN\",", "structure_state=struct_ctx.regime if struct_ctx else \"UNKNOWN\",")

with open('src/qx/pipeline/orchestrator.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("orchestrator SMC regime fixed")
