"""Scheduler/Runner configuration models.

Supports multiple execution backends:
- JobLibRunner: Local parallel execution using joblib
- SlurmRunner: HPC cluster execution via SLURM
- PanDAiDDSRunner: Distributed execution via PanDA iDDS
"""

from typing import Dict, Optional, List, Any, Literal
from pydantic import BaseModel, Field
from .scheduler_registry import get_runner_config_model

# Lazy import wrapper for JobLibRunnerConfig
def __getattr__(name: str):
    """Lazy-load JobLibRunnerConfig to avoid circular imports."""
    if name == "JobLibRunnerConfig":
        from aid2e.schedulers.JobLib import JobLibRunnerConfig
        return JobLibRunnerConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class SlurmRunnerConfig(BaseModel):
    """Configuration for SLURM HPC runner."""
    partition: str = Field(
        default="gpu",
        description="SLURM partition/queue name"
    )
    ntasks: int = Field(
        default=1,
        description="Number of tasks to run"
    )
    cpus_per_task: int = Field(
        default=1,
        description="CPU cores per task"
    )
    mem_per_task: str = Field(
        default="4GB",
        description="Memory per task (e.g., '4GB', '8000MB')"
    )
    time_limit: str = Field(
        default="01:00:00",
        description="Wall clock time limit (HH:MM:SS)"
    )
    gres: Optional[str] = Field(
        default=None,
        description="Generic resource allocation (e.g., 'gpu:1' for one GPU)"
    )
    job_name: str = Field(
        default="aid2e_job",
        description="SLURM job name"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="Directory for SLURM output/error logs"
    )
    additional_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional SLURM parameters as dict (e.g., {'mail-type': 'END', 'mail-user': 'user@example.com'})"
    )


class PanDAiDDSRunnerConfig(BaseModel):
    """Configuration for PanDA iDDS distributed runner."""
    request_id: Optional[int] = Field(
        default=None,
        description="PanDA iDDS request ID for tracking"
    )
    campaign_name: str = Field(
        default="aid2e_optimization",
        description="Campaign name for PanDA tracking"
    )
    processing_type: str = Field(
        default="optimization",
        description="Type of processing in PanDA system"
    )
    vo: str = Field(
        default="atlas",
        description="Virtual organization (VO) in PanDA"
    )
    cloud: Optional[str] = Field(
        default=None,
        description="Target cloud/site for execution"
    )
    n_workers: int = Field(
        default=10,
        description="Number of worker processes in PanDA"
    )
    max_concurrent_tasks: int = Field(
        default=20,
        description="Maximum concurrent tasks at once"
    )
    timeout_per_task: int = Field(
        default=3600,
        description="Timeout per task in seconds"
    )
    retry_policy: str = Field(
        default="exponential",
        description="Retry policy: 'immediate', 'linear', 'exponential'"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum number of retries per failed task"
    )
    additional_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional PanDA iDDS parameters"
    )


class SchedulerConfiguration(BaseModel):
    """Complete scheduler/runner configuration."""
    
    runner_type: Literal["JobLibRunner", "SlurmRunner", "PanDAiDDSRunner"] = Field(
        default="JobLibRunner",
        description="Type of runner/scheduler to use"
    )
    
    # Runner-specific configuration - one of these will be populated
    joblib: Optional[BaseModel] = Field(
        default=None,
        description="JobLib-specific configuration (used when runner_type='JobLibRunner')"
    )
    slurm: Optional[SlurmRunnerConfig] = Field(
        default=None,
        description="SLURM-specific configuration (used when runner_type='SlurmRunner')"
    )
    panda: Optional[PanDAiDDSRunnerConfig] = Field(
        default=None,
        description="PanDA iDDS-specific configuration (used when runner_type='PanDAiDDSRunner')"
    )
    
    # Common settings
    max_retries: int = Field(
        default=3,
        description="Global maximum retries for failed jobs"
    )
    output_location: str = Field(
        default="./scheduler_output",
        description="Base directory for scheduler output files"
    )
    monitor_interval: int = Field(
        default=30,
        description="Monitoring interval in seconds for job status checks"
    )
    
    class Config:
        """Pydantic config."""
        extra = "allow"  # Allow additional fields for extensibility
    
    def get_active_config(self) -> Optional[BaseModel]:
        """Get the active runner-specific configuration based on runner_type.
        
        Returns:
            The appropriate config object (JobLibRunnerConfig, SlurmRunnerConfig, 
            or PanDAiDDSRunnerConfig), or None if no matching config exists.
        """
        if self.runner_type == "JobLibRunner":
            return self.joblib
        elif self.runner_type == "SlurmRunner":
            return self.slurm
        elif self.runner_type == "PanDAiDDSRunner":
            return self.panda
        return None
    
    def parse_runner_params(self) -> Optional[BaseModel]:
        """
        Look up runner-specific config model via registry and parse parameters.
        Falls back to get_active_config() if no registry entry found.
        
        Returns:
            Validated runner-specific config model, or None.
        """
        Model = get_runner_config_model(self.runner_type)
        if Model:
            config = self.get_active_config()
            if config:
                return Model(**config.dict())
        return self.get_active_config()

