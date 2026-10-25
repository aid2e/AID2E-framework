"""AID2E Optimizers module - Bayesian and evolutionary algorithms.

This module provides various optimization algorithms for multi-objective
optimization problems, including:

- BaseOptimizer: Abstract base class defining the common optimizer interface.
- AxOptimizer: Bayesian optimization using Ax with Sobol initialization,
  SAASBO surrogate model, and qNEHVI acquisition function.
- PyMOOProblem: PyMOO-only public ``Problem`` wrapper for structural ask/tell
  integrations. Ax does not expose an equivalent public problem wrapper.
- PyMOOOptimizer: Evolutionary optimization (GA, NSGA-II, NSGA-III, MOEA/D)
  via PyMOO's ask/tell interface for external evaluation.
- compute_pareto_front: Backend-agnostic Pareto front utility.

Attributes:
    __version__: Version string inherited from the main aid2e package.
"""

from aid2e import __MAIN_VERSION__
from .base import BaseOptimizer, SearchSpace, Trial, compute_pareto_front
# BEGIN modification Baptiste
# Lazy import: do not use all Ax if only for Trail
#from .ax import AxOptimizer, AxOptimizerConfig
#from .pymoo import AID2EProblem, PyMOOOptimizer, PyMOOOptimizerConfig, PyMOOProblem
# END modification Baptiste

__version__ = __MAIN_VERSION__
__all__ = [
    "BaseOptimizer",
    "SearchSpace",
    "Trial",
    "compute_pareto_front",
    "AxOptimizer",
    "AxOptimizerConfig",
    "PyMOOProblem",
    "PyMOOOptimizer",
    "PyMOOOptimizerConfig",
    "AID2EProblem",
]

# BEGIN modification Baptiste
# Lazy import: do not use all Ax if only for Trail
def __getattr__(name):
    if name in ("AxOptimizer", "AxOptimizerConfig"):
        from .ax import AxOptimizer, AxOptimizerConfig
        return {
            "AxOptimizer": AxOptimizer,
            "AxOptimizerConfig": AxOptimizerConfig,
        }[name]

    if name in (
        "PyMOOProblem",
        "PyMOOOptimizer",
        "PyMOOOptimizerConfig",
        "AID2EProblem",
    ):
        from .pymoo import (
            AID2EProblem,
            PyMOOOptimizer,
            PyMOOOptimizerConfig,
            PyMOOProblem,
        )
        return {
            "PyMOOProblem": PyMOOProblem,
            "PyMOOOptimizer": PyMOOOptimizer,
            "PyMOOOptimizerConfig": PyMOOOptimizerConfig,
            "AID2EProblem": AID2EProblem,
        }[name]

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
# END modification Baptiste