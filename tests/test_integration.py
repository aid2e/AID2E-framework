"""Integration tests for aid2e package."""

import pytest


def test_all_modules_importable():
    """Test that all major modules can be imported together."""
    import aid2e.cli
    import aid2e.optimizers
    import aid2e.schedulers
    import aid2e.utilities.configurations
    import aid2e.utilities.epic_utils
    
    assert aid2e.cli is not None
    assert aid2e.optimizers is not None
    assert aid2e.schedulers is not None
    assert aid2e.utilities.configurations is not None
    assert aid2e.utilities.epic_utils is not None


def test_from_aid2e_import():
    """Test importing modules from aid2e package."""
    from aid2e import cli, optimizers, schedulers
    assert cli is not None
    assert optimizers is not None
    assert schedulers is not None


def test_utilities_nested_import():
    """Test nested utilities imports work correctly."""
    from aid2e.utilities.configurations import load_config
    from aid2e.utilities.epic_utils import epic_design_config
    
    assert callable(load_config)
    assert epic_design_config is not None


def test_namespace_consistency():
    """Test that namespace imports are consistent."""
    import aid2e.cli as cli1
    from aid2e import cli as cli2
    
    # Both should reference the same module
    assert cli1.__name__ == cli2.__name__
    assert cli1 is cli2


def test_no_old_import_paths():
    """Test that old flat import paths don't work (configurations, epic_utils at top level)."""
    with pytest.raises(ModuleNotFoundError):
        import configurations
    
    with pytest.raises(ModuleNotFoundError):
        import epic_utils
