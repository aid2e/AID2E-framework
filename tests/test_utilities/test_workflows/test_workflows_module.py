"""Tests for aid2e.utilities.workflows module."""

import pytest

def test_workflows_module_import():
    """Test that aid2e.utilities.workflows can be imported."""
    import aid2e.utilities.workflows
    assert aid2e.utilities.workflows is not None


def test_workflows_module_has_version():
    """Test that workflows has a version attribute."""
    import aid2e.utilities.workflows
    assert hasattr(aid2e.utilities.workflows, '__version__')
    assert isinstance(aid2e.utilities.workflows.__version__, str)


def test_stack_layer():
    """Test that workflows module has StackLayer class."""
    from aid2e.utilities.workflows import StackLayer
    assert StackLayer is not None


def test_ana_layer():
    """Test that workflows module has AnaLayer class."""
    from aid2e.utilities.workflows import AnaLayer
    assert AnaLayer is not None


def test_experiment_stack():
    """Test that workflows module has ExperimentStack class."""
    from aid2e.utilities.workflows import ExperimentStack
    assert ExperimentStack is not None


def test_workflows_module_structure():
    """Test that workflows module has expected structure."""
    import aid2e.utilities.workflows as work
    assert hasattr(work, '__name__')
    assert work.__name__ == 'aid2e.utilities.workflows'
