"""Registry for runner-specific scheduler config models.

Follows the optimizer _registry pattern: register/get/list_registered. The
registry maps runner type names (e.g., "JobLibRunner") to Pydantic config
classes (e.g., JobLibRunnerConfig) used to validate runner-specific parameters.
"""

from typing import Dict, Type, Optional
from pydantic import BaseModel

_runner_config_registry: Dict[str, Type[BaseModel]] = {}


def register(name: str, model: Type[BaseModel]) -> None:
    """Register a Pydantic model for a scheduler runner type.

    Args:
        name: Runner type identifier (e.g., "JobLibRunner", "SlurmRunner", "PanDAiDDSRunner").
        model: Pydantic model class that validates runner-specific params.
    """
    name_key = name
    _runner_config_registry[name_key] = model


def get(name: str) -> Optional[Type[BaseModel]]:
    """Retrieve a registered runner config model by name.

    Args:
        name: Runner type identifier.

    Returns:
        The registered Pydantic model class, or None if not registered.
    """
    return _runner_config_registry.get(name)


def list_registered() -> Dict[str, Type[BaseModel]]:
    """Get all registered runner config models.

    Returns:
        Dict mapping runner type names to Pydantic config classes.
    """
    return _runner_config_registry.copy()


# Backward-compatible aliases
register_runner_config = register
get_runner_config_model = get
list_registered_runners = lambda: list(_runner_config_registry.keys())

