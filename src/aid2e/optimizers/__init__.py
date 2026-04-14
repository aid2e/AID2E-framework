"""AID2E Optimizers module - MOBO and MOEA algorithms.

This module provides various optimization algorithms for multi-objective
optimization problems, including:

- BaseOptimizer: Abstract base class defining the common optimizer interface.
- AxOptimizer: Bayesian optimization using Ax with Sobol initialization,
  SAASBO surrogate model, and qNEHVI acquisition function.
- PyMOOOptimizer: Evolutionary optimization (NSGA-II, NSGA-III, MOEA/D) via
  PyMOO's ask/tell interface for external evaluation.
- compute_pareto_front: Backend-agnostic Pareto front utility.
- _registry: Auto-registration system for optimizer configurations.

Attributes:
    __version__: Version string inherited from the main aid2e package.
"""

from aid2e import __MAIN_VERSION__
from .base import BaseOptimizer, SearchSpace, Trial, compute_pareto_front
from ._registry import register, get as get_optimizer_config
from .ax import AxOptimizer, AxOptimizerConfig
from .pymoo import AID2EProblem, PyMOOOptimizer, PyMOOOptimizerConfig

# Explicit aliases avoid ambiguity with the third-party `ax` package and give
# callers a stable parent-package import path for AID2E-specific optimizers.
AID2EAxOptimizer = AxOptimizer
AID2EAxOptimizerConfig = AxOptimizerConfig
AID2EPyMOOOptimizer = PyMOOOptimizer
AID2EPyMOOOptimizerConfig = PyMOOOptimizerConfig

__version__ = __MAIN_VERSION__
__all__ = [
    "BaseOptimizer",
    "SearchSpace",
    "Trial",
    "compute_pareto_front",
    "AxOptimizer",
    "AxOptimizerConfig",
    "AID2EAxOptimizer",
    "AID2EAxOptimizerConfig",
    "PyMOOOptimizer",
    "PyMOOOptimizerConfig",
    "AID2EPyMOOOptimizer",
    "AID2EPyMOOOptimizerConfig",
    "AID2EProblem",
    "register",
    "get_optimizer_config",
]

