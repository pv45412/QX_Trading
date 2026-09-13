from types import SimpleNamespace
import pandas as pd
import pytest
from qx.data import holdings


def test_holdings_sorted_cached_and_attributed(monkeypatch):
    calls=[]
    def ticker(symbol):
        calls.append(symbol)
        return SimpleNamespace(funds_data=SimpleNamespace(top_holdings=pd.DataFrame(
            {'Name':['Apple','Nvidia'],'Holding Percent':[.12,.15]},index=['AAPL','NVDA'])))
    monkeypatch.setattr(holdings.yf,'Ticker',ticker)
    holdings.top_holdings.cache_clear()
    result=holdings.top_holdings('XLK',1)
    assert result['rows'][0]['symbol']=='NVDA'
    assert result['holdings_as_of'] is None
    assert result['source']=='Yahoo Finance fund data'
    holdings.top_holdings('XLK',1)
    assert len(calls)==1
    holdings.top_holdings.cache_clear()


def test_invalid_weight_fails(monkeypatch):
    monkeypatch.setattr(holdings.yf,'Ticker',lambda symbol: SimpleNamespace(
        funds_data=SimpleNamespace(top_holdings=pd.DataFrame(
            {'Name':['Invalid'],'Holding Percent':[float('nan')]},index=['BAD']))))
    holdings.top_holdings.cache_clear()
    with pytest.raises(ValueError):
        holdings.top_holdings('XLK',2)


def test_persistent_cache_preserves_timestamp_on_provider_failure(monkeypatch, tmp_path):
    payload={'symbol':'XLK','source':'Yahoo Finance fund data','retrieved_at':'2026-01-01T12:00:00+00:00',
             'rows':[{'symbol':'AAPL','name':'Apple','weight':.2}]}
    monkeypatch.setattr(holdings,'top_holdings',lambda *args: payload)
    first=holdings.cached_top_holdings('XLK',1,tmp_path)
    assert first['stale_holdings'] is False
    def fail(*args):
        raise RuntimeError('provider unavailable')
    monkeypatch.setattr(holdings,'top_holdings',fail)
    cached=holdings.cached_top_holdings('XLK',2,tmp_path)
    assert cached['stale_holdings'] is True
    assert cached['retrieved_at']==payload['retrieved_at']
    assert cached['rows']==payload['rows']
    (tmp_path/'XLK.json').write_text('{"symbol":"XLE","rows":[]}',encoding='utf-8')
    with pytest.raises(ValueError):
        holdings.cached_top_holdings('XLK',3,tmp_path)
    with pytest.raises(ValueError):
        holdings.cached_top_holdings('../XLK',3,tmp_path)
