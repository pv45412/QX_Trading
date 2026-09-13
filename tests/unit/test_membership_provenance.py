import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import pytest
from qx.data.membership import save_membership, membership_provenance, membership_source


def test_unknown_legacy_and_modified_membership(tmp_path):
    path = tmp_path / "symbols.csv"
    path.write_text("symbol\nAAPL\n")
    assert membership_provenance(path)["retrieved_at"] is None
    save_membership(path, path.read_bytes(), "https://example.com/membership")
    result = membership_provenance(path)
    assert result["retrieved_at"] is not None
    assert result["effective_date"] is None
    assert result["official"] is False
    path.write_text("symbol\nMSFT\n")
    assert membership_provenance(path)["source"] == "unknown"


def test_future_and_malformed_provenance_fails_closed(tmp_path):
    path = tmp_path / "symbols.csv"
    save_membership(path, b"symbol\nAAPL\n", "test")
    sidecar = path.with_suffix(".meta.json")
    value = json.loads(sidecar.read_text())
    value["retrieved_at"] = "2999-01-01T00:00:00+00:00"
    sidecar.write_text(json.dumps(value))
    assert membership_provenance(path)["source"] == "unknown"
    sidecar.write_text("[]")
    assert membership_provenance(path)["source"] == "unknown"


@pytest.mark.parametrize("failure", ["bool_version", "float_version", "blank_source", "duplicate_source",
                                   "duplicate_timestamp", "invalid_csv", "naive_time", "numeric_time"])
def test_provenance_rejects_ambiguous_or_invalid_evidence(tmp_path, failure):
    path = tmp_path / "symbols.csv"
    save_membership(path, b"symbol\nAAPL\n", "fixture")
    sidecar = path.with_suffix('.meta.json')
    record = json.loads(sidecar.read_text())
    if failure == "bool_version":
        record['schema_version'] = True
    elif failure == "float_version":
        record['schema_version'] = 1.0
    elif failure == "blank_source":
        record['source'] = '   '
    elif failure == "naive_time":
        record['retrieved_at'] = '2026-01-01T12:00:00'
    elif failure == "numeric_time":
        record['retrieved_at'] = 123
    elif failure == "invalid_csv":
        content = b'symbol,sector\nAAPL,Tech,EXTRA\n'
        path.write_bytes(content)
        record['sha256'] = sha256(content).hexdigest()
    value = json.dumps(record)
    if failure.startswith('duplicate_'):
        key, first = ('source', 'other') if failure == 'duplicate_source' else ('retrieved_at', '2999-01-01T00:00:00Z')
        value = '{' + json.dumps(key) + ':' + json.dumps(first) + ',' + value[1:]
    sidecar.write_text(value)
    assert membership_provenance(path)['source'] == 'unknown'


def test_bound_retrieval_uses_callers_cutoff_not_official_claims():
    content = b'symbol\nAAPL\n'
    cutoff = datetime(2026, 9, 11, 19, tzinfo=timezone.utc)
    record = {'schema_version': 1, 'sha256': sha256(content).hexdigest(), 'source': 'fixture',
              'retrieved_at': cutoff.isoformat(), 'official': True, 'effective_date': '2026-09-01'}
    metadata = json.dumps(record).encode()
    assert membership_source(content, metadata, as_of=cutoff) == ('fixture', cutoff)
    with pytest.raises(ValueError, match='retrieval'):
        membership_source(content, metadata, as_of=cutoff - timedelta(seconds=1))
    with pytest.raises(ValueError, match='aware'):
        membership_source(content, metadata, as_of=cutoff.replace(tzinfo=None))


@pytest.mark.parametrize('source', ['', '   ', None, 123])
def test_invalid_source_is_not_published(tmp_path, source):
    path = tmp_path / 'symbols.csv'
    save_membership(path, b'symbol\nAAPL\n', 'fixture')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='source'):
        save_membership(path, b'symbol\nMSFT\n', source)
    assert {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()} == before
