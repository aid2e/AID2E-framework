"""Shared pytest fixtures for aid2e-schedulers tests."""

import pytest


@pytest.fixture
def scheduler_fixture():
    """Example fixture for scheduler tests."""
    # Setup code here
    yield "scheduler_test_data"
    # Teardown code here
