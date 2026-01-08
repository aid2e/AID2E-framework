"""Tests for aid2e.optimizers module."""

import pytest


def test_optimizers_module_import():
    """Test that aid2e.optimizers module can be imported."""
    import aid2e.optimizers
    assert aid2e.optimizers is not None


def test_optimizers_module_has_version():
    """Test that aid2e.optimizers has a version attribute."""
    import aid2e.optimizers
    assert hasattr(aid2e.optimizers, '__version__')
    assert isinstance(aid2e.optimizers.__version__, str)


def test_optimizers_module_structure():
    """Test that optimizers module has expected structure."""
    import aid2e.optimizers
    # Module should be importable and have basic attributes
    assert hasattr(aid2e.optimizers, '__name__')
    assert aid2e.optimizers.__name__ == 'aid2e.optimizers'


def test_from_optimizers_import():
    """Test importing from aid2e.optimizers works."""
    from aid2e import optimizers
    assert optimizers is not None
    assert hasattr(optimizers, '__version__')
