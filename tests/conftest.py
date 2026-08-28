"""Global pytest fixtures for DATS test suite."""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def env_isolation() -> Generator[None, None, None]:
    """Snapshot and restore environment variables after every test.

    This prevents env-var leakage across tests, which is critical because
    ``pydantic-settings`` reads from ``os.environ`` at model-instantiation
    time.
    """
    original = dict(os.environ)
    yield
    # Restore original env vars
    to_remove = [k for k in os.environ if k not in original]
    for k in to_remove:
        del os.environ[k]
    for k, v in original.items():
        os.environ[k] = v
