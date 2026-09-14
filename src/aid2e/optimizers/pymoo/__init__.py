"""PyMOO-based evolutionary optimization for AID2E framework.

This subpackage provides GA, NSGA-II, NSGA-III, and MOEA/D via the PyMOO
library, integrated with the AID2E ``BaseOptimizer`` interface using PyMOO's
ask/tell protocol for external evaluation.

``PyMOOProblem`` is the public PyMOO Problem class for this search space and
is structural-only for ask/tell workflows in AID2E.
"""

from .config import PyMOOOptimizerConfig
from .optimizer import PyMOOOptimizer, PyMOOProblem

__all__ = [
    "PyMOOProblem",
    "PyMOOOptimizer",
    "PyMOOOptimizerConfig",
]
