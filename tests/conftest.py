"""Shared pytest fixtures for integration tests."""

import pytest


@pytest.fixture
def sample_integration_fixture():
    """Example fixture for integration tests."""
    # Setup code here
    yield "integration_test_data"
    # Teardown code here
