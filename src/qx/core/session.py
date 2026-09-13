from collections.abc import Iterable

from qx.core.engine import ScannerEngine
from qx.data.providers import MarketDataProvider
from qx.models.scan import RectangleScanParameters, ScanRunResult


class ScanSession:
    """Coordinates one stock scanner run from request to result."""

    def __init__(
        self,
        provider: MarketDataProvider,
        parameters: RectangleScanParameters | None = None,
    ) -> None:
        self.engine = ScannerEngine(provider=provider, parameters=parameters)

    def run(self, symbols: Iterable[str], period: str = "1y") -> ScanRunResult:
        return self.engine.scan_symbols(symbols, period=period)
