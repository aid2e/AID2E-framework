"""Tests for aid2e.utilities.configurations module."""

import pytest


def test_configurations_module_import():
    """Test that aid2e.utilities.configurations module can be imported."""
    import aid2e.utilities.configurations
    assert aid2e.utilities.configurations is not None


def test_configurations_module_has_version():
    """Test that configurations has a version attribute."""
    import aid2e.utilities.configurations
    assert hasattr(aid2e.utilities.configurations, '__version__')
    assert isinstance(aid2e.utilities.configurations.__version__, str)


def test_configurations_has_load_config():
    """Test that configurations module has load_config function."""
    from aid2e.utilities.configurations import load_config
    assert callable(load_config)


def test_configurations_has_full_config():
    """Test that configurations module has FullConfig class."""
    from aid2e.utilities.configurations import FullConfig
    assert FullConfig is not None


def test_configurations_module_structure():
    """Test that configurations module has expected structure."""
    import aid2e.utilities.configurations as config
    assert hasattr(config, '__name__')
    assert config.__name__ == 'aid2e.utilities.configurations'


def test_legacy_configuration_aliases_are_not_exported():
    """Legacy compatibility exports should be removed from the package."""
    import aid2e.utilities.configurations as config

    assert not hasattr(config, "Objective")
    assert not hasattr(config, "ObjectiveComputationSpec")
    assert not hasattr(config, "register_runner_config")
    assert not hasattr(config, "get_runner_config_model")
    assert not hasattr(config, "list_registered_runners")
