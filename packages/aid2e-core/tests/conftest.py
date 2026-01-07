"""Shared pytest fixtures for aid2e-core tests."""

import pytest


@pytest.fixture
def core_fixture():
    """Example fixture for core tests."""
    # Setup code here
    yield "core_test_data"
    # Teardown code here
