"""Pydantic configuration model for the Slurm scheduler."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SlurmRunnerConfig(BaseModel):
    """Configuration for Slurm command-job execution."""

    partition: Optional[str] = Field(default=None, description="Slurm partition to submit into.")
    account: Optional[str] = Field(default=None, description="Slurm account to charge.")
    qos: Optional[str] = Field(default=None, description="Slurm QoS value.")
    time: Optional[str] = Field(default=None, description="Walltime limit in Slurm format, e.g. 00:10:00.")
    nodes: int = Field(default=1, ge=1, description="Number of nodes requested.")
    ntasks: int = Field(default=1, ge=1, description="Number of tasks requested.")
    cpus_per_task: Optional[int] = Field(default=None, ge=1, description="CPUs per task.")
    mem: Optional[str] = Field(default=None, description="Memory request, e.g. 4G.")
    gres: Optional[str] = Field(default=None, description="Generic resources request, e.g. gpu:1.")
    constraint: Optional[str] = Field(default=None, description="Optional Slurm node constraint.")
    job_name_prefix: str = Field(default="aid2e", description="Prefix for generated Slurm job names.")
    setup_commands: List[str] = Field(
        default_factory=list,
        description="Commands emitted verbatim before the workload command.",
    )
    submit_working_dir: Optional[str] = Field(
        default=None,
        description="Directory where sbatch is invoked and batch scripts are written.",
    )
    runtime_working_dir: Optional[str] = Field(
        default=None,
        description="Directory the batch script should cd into before running the workload.",
    )
    poll_interval: int = Field(default=5, ge=1, description="Default stage polling interval in seconds.")
    sacct_poll_interval: int = Field(
        default=10,
        ge=1,
        description="Reserved poll interval for sacct checks in seconds.",
    )
    sbatch_extra_args: List[str] = Field(
        default_factory=list,
        description="Extra arguments appended to the sbatch command line.",
    )
    capture_stdout: bool = Field(default=True, description="Capture stdout into a scheduler-owned log file.")
    capture_stderr: bool = Field(default=True, description="Capture stderr into a scheduler-owned log file.")
