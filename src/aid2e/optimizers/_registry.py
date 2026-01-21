"""Auto-registration system for optimizer configurations.

This module provides a simple registry for optimizer-specific configuration
models. Optimizer configs are registered when their modules are imported,
enabling discovery and validation without hard dependencies.

Usage:
    In optimizers/ax/config.py:
    >>> from aid2e.optimizers._registry import register
    >>> register("ax", AxOptimizerConfig)
    
    To retrieve:
    >>> from aid2e.optimizers._registry import get
    >>> config_class = get("ax")
"""

from typing import Dict, Type, Optional
from pydantic import BaseModel


_algorithm_configs: Dict[str, Type[BaseModel]] = {}


def register(name: str, config_class: Type[BaseModel]) -> None:
    """Register an optimizer configuration model.
    
    Args:
        name: Algorithm identifier (e.g., "ax", "nsga2")
        config_class: Pydantic BaseModel class for the config
    
    Raises:
        ValueError: If name is already registered
    
    Examples:
        >>> from pydantic import BaseModel
        >>> class MyOptimizerConfig(BaseModel):
        ...     param1: int = 10
        >>> register("myopt", MyOptimizerConfig)
    
    Notes:
        This is typically called automatically when optimizer modules are imported.
    """
    name_lower = name.lower()
    if name_lower in _algorithm_configs:
        raise ValueError(
            f"Configuration for '{name}' is already registered. "
            f"Cannot register '{config_class.__name__}' as replacement."
        )
    _algorithm_configs[name_lower] = config_class


def get(name: str) -> Optional[Type[BaseModel]]:
    """Retrieve a registered optimizer configuration model.
    
    Args:
        name: Algorithm identifier (e.g., "ax", "nsga2")
    
    Returns:
        Pydantic BaseModel class if registered, None otherwise
    
    Examples:
        >>> config_class = get("ax")
        >>> if config_class:
        ...     config = config_class(n_iterations=100)
    """
    return _algorithm_configs.get(name.lower())


def list_registered() -> Dict[str, Type[BaseModel]]:
    """List all registered optimizer configurations.
    
    Returns:
        Dictionary mapping algorithm names to config classes
    
    Examples:
        >>> all_configs = list_registered()
        >>> for name, config_class in all_configs.items():
        ...     print(f"{name}: {config_class.__name__}")
    """
    return _algorithm_configs.copy()
