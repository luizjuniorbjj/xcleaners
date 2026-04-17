"""Configuration tests."""
import pytest
import os
import importlib


def test_secret_key_required(monkeypatch):
    """SECRET_KEY must be set — app should fail with empty/missing value.

    Sets SECRET_KEY="" so load_dotenv(override=False) won't re-inject from .env.
    config.py's `if not SECRET_KEY` covers both missing and empty.
    """
    import app.config as config_module

    monkeypatch.setenv("SECRET_KEY", "")

    try:
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            importlib.reload(config_module)
    finally:
        monkeypatch.undo()
        importlib.reload(config_module)


def test_secret_key_present():
    """SECRET_KEY is set in test environment."""
    # conftest.py sets this before tests run
    assert os.environ.get("SECRET_KEY") is not None
