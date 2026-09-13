from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_env_example_matches_schwab_first_policy() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "SCANNER_DATA_PROVIDER=schwab" in env_example
    assert "SCANNER_SCHWAB_TOKEN_PATH=data/secrets/schwab_token.json" in env_example


def test_gitignore_keeps_local_schwab_token_out_of_source_control() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "data/secrets/*" in gitignore
    assert "!data/secrets/.gitkeep" in gitignore
