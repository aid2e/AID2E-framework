"""Optimizer configuration models.

Defines the canonical top-level ``optimizer`` section used by full AID2E
configuration files. Problem objectives and problem/design constraints live in
the ``problem`` section; optimizer configuration is limited to backend
selection and backend-specific parameters.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from .optimization_registry import get


class OptimizerConfiguration(BaseModel):
    """Canonical optimizer section model."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Optimizer/backend name, for example 'ax'.")
    type: str = Field(..., description="Optimizer family, for example 'bayesian'.")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optimizer runtime parameters and backend-specific settings.",
    )

    def parse_algorithm_params(self) -> Optional[BaseModel]:
        """Parse registered backend-specific parameters if a model exists."""
        model = get(self.name)
        if model:
            return model(**(self.parameters or {}))
        return None
