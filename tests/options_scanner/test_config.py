from qx.options_scanner.config import get_scanner_config, ScannerConfig


def test_scanner_config_defaults():
    config = get_scanner_config()
    assert isinstance(config, ScannerConfig)
    assert config.config_version == "1.0.0"
    assert config.liquidity.max_option_spread_pct == 0.08
    assert config.liquidity.min_open_interest == 100
    assert config.blackouts.normal_mode_earnings_days == 5
    assert config.blackouts.fomc_cpi_event_hours == 48
    assert config.ewma.span == 20
    assert config.ewma.decay_lambda == 0.94
    assert config.grades.a_plus == 90.0
    assert config.grades.a == 80.0
    assert config.grades.b == 70.0
