"""Optimization configuration models.

Defines the optimizer selection and search space configuration. Objectives are
normalized to the unified ``ObjectiveDefinition`` model, but can still be
provided as directive strings (e.g., "minimize:f1") or mapping payloads. The
normalizer handles script/inline/multi-steps computation specs consistently with
problem-level definitions.

See `objectives.py` for the unified ObjectiveDefinition model used across
problem, optimization, and workflow layers.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field, field_validator
from .optimization_registry import get_algorithm_config_model
from .objectives import ObjectiveDefinition, ObjectiveDirection, ObjectiveComputationSpec


class OptimizerConfig(BaseModel):
    """Configuration for the optimizer algorithm."""
    name: str  # e.g., "MOBO", "Genetic", "RandomSearch"
    type: str  # e.g., "Bayesian", "evolutionary", "grid"
    
    # Algorithm-specific parameters
    parameters: Dict[str, Any] = Field(default_factory=dict)


class OptimizationConfiguration(BaseModel):
    """Complete optimization configuration."""
    name: str
    description: Optional[str] = ""
    
    # Optimization parameters
    optimizer: OptimizerConfig
    
    # Objective definitions
    objectives: List[ObjectiveDefinition] = Field(default_factory=list)
    
    # Constraint definitions
    constraints: List[str] = Field(default_factory=list)  # e.g., ["x1 < 10", "x2 > 0"]
    
    # Search space configuration
    n_iterations: int = 100
    n_initial_samples: int = 10
    parallel_evaluations: int = 1

    @field_validator("objectives", mode="before")
    @classmethod
    def normalize_objectives(cls, raw_objectives: Any) -> List[ObjectiveDefinition]:
        """Normalize objective entries to ObjectiveDefinition.

        Supports directive strings (e.g., ``"minimize:f1"``), mapping payloads,
        or already constructed ``ObjectiveDefinition`` instances.
        """
        if raw_objectives is None:
            return []

        if not isinstance(raw_objectives, list):
            raise ValueError("'objectives' must be provided as a list")

        normalized: List[ObjectiveDefinition] = []
        for entry in raw_objectives:
            if isinstance(entry, ObjectiveDefinition):
                normalized.append(entry)
                continue

            if isinstance(entry, str):
                normalized.append(ObjectiveDefinition.from_directive(entry))
                continue

            if isinstance(entry, dict):
                normalized.append(cls._objective_from_dict(entry))
                continue

            raise ValueError(f"Unsupported objective entry type: {type(entry)}")

        return normalized

    @staticmethod
    def _parse_computation(computation: Any) -> Optional[ObjectiveComputationSpec]:
        if computation is None:
            return None
        if isinstance(computation, ObjectiveComputationSpec):
            return computation
        if isinstance(computation, dict):
            payload = dict(computation)
            if "multi-steps" in payload and "multi_steps" not in payload:
                payload["multi_steps"] = payload.pop("multi-steps")
            return ObjectiveComputationSpec(**payload)
        raise ValueError("Invalid computation block for objective; expected mapping or ObjectiveComputationSpec")

    @classmethod
    def _objective_from_dict(cls, payload: Dict[str, Any]) -> ObjectiveDefinition:
        if "name" not in payload:
            raise ValueError("Objective entry missing required field 'name'")

        if "direction" in payload:
            direction_raw = payload["direction"]
            direction = direction_raw if isinstance(direction_raw, ObjectiveDirection) else ObjectiveDirection(str(direction_raw).lower())
        else:
            minimize = payload.get("minimize", True)
            direction = ObjectiveDirection.MINIMIZE if minimize else ObjectiveDirection.MAXIMIZE

        computation = cls._parse_computation(payload.get("computation"))
        metrics_keys = payload.get("metrics_keys", []) or []

        return ObjectiveDefinition(
            name=payload["name"],
            direction=direction,
            computation=computation,
            metrics_keys=metrics_keys,
        )

    def parse_algorithm_params(self) -> Optional[BaseModel]:
        """
        If an algorithm-specific config model is registered under `optimizer.name`,
        parse and return a validated model instance for `optimizer.parameters`.
        Returns None if no model is registered.
        """
        Model = get_algorithm_config_model(self.optimizer.name)
        if Model:
            return Model(**(self.optimizer.parameters or {}))
        return None
