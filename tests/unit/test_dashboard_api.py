import pandas as pd
from qx.interfaces.web import create_app
from qx.market.dashboard_metrics import DASHBOARD_ETFS


def endpoint(path):
    return next(r.endpoint for r in create_app(path / 'none.db', path).routes
                if r.path == '/api/rotation/analytics')


def write(path, symbol):
    values = list(range(100, 130))
    pd.DataFrame({key: values for key in ('open','high','low','close','volume')},
                 index=pd.bdate_range('2026-01-01',periods=30,name='Date')).to_csv(path / f'{symbol}_1y.csv')


def test_empty_cache_keeps_universe_without_inventing_metrics(tmp_path):
    result = endpoint(tmp_path)()
    assert result['coverage'] == 0
    assert len(result['rows']) == 29
    assert result['benchmark_metrics'] is None
    assert all('rs_rank' not in row for row in result['rows'])


def test_complete_coverage_ties_have_equal_midpoint_rank(tmp_path):
    for symbol in ['SPY', 'QQQ', 'DIA', *DASHBOARD_ETFS.values()]:
        write(tmp_path, symbol)
    result = endpoint(tmp_path)()
    assert result['coverage'] == 29
    assert all(row['rs_rank'] == 50 for row in result['rows'])
    assert result['benchmark_metrics']['sessions'] == 30
    (tmp_path / 'XLE_1y.csv').unlink()
    partial = endpoint(tmp_path)()
    assert partial['coverage'] == 28
    assert all('rs_rank' not in row for row in partial['rows'])
