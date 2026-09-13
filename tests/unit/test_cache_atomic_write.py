from pathlib import Path
from unittest.mock import patch

import pytest

from qx.data.cache import _atomic_write


def test_replace_failure_preserves_cache_and_removes_temporary(tmp_path: Path):
    target = tmp_path / "bars.csv"
    target.write_bytes(b"original")
    with patch("qx.data.cache.os.replace", side_effect=OSError("locked")):
        with pytest.raises(OSError, match="locked"):
            _atomic_write(target, b"replacement")
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_write_failure_preserves_cache_and_removes_temporary(tmp_path: Path):
    target = tmp_path / "bars.csv"
    target.write_bytes(b"original")
    temporary = tmp_path / "partial.tmp"

    class FailingFile:
        name = str(temporary)

        def __enter__(self):
            temporary.write_bytes(b"partial")
            return self

        def __exit__(self, *args):
            return False

        def write(self, content):
            raise OSError("disk full")

    with patch("qx.data.cache.tempfile.NamedTemporaryFile", return_value=FailingFile()):
        with pytest.raises(OSError, match="disk full"):
            _atomic_write(target, b"replacement")
    assert target.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [target]


def test_successful_write_replaces_cache_without_temporary_files(tmp_path: Path):
    target = tmp_path / "bars.csv"
    target.write_bytes(b"original")
    _atomic_write(target, b"replacement")
    assert target.read_bytes() == b"replacement"
    assert list(tmp_path.iterdir()) == [target]
