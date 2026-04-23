"""Pydantic models for Ax-based optimizer configuration."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aid2e.utilities.configurations.optimization_registry import register

from ._resolver import validate_generator_name


class AxOptimizerConfig(BaseModel):
    """Configure the Ax optimizer backend for AID2E.

    Define the tuning parameters used by the Ax-based Bayesian optimization
    workflow, including initialization behavior, model-generation settings, and
    core iteration controls.

    Attributes:
        initialization_strategy: Choose how the initial design points are drawn
            before model-based generation begins. Supported values are
            ``"sobol"``, ``"uniform"``, and ``"center"``.
        generator: Specify the Ax generator enum name used for model-based
            candidate generation. The default is ``"BOTORCH_MODULAR"``.
        generator_kwargs: Provide keyword arguments for Ax ``GeneratorSpec``
            setup (for example, model configuration details).
        generator_gen_kwargs: Provide generation-time keyword arguments passed
            into Ax candidate generation (for example,
            ``model_gen_options`` budgets).
        objective_thresholds: Optionally map objective metric names to
            threshold values for multi-objective optimization.
        n_initial_samples: Set the number of initialization trials.
        n_iterations: Set the total optimization iteration budget.
        batch_size: Set the number of candidates proposed per iteration.
        seed: Set an optional random seed for reproducibility.

    Examples:
        >>> config = AxOptimizerConfig(
        ...     initialization_strategy="sobol",
        ...     generator="BOTORCH_MODULAR",
        ...     generator_kwargs={"fit_out_of_design": False},
        ...     generator_gen_kwargs={"model_gen_options": {"acqf_optimizer_kwargs": {"num_restarts": 8}}},
        ...     n_initial_samples=12,
        ...     n_iterations=60,
        ...     batch_size=2,
        ...     seed=42,
        ... )
        >>> config.generator
        'BOTORCH_MODULAR'

    Notes:
        Legacy fields such as ``surrogate_model`` and
        ``acquisition_function`` are explicitly rejected.
    """
    # TODO: Remove the extra fields once the legacy config surface is fully retired.
    model_config = ConfigDict(extra="forbid")
    initialization_strategy: Literal["sobol", "uniform", "center"] = Field(
        default="sobol",
        description=(
            "Initialization strategy: 'sobol' for quasi-random initialization, "
            "'uniform' for uniform random initialization, or 'center' for one "
            "center point followed by additional initialization samples."
        ),
    )
    generator: str = Field(
        default="BOTORCH_MODULAR",
        description=(
            "Ax generator enum name. This backend currently supports "
            "'BOTORCH_MODULAR' and treats it as the default model-based backend."
        ),
    )
    generator_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Keyword arguments passed to Ax's GeneratorSpec for the configured "
            "model-based generator. YAML-friendly string values are resolved to "
            "supported Ax / BoTorch classes at runtime."
        ),
    )
    generator_gen_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Generation-time kwargs passed through Ax into candidate generation, "
            "such as optimizer budgets under 'model_gen_options'."
        ),
    )
    objective_thresholds: Optional[dict[str, float]] = Field(
        default=None,
        description=(
            "Optional objective thresholds for multi-objective optimization, "
            "keyed by metric name."
        ),
    )
    n_initial_samples: int = Field(
        default=10,
        ge=1,
        description="Number of samples in the initialization phase.",
    )
    n_iterations: int = Field(
        default=50,
        ge=1,
        description="Total number of optimization iterations.",
    )
    batch_size: int = Field(
        default=1,
        ge=1,
        description="Number of candidates to evaluate per iteration.",
    )
    seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducibility. If None, results are non-deterministic.",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_fields(cls, raw_value: Any) -> Any:
        """Fail fast on the retired Ax config surface."""
        if not isinstance(raw_value, dict):
            return raw_value

        legacy_fields = [
            field_name
            for field_name in ("surrogate_model", "acquisition_function")
            if field_name in raw_value
        ]
        if legacy_fields:
            joined = ", ".join(legacy_fields)
            raise ValueError(
                f"AxOptimizerConfig no longer accepts legacy fields: {joined}. "
                "Use 'generator', 'generator_kwargs', and 'generator_gen_kwargs' "
                "instead."
            )
        return raw_value

    @field_validator("generator")
    @classmethod
    def normalize_generator(cls, value: str) -> str:
        """Normalize the configured generator to an Ax enum-style name."""
        return validate_generator_name(value)


register("ax", AxOptimizerConfig)
