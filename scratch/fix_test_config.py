import sys

with open('tests/unit/test_pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("load_rules_config(\"research_v1\")", "load_rules_config()")

with open('tests/unit/test_pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("test_pipeline.py config fixed")
