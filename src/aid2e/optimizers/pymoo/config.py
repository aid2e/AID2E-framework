"""Pydantic configuration model for PyMOO-based optimizers.

Supported algorithms and their best use cases:

- ``ga``: Single-objective Genetic Algorithm.
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


PyMOOAlgorithm = Literal["ga", "nsga2", "nsga3", "moead"]


class PyMOOOptimizerConfig(BaseModel):
    """Configuration for PyMOO-based evolutionary optimizers.

    Attributes:
        algorithm: Optional evolutionary algorithm identifier. If omitted,
            AID2E infers ``"ga"`` for single-objective problems and
            ``"nsga2"`` for multi-objective problems.
        pop_size: Population size (number of individuals per generation).
        n_offsprings: Number of offspring generated each generation.  ``None``
            defaults to ``pop_size``.
        crossover_prob: Simulated Binary Crossover (SBX) probability.
        crossover_eta: SBX distribution index — larger values produce offspring
            closer to the parents.
        mutation_eta: Polynomial mutation distribution index.
        n_iterations: Number of generations to run when using this config in
            declarative/runtime-driven flows.
        n_partitions: Reference-direction partitions for NSGA-III and MOEA/D.
            The total number of reference directions grows combinatorially with
            this value and ``n_objectives``.  Ignored for NSGA-II.
        seed: Random seed for reproducibility.  ``None`` yields non-deterministic
            results.
        verbose: Whether PyMOO prints per-generation progress to stdout.

    Examples:
        >>> config = PyMOOOptimizerConfig(
        ...     pop_size=100,
        ...     seed=42,
        ... )
        >>> config.algorithm is None
        True
        >>> config2 = PyMOOOptimizerConfig(algorithm="nsga3", n_partitions=12)

    Notes:
        - ``ga`` is the recommended default for single-objective problems.
        - NSGA-II is the recommended default for 2-objective problems.
        - For 3+ objectives consider NSGA-III or MOEA/D — their reference
          direction structures are better suited to high-dimensional fronts.
        - ``n_partitions`` has a strong effect on runtime for NSGA-III/MOEA/D;
          start with 12 for 2-3 objectives and reduce for 4+ objectives.
    """

    algorithm: Optional[PyMOOAlgorithm] = Field(
        default=None,
        description=(
            "Optional evolutionary algorithm. If omitted, AID2E infers 'ga' "
            "for single-objective problems and 'nsga2' for multi-objective problems."
        ),
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
    n_iterations: int = Field(
        default=50,
        ge=1,
        description="Number of generations for runtime-driven optimization loops.",
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

    def resolve_algorithm(self, n_objectives: int) -> PyMOOAlgorithm:
        """Resolve the algorithm for the given objective count.

        Args:
            n_objectives: Number of objectives in the optimization problem.

        Returns:
            Concrete PyMOO algorithm identifier.

        Raises:
            ValueError: If the configured explicit algorithm is incompatible
                with the objective count.
        """
        if n_objectives < 1:
            raise ValueError("n_objectives must be >= 1")

        if self.algorithm is None:
            return "ga" if n_objectives == 1 else "nsga2"

        if self.algorithm == "ga" and n_objectives != 1:
            raise ValueError(
                "PyMOO algorithm 'ga' only supports single-objective problems. "
                f"Received {n_objectives} objectives."
            )

        if self.algorithm in {"nsga2", "nsga3", "moead"} and n_objectives == 1:
            raise ValueError(
                f"PyMOO algorithm '{self.algorithm}' requires a multi-objective "
                "problem. Use 'ga' or omit 'algorithm' for single-objective optimization."
            )

        return self.algorithm


# Auto-register with the optimizer config registry
register("pymoo", PyMOOOptimizerConfig)
