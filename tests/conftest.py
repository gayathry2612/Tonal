"""
Shared pytest fixtures.

QCoreApplication (no display required) is enough for QObject-based tests.
This lets the library/core tests run headlessly on CI without a display server.
"""
import sys
import pytest
from PySide6.QtCore import QCoreApplication


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QCoreApplication — created once, reused across all tests."""
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv[:1])
    yield app
