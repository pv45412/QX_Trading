import sys

with open('src/qx/pipeline/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace("from qx.regime.market_regime import MarketRegimeContext", "from qx.regime.market_regime import MarketRegimeModel")
content = content.replace("market_regime: Optional[MarketRegimeContext] = None", "market_regime: Optional[MarketRegimeModel] = None")

with open('src/qx/pipeline/models.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("models.py fixed again again.")
