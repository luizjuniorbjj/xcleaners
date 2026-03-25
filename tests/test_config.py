"""Configuration tests."""
import pytest
import os
import importlib


def test_secret_key_required():
    """SECRET_KEY must be set — app should fail without it."""
    # Ensure the module is imported first (with the key present from conftest)
    import app.config as config_module

    original = os.environ.get("SECRET_KEY")
    os.environ.pop("SECRET_KEY", None)

    try:
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            importlib.reload(config_module)
    finally:
        # Always restore so subsequent tests are unaffected
        if original is not None:
            os.environ["SECRET_KEY"] = original
        # Re-import with valid key to reset module state
        importlib.reload(config_module)


def test_secret_key_present():
    """SECRET_KEY is set in test environment."""
    # conftest.py sets this before tests run
    assert os.environ.get("SECRET_KEY") is not None
