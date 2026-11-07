"""Pytest configuration and QApplication fixture."""

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Ensure QApplication exists during test execution."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

