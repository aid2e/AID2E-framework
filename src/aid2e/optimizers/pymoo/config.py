"""Pydantic configuration model for PyMOO-based optimizers.

Supported algorithms and their best use cases:

- ``nsga2``: NSGA-II — fast, well-tested, good for 2-3 objectives.
- ``nsga3``: NSGA-III — structured reference directions, 3+ objectives.
- ``moead``: MOEA/D — weight-decomposition, highly customisable, 3+ objectives.

Auto-registration with the optimizer registry happens at import time so that
``get_optimizer_config("pymoo")`` works immediately after importing this package.

Project: AID2E v0.0.0 — AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/AID2E-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field

from aid2e.optimizers._registry import register


class PyMOOOptimizerConfig(BaseModel):
    """Configuration for PyMOO-based evolutionary optimizers.

    Attributes:
        algorithm: Evolutionary algorithm identifier.  Defaults to ``"nsga2"``.
        pop_size: Population size (number of individuals per generation).
        n_offsprings: Number of offspring generated each generation.  ``None``
            defaults to ``pop_size`` (standard for NSGA-II).
        crossover_prob: Simulated Binary Crossover (SBX) probability.
        crossover_eta: SBX distribution index — larger values produce offspring
            closer to the parents.
        mutation_eta: Polynomial mutation distribution index.
        n_partitions: Reference-direction partitions for NSGA-III and MOEA/D.
            The total number of reference directions grows combinatorially with
            this value and ``n_objectives``.  Ignored for NSGA-II.
        seed: Random seed for reproducibility.  ``None`` yields non-deterministic
            results.
        verbose: Whether PyMOO prints per-generation progress to stdout.

    Examples:
        >>> config = PyMOOOptimizerConfig(
        ...     algorithm="nsga2",
        ...     pop_size=100,
        ...     seed=42,
        ... )
        >>> config.algorithm
        'nsga2'
        >>> config2 = PyMOOOptimizerConfig(algorithm="nsga3", n_partitions=12)

    Notes:
        - NSGA-II is the recommended default for 2-objective problems.
        - For 3+ objectives consider NSGA-III or MOEA/D — their reference
          direction structures are better suited to high-dimensional fronts.
        - ``n_partitions`` has a strong effect on runtime for NSGA-III/MOEA/D;
          start with 12 for 2-3 objectives and reduce for 4+ objectives.
    """

    algorithm: Literal["nsga2", "nsga3", "moead"] = Field(
        default="nsga2",
        description="Evolutionary algorithm: 'nsga2', 'nsga3', or 'moead'.",
    )
    pop_size: int = Field(
        default=100,
        ge=2,
        description="Population size — number of candidate solutions per generation.",
    )
    n_offsprings: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "Number of offspring per generation. "
            "Defaults to pop_size when None."
        ),
    )
    crossover_prob: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="SBX crossover probability.",
    )
    crossover_eta: float = Field(
        default=15.0,
        gt=0.0,
        description="SBX crossover distribution index.",
    )
    mutation_eta: float = Field(
        default=20.0,
        gt=0.0,
        description="Polynomial mutation distribution index.",
    )
    n_partitions: int = Field(
        default=12,
        ge=1,
        description=(
            "Reference-direction partitions for NSGA-III and MOEA/D. "
            "Ignored for NSGA-II."
        ),
    )
    seed: Optional[int] = Field(
        default=None,
        description="Random seed. None means non-deterministic.",
    )
    verbose: bool = Field(
        default=False,
        description="Print per-generation statistics to stdout.",
    )


# Auto-register with the optimizer config registry
register("pymoo", PyMOOOptimizerConfig)
