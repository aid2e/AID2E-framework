"""Tests for aid2e.schedulers module."""

import pytest


def test_schedulers_module_import():
    """Test that aid2e.schedulers module can be imported."""
    import aid2e.schedulers
    assert aid2e.schedulers is not None


def test_schedulers_module_has_version():
    """Test that aid2e.schedulers has a version attribute."""
    import aid2e.schedulers
    assert hasattr(aid2e.schedulers, '__version__')
    assert isinstance(aid2e.schedulers.__version__, str)


def test_schedulers_module_structure():
    """Test that schedulers module has expected structure."""
    import aid2e.schedulers
    # Module should be importable and have basic attributes
    assert hasattr(aid2e.schedulers, '__name__')
    assert aid2e.schedulers.__name__ == 'aid2e.schedulers'


def test_from_schedulers_import():
    """Test importing from aid2e.schedulers works."""
    from aid2e import schedulers
    assert schedulers is not None
    assert hasattr(schedulers, '__version__')
