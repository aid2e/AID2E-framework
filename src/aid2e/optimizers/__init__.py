"""AID2E Optimizers module - Bayesian and evolutionary algorithms.

This module provides various optimization algorithms for multi-objective
optimization problems, including:

- BaseOptimizer: Abstract base class defining the common optimizer interface.
- AxOptimizer: Bayesian optimization using Ax with configurable initialization
  and Modular BoTorch generation.
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
from .ax import AxOptimizer, AxOptimizerConfig
from .pymoo import PyMOOOptimizer, PyMOOOptimizerConfig, PyMOOProblem

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
]
