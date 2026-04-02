"""PyMOO-based evolutionary optimization for AID2E framework.

This subpackage provides NSGA-II, NSGA-III, and MOEA/D via the PyMOO library,
integrated with the AID2E ``BaseOptimizer`` interface using PyMOO's ask/tell
protocol for external evaluation.

``AID2EProblem`` is the public PyMOO Problem class for this search space. It
can be used in ask/tell mode (default, no eval_fn) or direct evaluation mode
(supply an eval_fn for synchronous runs via ``pymoo.optimize.minimize``).
"""

from .config import PyMOOOptimizerConfig
from .optimizer import AID2EProblem, PyMOOOptimizer

__all__ = ["AID2EProblem", "PyMOOOptimizer", "PyMOOOptimizerConfig"]
