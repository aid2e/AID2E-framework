"""
AID2E Schedulers module - JobLib, SLURM, and PanDA schedulers.

This module provides job runners and integration with the Ax Platform
for running optimization trials on different execution backends.

Runners:
    - JobLibRunner: Local parallel execution using joblib
    - SlurmRunner: Cluster execution via SLURM (Phase 2)
    - PanDAiDDSRunner: Distributed execution via PanDA/iDDS (Phase 2)

Integration:
    - ax_integration: Helper functions to bridge AID2E configs with Ax Platform
"""

from aid2e import __MAIN_VERSION__

from .base_runner import BaseRunner
from .job import Job, JobType
from .job_state import JobState
from .joblib_runner import JobLibRunner
from .ax_integration import (
    create_ax_client_from_config,
    get_runner_from_config,
    create_scheduler_from_config,
    convert_results_to_ax_format,
)

__version__ = __MAIN_VERSION__
__all__ = [
    # Core classes
    "BaseRunner",
    "Job",
    "JobType",
    "JobState",
    # Runners
    "JobLibRunner",
    # Integration helpers
    "create_ax_client_from_config",
    "get_runner_from_config",
    "create_scheduler_from_config",
    "convert_results_to_ax_format",
]
