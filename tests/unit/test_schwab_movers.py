import pytest
from qx.brokers.schwab.movers import normalize_screeners, fetch_top_movers


def row(**updates):
    return {"symbol": "TEST", "lastPrice": 99., "netChange": -1., **updates}


@pytest.mark.parametrize("updates", [{"lastPrice": float("nan")}, {"netChange": True}, {"lastPrice": 0}, {"netChange": 100}, {"symbol": ""}])
def test_invalid_prices_fail_closed(updates):
    with pytest.raises(ValueError):
        normalize_screeners({"screeners": [row(**updates)]})


def test_negative_highest_mover_is_not_relabelled_as_gainer():
    class Client:
        def get(self, path, params):
            assert path == "/marketdata/v1/movers/$SPX"
            return {"screeners": [row()]}
    result = fetch_top_movers(Client())
    assert result["groups"]["highest"][0]["return"] == pytest.approx(-.01)
    assert result["market_as_of"] is None


def test_duplicates_and_missing_list_rejected():
    for payload in ({}, {"screeners": [row(), row()]}):
        with pytest.raises(ValueError):
            normalize_screeners(payload)


def test_request_guard_and_sanitized_failure(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request
    from qx.interfaces import web
    endpoint = next(r.endpoint for r in web.create_app().routes if r.path == "/api/schwab/movers")
    with pytest.raises(HTTPException) as error:
        endpoint(Request({"type": "http", "headers": []}))
    assert error.value.status_code == 403
    def fail(*args):
        raise RuntimeError("private broker error")
    monkeypatch.setattr(web, "_schwab_client", fail)
    with pytest.raises(HTTPException) as error:
        endpoint(Request({"type": "http", "headers": [(b"x-qx-refresh", b"1")]}))
    assert error.value.status_code == 503
    assert "private" not in error.value.detail
