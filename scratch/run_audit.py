import os
import ast
import time
import json
import re
from pathlib import Path

def find_fastapi_routes(root_path):
    routes = []
    for root, dirs, files in os.walk(root_path):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                content = open(path, encoding='utf-8').read()
                if '@app.' in content or '@router.' in content:
                    routes.append(path)
    return routes

def find_react_fetches(root_path):
    fetches = []
    if not os.path.exists(root_path): return fetches
    for root, dirs, files in os.walk(root_path):
        for f in files:
            if f.endswith(('.js', '.jsx', '.ts', '.tsx')):
                path = os.path.join(root, f)
                try:
                    content = open(path, encoding='utf-8').read()
                    if 'fetch(' in content or 'axios' in content:
                        fetches.append(path)
                except Exception:
                    pass
    return fetches

def check_computations(root_path):
    # Search for SMC structure, Order Blocks, regime, Direction Score, etc.
    computations = {}
    for root, dirs, files in os.walk(root_path):
        for f in files:
            if f.endswith('.py'):
                path = os.path.join(root, f)
                try:
                    content = open(path, encoding='utf-8').read()
                    if 'MarketRegimeEngine' in content:
                        computations.setdefault('Regime', []).append(path)
                    if 'DirectionEngine' in content:
                        computations.setdefault('Direction', []).append(path)
                    if 'OrderBlock' in content:
                        computations.setdefault('OrderBlocks', []).append(path)
                    if 'StructureEngine' in content:
                        computations.setdefault('Structure', []).append(path)
                except Exception:
                    pass
    return computations

out = {
    'routes': find_fastapi_routes('src/qx'),
    'react_fetches': find_react_fetches('web/src'),
    'computations': check_computations('src/qx')
}

with open('scratch/audit_results.json', 'w') as f:
    json.dump(out, f, indent=2)
