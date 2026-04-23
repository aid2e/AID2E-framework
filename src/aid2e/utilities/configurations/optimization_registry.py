"""Canonical registry for optimizer parameter-schema models.

Optimizer backends register their Pydantic config models here, and config
utilities use the registry to validate ``optimizer.parameters`` payloads.
Built-in backends are loaded lazily so schema lookup works even before their
config modules have been imported elsewhere.
"""

from __future__ import annotations

import importlib
from typing import Callable, Dict, Optional, Type

from pydantic import BaseModel

_algorithm_configs: Dict[str, Type[BaseModel]] = {}
_algorithm_config_loaders: Dict[str, Callable[[], None]] = {
    "ax": lambda: importlib.import_module("aid2e.optimizers.ax.config"),
    "pymoo": lambda: importlib.import_module("aid2e.optimizers.pymoo.config"),
}


def register(name: str, model: Type[BaseModel]) -> None:
    """Register an optimizer config model by backend name."""
    key = name.lower()
    if key in _algorithm_configs:
        raise ValueError(
            f"Configuration for '{name}' is already registered. "
            f"Cannot register '{model.__name__}' as replacement."
        )
    _algorithm_configs[key] = model


def get(name: str) -> Optional[Type[BaseModel]]:
    """Retrieve a registered optimizer config model, loading built-ins lazily."""
    key = name.lower()
    if key in _algorithm_configs:
        return _algorithm_configs[key]

    loader = _algorithm_config_loaders.get(key)
    if loader is None:
        return None

    loader()
    return _algorithm_configs.get(key)


def list_registered() -> Dict[str, Type[BaseModel]]:
    """Return registered optimizer config models after loading built-ins."""
    for name, loader in _algorithm_config_loaders.items():
        if name not in _algorithm_configs:
            loader()
    return _algorithm_configs.copy()
