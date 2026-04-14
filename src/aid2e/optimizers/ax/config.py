"""Pydantic models for Ax-based optimizer configuration.

This module defines the configuration schema for Ax optimizer instances.
It registers the AxOptimizerConfig model with the optimizer registry.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field
from aid2e.optimizers._registry import register


class AxOptimizerConfig(BaseModel):
    """Configuration for Ax optimizer.
    
    This model defines the parameters for Ax-based Bayesian optimization
    using Sobol initialization, SAASBO surrogate model, and qNEHVI acquisition.
    
    Attributes:
        initialization_strategy: The initialization method for the search.
            Defaults to "sobol" for Sobol quasi-random sampling.
        surrogate_model: The surrogate model type. Defaults to "saasbo" for
            Scalable Asynchronous Adaptive Bayesian Optimization.
        acquisition_function: The acquisition function for candidate selection.
            Defaults to "qnehvi" for Batched Noisy Expected Hypervolume Improvement.
        n_initial_samples: Number of samples to evaluate in the initialization phase.
        n_iterations: Total number of optimization iterations.
        batch_size: Number of candidates to evaluate in each iteration.
        seed: Random seed for reproducibility. If None, results may vary.
    
    Examples:
        >>> config = AxOptimizerConfig(
        ...     initialization_strategy="sobol",
        ...     surrogate_model="saasbo",
        ...     acquisition_function="qnehvi",
        ...     n_initial_samples=10,
        ...     n_iterations=50,
        ...     batch_size=5,
        ...     seed=42
        ... )
        >>> config.initialization_strategy
        'sobol'
    
    Notes:
        All default values are chosen for robust multi-objective Bayesian optimization.
        The combination of Sobol, SAASBO, and qNEHVI is well-suited for high-dimensional
        problems with multiple competing objectives.
    """
    
    initialization_strategy: Literal["sobol", "random", "center"] = Field(
        default="sobol",
        description=(
            "Initialization strategy: 'sobol' for quasi-random initialization, "
            "'random' for uniform random initialization, or 'center' for one "
            "center point followed by additional initialization samples."
        ),
    )
    surrogate_model: Literal["saasbo", "gpei", "modular_botorch"] = Field(
        default="saasbo",
        description=(
            "Surrogate model type: 'saasbo', 'gpei', or 'modular_botorch' "
            "(Ax Modular BoTorch generator)."
        ),
    )
    acquisition_function: Literal["qnehvi", "qlognehvi", "qlognei"] = Field(
        default="qnehvi",
        description=(
            "Acquisition function preference. For modular BoTorch mode, Ax may "
            "dispatch to its compatible default if explicit mapping is unavailable."
        ),
    )
    n_initial_samples: int = Field(
        default=10,
        ge=1,
        description="Number of samples in the initialization phase."
    )
    n_iterations: int = Field(
        default=50,
        ge=1,
        description="Total number of optimization iterations."
    )
    batch_size: int = Field(
        default=1,
        ge=1,
        description="Number of candidates to evaluate per iteration."
    )
    seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducibility. If None, results are non-deterministic."
    )


# Auto-register with the optimizer registry
register("ax", AxOptimizerConfig)
