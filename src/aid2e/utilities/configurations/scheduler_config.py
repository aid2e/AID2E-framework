"""Scheduler configuration models.

Unified scheduler configuration for AID2E workflow execution.
Runner-specific parameters are validated via the scheduler registry.

Supports multiple execution backends:
- JobLibRunner: Local parallel execution using joblib
- SlurmRunner: HPC cluster execution via SLURM
- PanDAiDDSRunner: Distributed execution via PanDA iDDS

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from typing import Dict, Optional, Any, Literal
from pydantic import BaseModel, Field
from .scheduler_registry import get_runner_config_model


class SchedulerConfiguration(BaseModel):
    """Complete scheduler/runner configuration.
    
    Specifies which scheduler backend to use and its parameters.
    Runner-specific configuration is validated via the scheduler registry.
    
    Attributes:
        runner_type: Type of runner/scheduler to use (JobLibRunner, SlurmRunner, PanDAiDDSRunner).
        parameters: Runner-specific parameters as free-form dict.
        max_retries: Global maximum retries for failed jobs.
        output_location: Base directory for scheduler output files.
        monitor_interval: Monitoring interval in seconds for job status checks.
        
    Example:
        >>> config = SchedulerConfiguration(
        ...     runner_type="JobLibRunner",
        ...     parameters={"n_jobs": -1, "backend": "threading"},
        ...     output_location="./output"
        ... )
    """
    
    runner_type: Literal["JobLibRunner", "SlurmRunner", "PanDAiDDSRunner"] = Field(
        default="JobLibRunner",
        description="Type of runner/scheduler to use"
    )
    
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Runner-specific parameters (validated by scheduler registry)"
    )
    
    max_retries: int = Field(
        default=3,
        ge=0,
        description="Global maximum retries for failed jobs"
    )
    output_location: str = Field(
        default="./scheduler_output",
        description="Base directory for scheduler output files"
    )
    monitor_interval: int = Field(
        default=30,
        ge=1,
        description="Monitoring interval in seconds for job status checks"
    )
    
    class Config:
        """Pydantic configuration.
        
        Allows additional fields for forward compatibility with new runners.
        """
        extra = "allow"
    
    def parse_runner_params(self) -> Optional[BaseModel]:
        """Parse and validate runner-specific parameters via registry.
        
        Looks up the registered config model for this runner_type and
        validates the parameters dict against it.
        
        Returns:
            Validated runner-specific config model instance, or None if 
            runner type not found in registry.
            
        Raises:
            ValidationError: If parameters don't match the runner's schema.
            
        Example:
            >>> config = SchedulerConfiguration(
            ...     runner_type="JobLibRunner",
            ...     parameters={"n_jobs": 4}
            ... )
            >>> joblib_config = config.parse_runner_params()
            >>> joblib_config.n_jobs
            4
        """
        Model = get_runner_config_model(self.runner_type)
        if Model:
            return Model(**self.parameters)
        return None

