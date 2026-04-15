"""Pydantic models for Ax-based optimizer configuration."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aid2e.optimizers._registry import register

from ._resolver import validate_generator_name


class AxOptimizerConfig(BaseModel):
    """Configuration for the AID2E Ax backend."""

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
