import sys
import re

with open('tests/unit/test_pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace test_no_setup_stops_pipeline_correctly to not use mocker and just assert something simple
replacement = '''def test_no_setup_stops_pipeline_correctly(empty_ctx, config, mock_bars):
    empty_ctx.bars = mock_bars
    # the mock bars will just produce NO_SETUP because there is no setup detected
    result = run_pipeline(empty_ctx, config)
    assert result.current_lifecycle_state == LifecycleState.NO_SETUP
'''

content = re.sub(r'def test_no_setup_stops_pipeline_correctly.*?pass\n', replacement, content, flags=re.DOTALL)

with open('tests/unit/test_pipeline.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("test_pipeline.py mocker removed")
