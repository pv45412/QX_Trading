"""
Unit tests for QX Data Ingestion & Warmup Automation Engine.
"""

from qx.automation.data_ingestion import QXDataIngestionPipeline


def test_data_ingestion_quotes_sync():
    pipeline = QXDataIngestionPipeline(symbols=["XLK", "SPY"])
    quotes = pipeline.sync_market_quotes()
    assert "XLK" in quotes
    assert quotes["XLK"]["status"] == "SYNCED"
    assert "SPY" in quotes


def test_data_ingestion_futures_sync():
    pipeline = QXDataIngestionPipeline()
    futures = pipeline.sync_futures_context()
    assert "ES" in futures
    assert futures["ES"]["status"] == "SYNCED"
    assert "NQ" in futures


def test_data_ingestion_full_pipeline_run():
    pipeline = QXDataIngestionPipeline(symbols=["XLK", "XLC"])
    result = pipeline.run_pipeline()
    assert result["status"] == "COMPLETED"
    assert result["quotes_synced"] == 2
    assert result["futures_synced"] == 2
    assert "completed_at" in result
