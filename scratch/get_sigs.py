import ast
import os

paths = [
    'src/qx/structure/smc_suite.py',
    'src/qx/regime/market_regime.py',
    'src/qx/direction/direction_engine.py',
    'src/qx/playbooks/engine.py',
    'src/qx/triggers/engine.py',
    'src/qx/tradeability/engine.py',
    'src/qx/options_expression/engine.py',
    'src/qx/portfolio/portfolio_risk_engine.py'
]

for p in paths:
    if not os.path.exists(p):
        print(f"NOT FOUND: {p}")
        continue
    code = open(p, encoding='utf-8').read()
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and ('eval' in node.name or 'analyze' in node.name or 'process' in node.name):
            args = [a.arg for a in node.args.args]
            print(f"{p}: {node.name}({', '.join(args)})")
        elif isinstance(node, ast.ClassDef):
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and ('eval' in m.name or 'analyze' in m.name):
                    args = [a.arg for a in m.args.args]
                    print(f"{p}: {node.name}.{m.name}({', '.join(args)})")
