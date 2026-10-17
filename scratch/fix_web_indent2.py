import sys

with open('src/qx/interfaces/web.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip().startswith("try: run_pipeline_shadow(symbol)"):
        new_lines.append("        try: run_pipeline_shadow(symbol)\n")
    elif line.strip().startswith("except Exception: pass"):
        new_lines.append("        except Exception: pass\n")
    else:
        new_lines.append(line)

with open('src/qx/interfaces/web.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
