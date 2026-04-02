"""PyMOO-based evolutionary optimization for AID2E framework.

This subpackage provides NSGA-II, NSGA-III, and MOEA/D via the PyMOO library,
integrated with the AID2E ``BaseOptimizer`` interface using PyMOO's ask/tell
protocol for external evaluation.
"""

from .config import PyMOOOptimizerConfig
from .optimizer import PyMOOOptimizer

__all__ = ["PyMOOOptimizer", "PyMOOOptimizerConfig"]
