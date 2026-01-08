"""Optimization configuration models."""

from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field
from .optimization_registry import get_algorithm_config_model


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
    objectives: List[str] = Field(default_factory=list)  # e.g., ["minimize:f1", "maximize:f2"]
    
    # Constraint definitions
    constraints: List[str] = Field(default_factory=list)  # e.g., ["x1 < 10", "x2 > 0"]
    
    # Search space configuration
    n_iterations: int = 100
    n_initial_samples: int = 10
    parallel_evaluations: int = 1

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
