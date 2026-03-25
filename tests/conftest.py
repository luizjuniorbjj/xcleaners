"""Xcleaners Test Configuration."""
import pytest
import os

# Set test environment before importing app
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["ENCRYPTION_KEY"] = "test-encryption-key-32chars!!!"
os.environ["DATABASE_URL"] = ""  # Empty to prevent real DB connection
os.environ["DEBUG"] = "true"


@pytest.fixture
def anyio_backend():
    return "asyncio"
