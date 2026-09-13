import pytest

from qx.data.membership_audit import audit_membership
from qx.data.stock_refresh import StockRefresh
from qx.data.dashboard_refresh import DashboardRefresh


def test_valid_structure_does_not_certify_membership(tmp_path):
    (tmp_path / "dow_jones_symbols.csv").write_text("symbol\n" + "\n".join(f"A{i}" for i in range(30)))
    report = audit_membership(tmp_path, "dow_jones")
    assert report["structure_valid"]
    assert report["count"] == 30
    assert not report["official_verified"]
    assert len(report["missing_evidence"]) == 3


def test_missing_membership_and_unknown_universe(tmp_path):
    assert not audit_membership(tmp_path, "sp500")["structure_valid"]
    with pytest.raises(ValueError):
        audit_membership(tmp_path, "../unknown")


def test_stock_reservation_does_not_claim_etf_count(tmp_path):
    refresh = StockRefresh(tmp_path, lambda: None, "sp500")
    assert refresh.reserve()
    assert refresh.status()["total"] == 0


@pytest.mark.parametrize("content", ["[]", "null", "42"])
def test_status_survives_invalid_metadata_shape(tmp_path, content):
    refresh = DashboardRefresh(tmp_path / "bars", lambda: None)
    refresh.root.mkdir()
    (refresh.root / "current.json").write_text(content)
    assert refresh.status()["storage_warning"]
