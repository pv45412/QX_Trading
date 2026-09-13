from copy import deepcopy

import pandas as pd

from qx.market.holding_analytics import enrich_holdings


def write(path, symbol, shift=0):
    prices = list(range(100, 130))
    dates = pd.bdate_range('2026-01-01', periods=30, name='Date') + pd.Timedelta(days=shift)
    pd.DataFrame({key: prices for key in ('open','high','low','close','volume')},
                 index=dates).to_csv(path / f'{symbol}_1y.csv')


def test_holdings_enriched_without_changing_cached_payload(tmp_path):
    write(tmp_path, 'SPY')
    write(tmp_path, 'AAPL')
    payload = {'rows': [{'symbol':'AAPL','weight':.2,'name':'Apple'},
                        {'symbol':'MISSING','weight':.1,'name':'Missing'}]}
    original = deepcopy(payload)
    result = enrich_holdings(payload, tmp_path)
    assert payload == original
    assert result['analytics_coverage'] == 1
    assert result['rows'][0]['analytics']['rs_change'] == 0
    assert result['rows'][0]['analytics']['source'] == 'unknown'
    assert result['rows'][1]['analytics'] is None


def test_dates_must_align_and_external_symbols_cannot_address_files(tmp_path):
    write(tmp_path, 'SPY')
    write(tmp_path, 'AAPL', shift=1)
    payload = {'rows': [{'symbol':'AAPL'}, {'symbol':'../SPY'}, {'symbol':'/SPY'}]}
    assert enrich_holdings(payload, tmp_path)['analytics_coverage'] == 0


def test_missing_benchmark_keeps_holdings(tmp_path):
    write(tmp_path, 'AAPL')
    payload = {'rows': [{'symbol':'AAPL','weight':.2}]}
    result = enrich_holdings(payload, tmp_path)
    assert result['rows'][0]['weight'] == .2
    assert result['rows'][0]['analytics'] is None
