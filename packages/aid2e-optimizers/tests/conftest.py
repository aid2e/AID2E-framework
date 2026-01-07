"""Shared pytest fixtures for aid2e-optimizers tests."""

import pytest


@pytest.fixture
def optimizer_fixture():
    """Example fixture for optimizer tests."""
    # Setup code here
    yield "optimizer_test_data"
    # Teardown code here
