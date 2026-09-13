import pandas as pd
import pytest
from fastapi import HTTPException
from qx.interfaces.web import create_app


def endpoint(tmp_path):
    return next(r.endpoint for r in create_app(tmp_path / 'none.db', tmp_path).routes
                if r.path == '/api/rotation/{symbol}/line')


def write_bars(path, values, dates=None):
    pd.DataFrame({'open': values, 'high': values, 'low': values, 'close': values,
                  'volume': [100]*len(values)},
                 index=pd.DatetimeIndex(dates or ['2026-09-01','2026-09-02'], name='Date')).to_csv(path)


def test_ratio_uses_aligned_cached_closes(tmp_path):
    write_bars(tmp_path / 'XLK_1y.csv', [100,110])
    write_bars(tmp_path / 'SPY_1y.csv', [200,200])
    result = endpoint(tmp_path)('xlk')
    assert [p['ratio'] for p in result['points']] == [.5,.55]
    assert result['sector_source'] == 'unknown'
    assert result['status'] == 'CACHED_UNVERIFIED'


def test_mismatched_dates_do_not_make_chart(tmp_path):
    write_bars(tmp_path / 'XLK_1y.csv', [100,110])
    write_bars(tmp_path / 'SPY_1y.csv', [200,200], ['2026-09-02','2026-09-03'])
    with pytest.raises(HTTPException) as error:
        endpoint(tmp_path)('XLK')
    assert error.value.status_code == 503


def test_symbols_cannot_address_files(tmp_path):
    with pytest.raises(HTTPException) as error:
        endpoint(tmp_path)('../SPY')
    assert error.value.status_code == 404
