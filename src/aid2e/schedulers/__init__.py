"""Schedulers for local and distributed execution backends.

Current built-in scheduler:
- JobLibScheduler: Local parallel execution using joblib.

Registries mirror the optimizer layout for consistency, providing register,
get, and list_registered helpers in aid2e.schedulers._registry.
"""

from aid2e import __MAIN_VERSION__

from aid2e.schedulers.base import BaseScheduler, JobStatus, StageExecutionResult
from aid2e.schedulers._registry import (
    get,
    get_scheduler,
    is_registered,
    is_scheduler_registered,
    list_registered,
    list_registered_schedulers,
    register,
    register_scheduler,
)

__version__ = __MAIN_VERSION__

# Lazy imports for JobLib to avoid circular dependencies with joblib multiprocessing
def __getattr__(name: str):
    """Lazy-load JobLib subpackage when accessed."""
    if name == "JobLib":
        from aid2e.schedulers import JobLib as _joblib
        return _joblib
    if name == "JobLibRunnerConfig":
        from aid2e.schedulers.JobLib import JobLibRunnerConfig
        return JobLibRunnerConfig
    if name == "JobLibScheduler":
        from aid2e.schedulers.JobLib import JobLibScheduler
        return JobLibScheduler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BaseScheduler",
    "JobStatus",
    "StageExecutionResult",
    "JobLibScheduler",
    "JobLibRunnerConfig",
    "register",
    "get",
    "list_registered",
    "is_registered",
    "register_scheduler",
    "get_scheduler",
    "list_registered_schedulers",
    "is_scheduler_registered",
    "JobLib",
]
