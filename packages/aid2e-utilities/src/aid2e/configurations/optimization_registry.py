"""Registry for algorithm-specific optimization config models.

Optimizers can register their Pydantic models keyed by algorithm name.
Utilities can look up the model to parse `optimizer.parameters`.
"""
from typing import Dict, Type, Optional
from pydantic import BaseModel

_algorithm_configs: Dict[str, Type[BaseModel]] = {}


def register_algorithm_config(name: str, model: Type[BaseModel]) -> None:
    """Register a Pydantic model for an optimization algorithm.

    Args:
        name: Algorithm identifier (e.g., "nsga2", "mobo").
        model: Pydantic model class that validates algorithm-specific params.
    """
    _algorithm_configs[name.lower()] = model


def get_algorithm_config_model(name: str) -> Optional[Type[BaseModel]]:
    """Retrieve a registered algorithm config model by name."""
    return _algorithm_configs.get(name.lower())
