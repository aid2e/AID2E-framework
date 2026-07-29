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

import json
from pathlib import Path
from typing import Dict, Optional, Any, Literal
import yaml
from pydantic import BaseModel, Field, ConfigDict
from .scheduler_registry import get


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
    
    model_config = ConfigDict(extra="forbid")

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
        Model = get(self.runner_type)
        if Model:
            return Model(**self.parameters)
        return None


class SchedulerConfigLoader:
    """Loader for scheduler YAML/CONFIG files.

    Parses files following the scheduler schema:

        scheduler:
          runner_type: "JobLibRunner"
          parameters:
            n_jobs: 4

    Notes:
        Use `SchedulerConfigLoader.load()` to load from a file path or
        `SchedulerConfigLoader.from_dict()` to construct from an in-memory dictionary.
    """

    @staticmethod
    def _build_from_scheduler_dict(
        scheduler_payload: Dict[str, Any],
        base_dir: Optional[Path] = None,
    ) -> SchedulerConfiguration:
        """Build SchedulerConfiguration from an inner ``scheduler`` mapping."""
        if not isinstance(scheduler_payload, dict):
            raise ValueError("Invalid scheduler definition: expected a mapping")
        scheduler_payload = dict(scheduler_payload)
        required_keys = ["runner_type", "parameters"]
        missing = [key for key in required_keys if key not in scheduler_payload]
        if missing:
            raise ValueError("Invalid scheduler definition, missing keys: " + ", ".join(missing))
        config = SchedulerConfiguration(**scheduler_payload)
        parameters = dict(config.parameters)
        if config.runner_type == "SlurmRunner":
            template_file = parameters.get("template_file")
            if template_file is None:
                if not parameters:
                    raise ValueError("Invalid SlurmRunner scheduler parameters, provide inline definitions or template_file")
            else:
                template_path = Path(template_file).expanduser()
                if base_dir and not template_path.is_absolute():
                    template_path = (base_dir / template_path).resolve()
                if not template_path.exists():
                    raise FileNotFoundError(f"Slurm template file not found: {template_file}")

                with open(template_path, "r") as f:
                    template_data = json.load(f)
                if not isinstance(template_data, dict):
                    raise ValueError("Invalid Slurm template file: expected a JSON object")

                inline_parameters = dict(parameters)
                inline_parameters.pop("template_file")
                if not template_data and not inline_parameters:
                    raise ValueError("Invalid Slurm template file: expected scheduler parameters")
                scheduler_payload["parameters"] = {
                    **template_data,
                    **inline_parameters,
                }
            config = SchedulerConfiguration(**scheduler_payload)
            parameters = dict(config.parameters)
        if config.runner_type == "PanDAiDDSRunner":
            if not parameters:
                raise ValueError("Invalid PanDAiDDSRunner scheduler parameters, provide PanDA definitions")

        Model = get(config.runner_type)
        if Model is None:
            raise ValueError(f"No scheduler config model registered for {config.runner_type}")
        unknown_keys = sorted(set(parameters) - set(Model.model_fields))
        if unknown_keys:
            raise ValueError(
                f"Invalid {config.runner_type} scheduler parameters, unknown keys: "
                + ", ".join(unknown_keys)
            )
        Model(**parameters)

        return config

    @staticmethod
    def load(file_path: str) -> SchedulerConfiguration:
        """Load a scheduler configuration from a YAML file."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Scheduler file not found: {file_path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        if "scheduler" not in data or not isinstance(data["scheduler"], dict):
            raise ValueError("Invalid scheduler file: missing 'scheduler' section")

        return SchedulerConfigLoader._build_from_scheduler_dict(
            data["scheduler"],
            base_dir=path.parent,
        )

    @staticmethod
    def from_dict(
        scheduler_payload: Dict[str, Any],
        base_dir: Optional[str] = None,
    ) -> SchedulerConfiguration:
        """Construct SchedulerConfiguration from an inner scheduler mapping."""
        return SchedulerConfigLoader._build_from_scheduler_dict(
            scheduler_payload,
            base_dir=Path(base_dir) if base_dir else None,
        )
