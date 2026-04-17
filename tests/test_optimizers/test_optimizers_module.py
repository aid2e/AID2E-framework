"""Tests for aid2e.optimizers module."""

import numpy as np
import pytest

from aid2e.utilities.configurations.base_models import ChoiceParameter, RangeParameter


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


def test_legacy_optimizer_aliases_are_not_exported():
    """Legacy parent-package optimizer aliases should be removed."""
    import aid2e.optimizers as optimizers

    assert not hasattr(optimizers, "AID2EAxOptimizer")
    assert not hasattr(optimizers, "AID2EAxOptimizerConfig")
    assert not hasattr(optimizers, "AID2EPyMOOOptimizer")
    assert not hasattr(optimizers, "AID2EPyMOOOptimizerConfig")


def test_optimizer_registry_helpers_are_not_exported():
    """Config registry helpers should not be exported from aid2e.optimizers."""
    import aid2e.optimizers as optimizers

    assert not hasattr(optimizers, "register")
    assert not hasattr(optimizers, "get_optimizer_config")


def test_pymoo_problem_exports_are_available():
    """PyMOO problem symbols should be exported at both package levels."""
    from aid2e import optimizers
    from aid2e.optimizers import AID2EProblem, PyMOOProblem
    from aid2e.optimizers.pymoo import (
        AID2EProblem as PymooAID2EProblem,
        PyMOOProblem as PymooProblem,
    )

    assert optimizers.PyMOOProblem is PyMOOProblem
    assert optimizers.AID2EProblem is AID2EProblem
    assert PymooProblem is PyMOOProblem
    assert PymooAID2EProblem is AID2EProblem


def test_aid2e_problem_alias_warns_and_behaves_like_pymoo_problem():
    """Deprecated alias should warn and still decode candidates correctly."""
    from aid2e.optimizers import AID2EProblem, PyMOOProblem

    param_items = [
        ("x", RangeParameter(name="x", value=0.5, bounds=(0.0, 1.0))),
        ("mode", ChoiceParameter(name="mode", value="a", choices=["a", "b", "c"])),
    ]
    kwargs = {
        "n_var": 2,
        "n_obj": 1,
        "xl": np.array([0.0, 0.0], dtype=float),
        "xu": np.array([1.0, 2.0], dtype=float),
        "param_items": param_items,
        "objective_names": ["loss"],
    }

    canonical_problem = PyMOOProblem(**kwargs)
    with pytest.deprecated_call(
        match="AID2EProblem is deprecated.*Use PyMOOProblem instead"
    ):
        deprecated_problem = AID2EProblem(**kwargs)

    decoded = np.array([0.25, 1.6], dtype=float)
    assert isinstance(deprecated_problem, PyMOOProblem)
    assert deprecated_problem.decode_x(decoded) == canonical_problem.decode_x(decoded)
