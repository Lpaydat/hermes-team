"""Pytest fixtures shared across all tests."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_storage_file():
    """Temp file path that does NOT exist — for testing fresh-load behavior."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)
