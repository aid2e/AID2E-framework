"""Registry for runner-specific scheduler config models.

Follows the optimizer _registry pattern: register/get/list_registered. The
registry maps runner type names (e.g., "JobLibRunner") to Pydantic config
classes (e.g., JobLibRunnerConfig) used to validate runner-specific parameters.
"""

from typing import Callable, Dict, Type, Optional
from pydantic import BaseModel

_runner_config_registry: Dict[str, Type[BaseModel]] = {}
_runner_config_loaders: Dict[str, Callable[[], Type[BaseModel]]] = {
    "JobLibRunner": lambda: __import__(
        "aid2e.schedulers.JobLib", fromlist=["JobLibRunnerConfig"]
    ).JobLibRunnerConfig,
    "PanDAiDDSRunner": lambda: __import__(
        "aid2e.schedulers.PanDAiDDS", fromlist=["PanDAiDDSRunnerConfig"]
    ).PanDAiDDSRunnerConfig,
    "SlurmRunner": lambda: __import__(
        "aid2e.schedulers.Slurm", fromlist=["SlurmRunnerConfig"]
    ).SlurmRunnerConfig,
}


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
    if name in _runner_config_registry:
        return _runner_config_registry[name]
    if name in _runner_config_loaders:
        model = _runner_config_loaders[name]()
        _runner_config_registry[name] = model
        return model
    return None


def list_registered() -> Dict[str, Type[BaseModel]]:
    """Get all registered runner config models.

    Returns:
        Dict mapping runner type names to Pydantic config classes.
    """
    for name in list(_runner_config_loaders.keys()):
        if name not in _runner_config_registry:
            try:
                _runner_config_registry[name] = _runner_config_loaders[name]()
            except Exception:
                pass
    return _runner_config_registry.copy()
