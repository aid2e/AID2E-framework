"""AID2E Optimizers module - MOBO and MOEA algorithms.

This module provides various optimization algorithms for multi-objective
optimization problems, including:

- BaseOptimizer: Abstract base class defining common optimizer interface
- AxOptimizer: Bayesian optimization using Ax with Sobol initialization,
  SAASBO surrogate model, and qNEHVI acquisition function.
- _registry: Auto-registration system for optimizer configurations

Attributes:
    __version__: Version string inherited from the main aid2e package.
"""

from aid2e import __MAIN_VERSION__
from .base import BaseOptimizer, SearchSpace, Trial
from ._registry import register, get as get_optimizer_config

# Import ax subpackage to trigger auto-registration
from . import ax
from .ax import AxOptimizer, AxOptimizerConfig

__version__ = __MAIN_VERSION__
__all__ = [
    "BaseOptimizer",
    "SearchSpace",
    "Trial",
    "AxOptimizer",
    "AxOptimizerConfig",
    "register",
    "get_optimizer_config",
    "ax",
]
