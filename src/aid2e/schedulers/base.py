"""Base scheduler abstract class for job execution.

All schedulers (JobLib, SLURM, PanDA, etc.) inherit from BaseScheduler
and implement the core interface: run_stage(), check_status(), cancel_job().

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/AID2E-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel


class JobStatus(BaseModel):
    """Represent status information for a single job.

    Args:
        job_id: Unique job identifier.
        status: Current status ("queued", "running", "completed", "failed", "cancelled").
        return_code: Exit code when completed or failed.
        stdout: Standard output from the job.
        stderr: Standard error from the job.
        metrics: Optional metrics (e.g., runtime, memory usage).
    """

    job_id: str
    status: str
    return_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


class StageExecutionResult(BaseModel):
    """Capture the result of executing all jobs in a stage.

    Args:
        stage_name: Name of the executed stage.
        job_statuses: Status for each job in the stage.
        artifacts: Output artifacts collected from the stage (path -> content).
        success: Whether all jobs completed successfully.
        error_message: Optional error message if the stage failed.
    """

    stage_name: str
    job_statuses: List[JobStatus]
    artifacts: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None


class BaseScheduler(ABC):
    """Define the common scheduler interface.

    Schedulers execute workflow stages on different backends (local, SLURM, PanDA, etc.).
    They handle job submission, monitoring, retries, and artifact collection.
    """

    def __init__(self, config: Optional[BaseModel] = None) -> None:
        """Initialize the scheduler with executor-specific configuration.

        Args:
            config: Executor-specific config (e.g., JobLibRunnerConfig, SlurmRunnerConfig).
        """

        self.config = config or {}

    @abstractmethod
    def run_stage(
        self,
        stage_name: str,
        job_definitions: List[Dict[str, Any]],
        parallelism_policy: Optional[Dict[str, Any]] = None,
        working_dir: Optional[str] = None,
    ) -> StageExecutionResult:
        """Execute all jobs in a stage respecting parallelism constraints.

        Args:
            stage_name: Name of the stage being executed.
            job_definitions: Job dictionaries with command, payload, outputs, etc.
            parallelism_policy: Parallelism settings (max_concurrent, retry_max, timeout_sec).
            working_dir: Working directory for job execution.

        Returns:
            StageExecutionResult describing job outcomes and collected artifacts.
        """

    @abstractmethod
    def check_status(self, job_id: str) -> JobStatus:
        """Check the status of a previously submitted job.

        Args:
            job_id: Unique job identifier returned from ``run_stage``.

        Returns:
            JobStatus with current state and metrics (if available).
        """

    @abstractmethod
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job if it is still running.

        Args:
            job_id: Unique job identifier.

        Returns:
            True if the job was cancelled, False otherwise.
        """

    def shutdown(self) -> None:
        """Clean up scheduler resources (optional for implementations)."""

        return None
