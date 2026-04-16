"""Tests for aid2e.utilities module."""

import pytest


def test_utilities_module_import():
    """Test that aid2e.utilities module can be imported."""
    import aid2e.utilities
    assert aid2e.utilities is not None


def test_utilities_has_configurations():
    """Test that utilities module has configurations submodule."""
    from aid2e.utilities import configurations
    assert configurations is not None


def test_utilities_has_epic_utils():
    """Test that utilities module has epic_utils submodule."""
    from aid2e.utilities import epic_utils
    assert epic_utils is not None


def test_utilities_structure():
    """Test utilities module structure."""
    import aid2e.utilities
    assert hasattr(aid2e.utilities, '__name__')
    assert aid2e.utilities.__name__ == 'aid2e.utilities'


def test_utilities_exports_runtime_builders():
    """Runtime builder functions should be exported from utilities."""
    from aid2e.utilities import (
        infer_optimizer_backend,
        build_optimizer_from_config,
        build_scheduler_runtime_config,
        build_scheduler_from_config,
        build_workflow_executor_from_config,
    )

    assert callable(infer_optimizer_backend)
    assert callable(build_optimizer_from_config)
    assert callable(build_scheduler_runtime_config)
    assert callable(build_scheduler_from_config)
    assert callable(build_workflow_executor_from_config)
