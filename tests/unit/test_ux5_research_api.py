from fastapi.testclient import TestClient

from qx.interfaces.web import create_app


def test_market_snapshot_does_not_fabricate_uncached_research_data(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    client = TestClient(create_app(database=tmp_path / "qx.db", cache_dir=cache_dir))

    payload = client.get("/api/market/NOTCACHED/snapshot").json()

    assert payload["status"] == "UNAVAILABLE"
    assert payload["source_class"] == "UNAVAILABLE"
    assert payload["last_price"] is None
    assert payload["structure"] is None
    assert payload["reason_code"] == "SOURCE_BARS_UNAVAILABLE"

