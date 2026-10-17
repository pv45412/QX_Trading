import sys

with open('tests/unit/test_pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.models.market import BarData\n", "import pandas as pd\n")
mock_bars_replacement = '''
@pytest.fixture
def mock_bars():
    df = pd.DataFrame({
        'timestamp': [datetime.now(timezone.utc)] * 50,
        'open': [100.0] * 50,
        'high': [101.0] * 50,
        'low': [99.0] * 50,
        'close': [100.5] * 50,
        'volume': [1000] * 50
    })
    return df
'''
import re
content = re.sub(r'@pytest\.fixture\s+def mock_bars\(\):.*?return \[\n.*?\]', mock_bars_replacement, content, flags=re.DOTALL)

with open('tests/unit/test_pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("test_pipeline.py fixed.")
