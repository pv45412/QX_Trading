import sys

with open('src/qx/interfaces/web.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("load_rules_config(\"research_v1\")", "load_rules_config()")

with open('src/qx/interfaces/web.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("web.py config fixed")
