import json
from unittest.mock import Mock

import pytest

from qx.data.membership import membership_symbols, save_membership, validate_membership_change
from qx.data.universe import UniverseLoader
from qx.data.stock_refresh import StockRefresh
from qx.market.stock_movers import stock_movers


@pytest.mark.parametrize("content", [b"symbol\n", b"name\nAAPL\n", b"symbol\nAAPL\nAAPL\n",
                                   b"symbol\nBRK.B\nBRK-B\n", b"symbol\nnot a ticker\n",
                                   b"symbol,symbol\nAAPL,MSFT\n",
                                   b"symbol,sector\nAAPL,Tech,EXTRA\n",
                                   b"symbol,sector\nAAPL\n",
                                   b"symbol,sector,sector\nAAPL,Tech,Other\n",
                                   b"symbol,\nAAPL,Tech\n",
                                   b'symbol,name\nAAPL,"unterminated\n'])
def test_malformed_membership_rejected(content):
    with pytest.raises(ValueError):
        membership_symbols(content)


def test_membership_keeps_valid_extra_columns_and_quoted_values():
    assert membership_symbols(b'\xef\xbb\xbfsymbol,name\r\nAAPL,"Apple, Inc."\r\nMSFT,Microsoft\r\n') == ["AAPL", "MSFT"]


@pytest.mark.parametrize("content", [b"symbol,name\nMSFT,Name,extra\n", b"symbol,name\nMSFT\n"])
def test_malformed_save_preserves_all_membership_artifacts(tmp_path, content):
    path = tmp_path / "symbols.csv"
    save_membership(path, b"symbol\nAAPL\n", "fixture")
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError):
        save_membership(path, content, "fixture")
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('content', [b'symbol,sector\nAAPL,Tech,EXTRA\n',
                                   b'symbol,sector\nAAPL\n',
                                   b'symbol,sector,sector\nAAPL,Tech,Other\n'])
def test_malformed_membership_never_starts_provider_or_replaces_publication(tmp_path, content):
    provider = Mock()
    refresh = StockRefresh(tmp_path / 'bars', provider, 'sp100')
    refresh.root.mkdir(parents=True)
    old = refresh.root / ('a' * 32)
    old.mkdir()
    pointer = refresh.root / 'current.json'
    pointer.write_text(json.dumps({'generation': old.name, 'finished_at': '2026-09-10T21:00:00Z',
                                   'data_as_of': '2026-09-10'}))
    before = pointer.read_bytes()
    (tmp_path / 'sp100_symbols.csv').write_bytes(content)
    for _ in range(2):
        assert refresh.reserve()
        refresh.run()
        assert refresh.status()['status'] == 'failed'
        assert refresh.status()['completed'] == 0
        assert pointer.read_bytes() == before
        provider.assert_not_called()


def test_count_and_turnover_guards():
    symbols = [f"A{i}" for i in range(30)]
    validate_membership_change("dow_jones", symbols, [])
    validate_membership_change("dow_jones", symbols[:-1] + ["NEW"], symbols)
    with pytest.raises(ValueError, match="count"):
        validate_membership_change("dow_jones", symbols[:-1], symbols)
    with pytest.raises(ValueError, match="10%"):
        validate_membership_change("dow_jones", [f"B{i}" for i in range(30)], symbols)


def test_observation_history_records_diff_not_effective_date(tmp_path):
    path = tmp_path / "symbols.csv"
    save_membership(path, b"symbol\nAAPL\nMSFT\n", "test")
    save_membership(path, b"symbol\nAAPL\nNVDA\n", "test")
    files = sorted((tmp_path / "membership_history" / "symbols").glob("*.json"))
    assert len(files) == 2
    record = json.loads(files[-1].read_text())
    assert record["added"] == ["NVDA"]
    assert record["removed"] == ["MSFT"]
    assert record["previous_symbols"] == ["AAPL", "MSFT"]
    assert record["effective_date"] is None
    assert record["official"] is False


def test_bad_download_preserves_cached_membership(tmp_path, monkeypatch):
    path = tmp_path / "dow_jones_symbols.csv"
    original = "symbol\n" + "\n".join(f"A{i}" for i in range(30)) + "\n"
    path.write_text(original)
    monkeypatch.setattr("qx.data.universe._is_fresh_cache", lambda _: False)
    result = UniverseLoader(tmp_path)._load_cached("dow_jones", lambda: ["AAPL"])
    assert len(result) == 30
    assert path.read_text() == original
    assert not path.with_suffix(".meta.json").exists()


def test_invalid_first_download_fails_without_cache(tmp_path):
    with pytest.raises(ValueError, match="count"):
        UniverseLoader(tmp_path)._load_cached("dow_jones", lambda: ["AAPL"])
    assert not (tmp_path / "dow_jones_symbols.csv").exists()


def test_movers_rejects_duplicate_members_before_loading_prices(tmp_path):
    (tmp_path / "sp500_symbols.csv").write_text("symbol\nAAA\nAAA\n")
    with pytest.raises(ValueError, match="duplicate"):
        stock_movers(tmp_path / "bars", "sp500")
