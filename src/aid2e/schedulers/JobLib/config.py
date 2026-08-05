"""Pydantic configuration model for JobLib scheduler.

Registers the JobLib runner configuration with the scheduler config registry.
"""

from typing import Optional
from pydantic import BaseModel, Field

from aid2e.utilities.configurations.scheduler_registry import register as register_runner_config


class JobLibRunnerConfig(BaseModel):
    """Configuration for the JobLib-based local scheduler.

    Args:
        n_jobs: Number of workers (-1 uses all CPUs).
        backend: JobLib backend ("loky", "threading", or "multiprocessing").
        timeout: Optional per-job timeout in seconds.
        verbose: JobLib verbosity level (0-11).
    """

    n_jobs: int = Field(
        default=-1,
        description="Number of jobs for parallel execution. -1 means use all processors",
    )
    backend: str = Field(
        default="loky",
        description="Backend for joblib: 'loky', 'threading', or 'multiprocessing'",
    )
    timeout: Optional[int] = Field(
        default=None,
        description="Timeout in seconds for each job",
    )
    verbose: int = Field(
        default=0,
        description="Verbosity level (0-11) for joblib logging",
    )


# Register with the runner-config registry for lookup by runner_type
register_runner_config("JobLibRunner", JobLibRunnerConfig)
