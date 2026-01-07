"""Shared pytest fixtures for aid2e-utilities tests."""

import pytest


@pytest.fixture
def utilities_fixture():
    """Example fixture for utilities tests."""
    # Setup code here
    yield "utilities_test_data"
    # Teardown code here
