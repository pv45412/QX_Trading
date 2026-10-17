import sys

with open('src/qx/pipeline/orchestrator.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("if not ctx.bars:", "if ctx.bars is None or len(ctx.bars) == 0:")
content = content.replace("current_bar = ctx.bars[-1]", "current_bar = ctx.bars.iloc[-1]")

with open('src/qx/pipeline/orchestrator.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("orchestrator.py fixed.")
