from qx.data.metadata import SymbolMetadataStore
from qx.models.scan import ScanCandidate


def displayed_candidate_metadata(
    candidates: list[ScanCandidate],
    *,
    max_symbols: int = 25,
    metadata_store: SymbolMetadataStore | None = None,
) -> tuple[SymbolMetadataStore, int]:
    metadata = metadata_store or SymbolMetadataStore()
    symbols = [candidate.symbol for candidate in candidates]
    enriched = metadata.enrich_yfinance(symbols, max_symbols=min(max_symbols, len(symbols)))
    return metadata, enriched
