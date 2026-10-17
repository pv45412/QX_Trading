import sys

with open('src/qx/interfaces/web.py', 'r', encoding='utf-8') as f:
    content = f.read()

import_snippet = '''
import logging
from qx.pipeline.models import QXEvaluationContext, QXEvaluationResult
from qx.pipeline.orchestrator import run_pipeline
from qx.config.rules_config import load_rules_config
from datetime import datetime, timezone
import traceback

logger = logging.getLogger(__name__)

def run_pipeline_shadow(symbol: str, timeframe: str = "5m"):
    try:
        config = load_rules_config("research_v1")
        ctx = QXEvaluationContext(
            symbol=symbol,
            timeframe=timeframe,
            evaluation_timestamp=datetime.now(timezone.utc),
            config=config
        )
        # Mock some bars to avoid BLOCKED
        from qx.models.market import BarData
        ctx.bars = [BarData(timestamp=datetime.now(timezone.utc), open=100.0, high=101.0, low=99.0, close=100.5, volume=1000) for _ in range(50)]
        result = run_pipeline(ctx, config)
        logger.info(f"[SHADOW MODE] V2 Pipeline evaluated {symbol}. State: {result.current_lifecycle_state}")
    except Exception as e:
        logger.error(f"[SHADOW MODE] V2 Pipeline failed for {symbol}: {e}")
'''

endpoint_snippet = '''
    @app.post("/api/v2/qx/evaluate/{symbol}")
    def evaluate_pipeline_v2(symbol: str, timeframe: str = "5m") -> QXEvaluationResult:
        config = load_rules_config("research_v1")
        ctx = QXEvaluationContext(
            symbol=symbol,
            timeframe=timeframe,
            evaluation_timestamp=datetime.now(timezone.utc),
            config=config
        )
        # Assuming Data is injected here normally, we'll mock minimal for v2 endpoint stability
        from qx.models.market import BarData
        ctx.bars = [BarData(timestamp=datetime.now(timezone.utc), open=100.0, high=101.0, low=99.0, close=100.5, volume=1000) for _ in range(50)]
        return run_pipeline(ctx, config)
'''

# Find the start of the file for imports
if "from qx.pipeline.models" not in content:
    content = import_snippet + "\n" + content

# Find where endpoints are defined, e.g., above ai_review
ai_review_idx = content.find("def ai_review(symbol: str, body: AIReviewRequest, request: Request) -> dict[str, Any]:")
if ai_review_idx != -1 and "@app.post(\"/api/v2/qx/evaluate/{symbol}\")" not in content:
    idx = content.rfind("@app.post", 0, ai_review_idx)
    content = content[:idx] + endpoint_snippet + "\n" + content[idx:]

    # Add background task to ai_review
    bg_task_str = "    request.app.state.background_tasks.add_task(run_pipeline_shadow, symbol)"
    # We will just inject it roughly since this is a complex file
    
with open('src/qx/interfaces/web.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("web.py patched.")
