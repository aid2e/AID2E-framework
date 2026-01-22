"""Registry and factory for scheduler implementations.

Aligns with the optimizer registry pattern: register, get, list_registered, and
is_registered. Uses lazy registration to avoid circular imports with joblib.
"""

from typing import Dict, Type, Optional, Callable

from aid2e.schedulers.base import BaseScheduler

# In-memory mapping of scheduler identifiers to their classes
_scheduler_registry: Dict[str, Type[BaseScheduler]] = {}

# Lazy loaders: map of name -> function that returns scheduler class
_scheduler_loaders: Dict[str, Callable[[], Type[BaseScheduler]]] = {
    "joblib": lambda: __import__("aid2e.schedulers.JobLib", fromlist=["JobLibScheduler"]).JobLibScheduler,
}


def register(name: str, scheduler_class: Type[BaseScheduler]) -> None:
    """Register a scheduler implementation.

    Args:
        name: Identifier used to retrieve the scheduler (case-insensitive).
        scheduler_class: Scheduler class that implements BaseScheduler.

    Raises:
        ValueError: If name is already registered or scheduler_class is invalid.
    """

    name_key = name.lower()
    if name_key in _scheduler_registry:
        raise ValueError(f"Scheduler '{name}' already registered")
    if not issubclass(scheduler_class, BaseScheduler):
        raise ValueError("Scheduler class must inherit from BaseScheduler")

    _scheduler_registry[name_key] = scheduler_class


def get(name: str) -> Type[BaseScheduler]:
    """Retrieve a scheduler class by name (with lazy loading).

    Args:
        name: Identifier that was used during registration.

    Returns:
        Scheduler class implementing BaseScheduler.

    Raises:
        KeyError: If the scheduler is not registered.
    """

    name_key = name.lower()

    # First check if already loaded
    if name_key in _scheduler_registry:
        return _scheduler_registry[name_key]

    # Try lazy loader
    if name_key in _scheduler_loaders:
        scheduler_class = _scheduler_loaders[name_key]()
        _scheduler_registry[name_key] = scheduler_class
        return scheduler_class

    available = list(_scheduler_registry.keys()) + list(_scheduler_loaders.keys())
    raise KeyError(f"Scheduler '{name}' not registered. Available: {available}")


def list_registered() -> Dict[str, Type[BaseScheduler]]:
    """Return a copy of the registered schedulers mapping.

    Loads all lazy-registered schedulers.
    """

    # Load all lazy schedulers
    for name in list(_scheduler_loaders.keys()):
        if name not in _scheduler_registry:
            try:
                _scheduler_registry[name] = _scheduler_loaders[name]()
            except Exception:
                pass  # Skip if fails to load

    return _scheduler_registry.copy()


def is_registered(name: str) -> bool:
    """Return True if the scheduler name is registered or can be lazy-loaded."""

    name_key = name.lower()
    return name_key in _scheduler_registry or name_key in _scheduler_loaders


# Backward-compatible aliases
register_scheduler = register
get_scheduler = get
list_registered_schedulers = list_registered
is_scheduler_registered = is_registered
