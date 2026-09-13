from datetime import datetime, timezone

import pytest

from qx.brokers.schwab.quotes import _first_timestamp


@pytest.mark.parametrize("key", ["quoteTime", "tradeTime", "quoteTimeInLong", "tradeTimeInLong"])
def test_timestamp_fields_are_utc(key):
    value = 1788971468394
    assert _first_timestamp({key: value}) == datetime.fromtimestamp(value / 1000, timezone.utc)


@pytest.mark.parametrize("value", [None, 0, -1, float("nan"), float("inf"), 1e100])
def test_invalid_timestamp_is_unknown(value):
    assert _first_timestamp({"quoteTime": value}) is None
